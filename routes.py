import sys
import rpc_pb2 as ln

MAX_ROUTES = 50
HIGH_FEES_THRESHOLD_MSAT = 3000000


def debug(message):
    sys.stderr.write(message + "\n")


class Routes:
    def __init__(self, lnd, payment_request, remote_pubkey):
        self.lnd = lnd
        self.payment = payment_request
        self.remote_pubkey = remote_pubkey
        self.rebalance_channel = self.get_channel(self.remote_pubkey)
        self.total_time_lock = 0
        self.index = 0
        self.routes = self.get_routes()

    def has_next(self):
        return self.index < len(self.routes)

    def get_next(self):
        route = self.routes[self.index]
        self.index += 1
        return route

    def get_routes(self):
        num_routes = MAX_ROUTES
        routes = self.lnd.get_routes(self.remote_pubkey, self.get_amount(), num_routes)
        result = []
        for route in routes:
            modified_route = self.add_rebalance_channel(route)
            if modified_route:
                result.append(modified_route)
        return result

    # Returns a route if things went OK, None otherwise
    def add_rebalance_channel(self, route):
        hops = route.hops
        if self.low_local_ratio_after_sending(hops):
            # debug("Ignoring route, channel is low on funds")
            return None
        if self.is_first_hop(hops, self.rebalance_channel):
            # debug("Ignoring route, channel to add already is part of route")
            return None
        amount_msat = int(hops[-1].amt_to_forward_msat)

        expiry_last_hop = self.lnd.get_current_height() + self.get_expiry_delta_last_hop()
        self.total_time_lock = expiry_last_hop

        self.update_amounts(hops)
        self.update_expiry(hops)

        hops.extend([self.create_new_hop(amount_msat, self.rebalance_channel, expiry_last_hop)])

        if self.update_route_totals(route):
            return route
        else:
            return None

    # Returns True only if everything went well, False otherwise
    def update_route_totals(self, route):
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

        route.total_time_lock = self.total_time_lock
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
            hop.amt_to_forward = amount_to_forward_msat / 1000

            fee_msat_before = hop.fee_msat
            new_fee_msat = self.get_fee_msat(amount_to_forward_msat, hop.chan_id, hop.pub_key)
            hop.fee_msat = new_fee_msat
            hop.fee = new_fee_msat / 1000
            additional_fees += new_fee_msat - fee_msat_before

    def get_expiry_delta_last_hop(self):
        return self.payment.cltv_expiry

    def update_expiry(self, hops):
        for hop in reversed(hops):
            hop.expiry = self.total_time_lock

            channel_id = hop.chan_id
            target_pubkey = hop.pub_key
            policy = self.lnd.get_policy(channel_id, target_pubkey)

            time_lock_delta = policy.time_lock_delta
            self.total_time_lock += time_lock_delta

    @staticmethod
    def is_first_hop(hops, channel):
        return hops[0].pub_key == channel.remote_pubkey

    def get_fee_msat(self, amount_msat, channel_id, target_pubkey):
        policy = self.lnd.get_policy(channel_id, target_pubkey)
        fee_base_msat = self.get_fee_base_msat(policy)
        fee_rate_milli_msat = int(policy.fee_rate_milli_msat)
        return fee_base_msat + fee_rate_milli_msat * amount_msat / 1000000

    @staticmethod
    def get_fee_base_msat(policy):
        # sometimes that field seems not to be set -- interpret it as 0
        if hasattr(policy, "fee_base_msat"):
            return int(policy.fee_base_msat)
        return int(0)

    def low_local_ratio_after_sending(self, hops):
        pub_key = hops[0].pub_key
        channel = self.get_channel(pub_key)

        remote = channel.remote_balance + self.get_amount()
        local = channel.local_balance - self.get_amount()
        ratio = float(local) / (remote + local)
        return ratio < 0.5

    def get_amount(self):
        return self.payment.num_satoshis

    def get_channel(self, pubkey):
        for channel in self.lnd.get_channels():
            if channel.remote_pubkey == pubkey:
                return channel
