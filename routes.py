import sys
import rpc_pb2 as ln

MAX_ROUTES_TO_REQUEST = 60
ROUTE_REQUEST_INCREMENT = 15
HIGH_FEES_THRESHOLD_MSAT = 3000000


def debug(message):
    sys.stderr.write(message + "\n")


class Routes:
    def __init__(self, lnd, payment_request, first_hop_pubkey, remote_pubkey):
        self.lnd = lnd
        self.payment = payment_request
        self.first_hop_pubkey = first_hop_pubkey
        self.remote_pubkey = remote_pubkey
        self.rebalance_channel = self.get_channel(self.remote_pubkey)
        self.all_routes = []
        self.returned_routes = []
        self.num_requested_routes = 0

    def has_next(self):
        self.update_routes()
        return self.returned_routes < self.all_routes

    def get_next(self):
        self.update_routes()
        for route in self.all_routes:
            if route not in self.returned_routes:
                self.returned_routes.append(route)
                return route
        return None

    def update_routes(self):
        while True:
            if self.returned_routes < self.all_routes:
                return
            if self.num_requested_routes >= MAX_ROUTES_TO_REQUEST:
                return
            num_routes_to_request = self.num_requested_routes + ROUTE_REQUEST_INCREMENT
            num_routes_to_request = min(MAX_ROUTES_TO_REQUEST, num_routes_to_request)
            self.request_routes(num_routes_to_request)

    def request_routes(self, num_routes_to_request):
        routes = self.lnd.get_routes(self.remote_pubkey, self.get_amount(), num_routes_to_request)
        self.num_requested_routes = num_routes_to_request
        for route in routes:
            modified_route = self.add_rebalance_channel(route)
            self.add_route(modified_route)

    def add_rebalance_channel(self, route):
        hops = route.hops
        last_hop = hops[-1]
        amount_msat = int(last_hop.amt_to_forward_msat)

        expiry_last_hop = self.lnd.get_current_height() + self.get_expiry_delta_last_hop()
        total_time_lock = expiry_last_hop

        self.update_amounts(hops)
        total_time_lock = self.update_expiry(hops, total_time_lock)

        hops.extend([self.create_new_hop(amount_msat, self.rebalance_channel, expiry_last_hop)])

        if self.update_route_totals(route, total_time_lock):
            return route
        else:
            return None

    @staticmethod
    # Returns True only if everything went well, False otherwise
    def update_route_totals(route, total_time_lock):
        total_fee_msat = 0
        for hop in route.hops:
            total_fee_msat += hop.fee_msat
        if total_fee_msat > HIGH_FEES_THRESHOLD_MSAT:
            debug("High fees! " + str(total_fee_msat) + " msat")
            return False

        total_amount_msat = route.hops[-1].amt_to_forward_msat + total_fee_msat

        route.total_amt_msat = total_amount_msat
        route.total_amt = total_amount_msat // 1000
        route.total_fees_msat = total_fee_msat
        route.total_fees = total_fee_msat // 1000

        route.total_time_lock = total_time_lock
        return True

    def create_new_hop(self, amount_msat, channel, expiry):
        new_hop = ln.Hop(
            chan_capacity=channel.capacity,
            fee_msat=0,
            fee=0,
            expiry=expiry,
            amt_to_forward_msat=amount_msat,
            amt_to_forward=amount_msat // 1000,
            chan_id=channel.chan_id,
            pub_key=self.lnd.get_own_pubkey(),
        )
        return new_hop

    def update_amounts(self, hops):
        additional_fees = 0
        for hop in reversed(hops):
            amount_to_forward_msat = hop.amt_to_forward_msat + additional_fees
            hop.amt_to_forward_msat = amount_to_forward_msat
            hop.amt_to_forward = amount_to_forward_msat // 1000

            fee_msat_before = hop.fee_msat
            new_fee_msat = self.get_fee_msat(amount_to_forward_msat, hop.chan_id, hop.pub_key)
            hop.fee_msat = new_fee_msat
            hop.fee = new_fee_msat // 1000
            additional_fees += new_fee_msat - fee_msat_before

    def get_expiry_delta_last_hop(self):
        return self.payment.cltv_expiry

    def update_expiry(self, hops, total_time_lock):
        for hop in reversed(hops):
            hop.expiry = total_time_lock

            channel_id = hop.chan_id
            target_pubkey = hop.pub_key
            policy = self.lnd.get_policy(channel_id, target_pubkey)

            time_lock_delta = policy.time_lock_delta
            total_time_lock += time_lock_delta
        return total_time_lock

    def get_fee_msat(self, amount_msat, channel_id, target_pubkey):
        policy = self.lnd.get_policy(channel_id, target_pubkey)
        fee_base_msat = self.get_fee_base_msat(policy)
        fee_rate_milli_msat = int(policy.fee_rate_milli_msat)
        return fee_base_msat + fee_rate_milli_msat * amount_msat // 1000000

    @staticmethod
    def get_fee_base_msat(policy):
        # sometimes that field seems not to be set -- interpret it as 0
        if hasattr(policy, "fee_base_msat"):
            return int(policy.fee_base_msat)
        return int(0)

    def add_route(self, route):
        if self.route_is_invalid(route):
            return

        if route not in self.all_routes:
            self.all_routes.append(route)

    def route_is_invalid(self, route):
        if route is None:
            return True
        first_hop = route.hops[0]
        if self.does_not_have_requested_first_hop(first_hop):
            return True
        if self.low_local_ratio_after_sending(first_hop):
            return True
        if self.target_is_first_hop(first_hop):
            return True
        return False

    def does_not_have_requested_first_hop(self, first_hop):
        if not self.first_hop_pubkey:
            return False
        return first_hop.pub_key != self.first_hop_pubkey

    def low_local_ratio_after_sending(self, first_hop):
        pub_key = first_hop.pub_key
        channel = self.get_channel(pub_key)

        remote = channel.remote_balance + self.get_amount()
        local = channel.local_balance - self.get_amount()
        ratio = float(local) / (remote + local)
        return ratio < 0.5

    def target_is_first_hop(self, first_hop):
        return first_hop.pub_key == self.rebalance_channel.remote_pubkey

    @staticmethod
    def print_route(route):
        route_str = " -> ".join(str(h.chan_id) for h in route.hops)
        return route_str

    def get_amount(self):
        return self.payment.num_satoshis

    def get_channel(self, pubkey):
        for channel in self.lnd.get_channels():
            if channel.remote_pubkey == pubkey:
                return channel
