import sys
from route_extension import RouteExtension

MAX_ROUTES_TO_REQUEST = 60
ROUTE_REQUEST_INCREMENT = 15


def debug(message):
    sys.stderr.write(message + "\n")


class Routes:
    def __init__(self, lnd, payment_request, first_hop_channel_id, last_hop_channel):
        self.lnd = lnd
        self.payment_request = payment_request
        self.first_hop_channel_id = first_hop_channel_id
        self.last_hop_channel = last_hop_channel
        self.all_routes = []
        self.returned_routes = []
        self.num_requested_routes = 0
        self.route_extension = RouteExtension(self.lnd, last_hop_channel, self.payment_request)

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
        routes = self.lnd.get_routes(self.last_hop_channel.remote_pubkey, self.get_amount(), num_routes_to_request)
        self.num_requested_routes = num_routes_to_request
        for route in routes:
            modified_route = self.add_rebalance_channel(route)
            self.add_route(modified_route)

    def add_rebalance_channel(self, route):
        return self.route_extension.add_rebalance_channel(route)

    def add_route(self, route):
        if route is None:
            return
        if route not in self.all_routes:
            self.all_routes.append(route)

    @staticmethod
    def print_route(route):
        route_str = " -> ".join(str(h.chan_id) for h in route.hops)
        return route_str

    def get_amount(self):
        return self.payment_request.num_satoshis
