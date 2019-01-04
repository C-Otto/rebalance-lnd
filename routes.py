import sys
from route_extension import RouteExtension

MAX_ROUTES_TO_REQUEST = 60
ROUTE_REQUEST_INCREMENT = 15


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
        self.route_extension = RouteExtension(self.lnd, self.rebalance_channel, self.payment)

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
        return self.route_extension.add_rebalance_channel(route)

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
