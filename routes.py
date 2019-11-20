import sys
from route_extension import RouteExtension

MAX_ROUTES_TO_REQUEST = 100


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
        self.ignored_edges = []
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
            self.request_route()

    def request_route(self):
        fee_last_hop_msat = self.route_extension.get_fee_msat(self.get_amount() * 1000, self.last_hop_channel.chan_id,
                                                              self.last_hop_channel.remote_pubkey)
        fee_last_hop = fee_last_hop_msat // 1000
        amount = self.get_amount() + fee_last_hop
        routes = self.lnd.get_route(self.last_hop_channel.remote_pubkey, amount, self.ignored_edges)
        if routes is None:
            self.num_requested_routes = MAX_ROUTES_TO_REQUEST
        else:
            self.num_requested_routes += 1
            for route in routes:
                modified_route = self.add_rebalance_channel(route)
                self.add_route(modified_route)

    def add_rebalance_channel(self, route):
        return self.route_extension.add_rebalance_channel(route, self.get_amount() * 1000)

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

    def ignore_first_hop(self, channel):
        own_key = self.lnd.get_own_pubkey()
        other_key = channel.remote_pubkey
        self.ignore_edge_from_to(channel.chan_id, own_key, other_key)

    def ignore_edge_on_route(self, failure_source_pubkey, route):
        ignore_next = False
        for hop in route.hops:
            if ignore_next:
                debug("ignoring channel %s (from %s to %s)" % (hop.chan_id, failure_source_pubkey, hop.pub_key))
                self.ignore_edge_from_to(hop.chan_id, failure_source_pubkey, hop.pub_key)
                return
            if hop.pub_key == failure_source_pubkey:
                ignore_next = True

    def ignore_highest_fee_hop(self, route):
        max_fee_msat = 0
        max_fee_hop_index = None
        index = 0
        for hop in route.hops:
            if hop.fee_msat > max_fee_msat:
                max_fee_msat = hop.fee_msat
                max_fee_hop_index = index
            index += 1

        max_fee_hop = route.hops[max_fee_hop_index]
        dest_pub_key = max_fee_hop.pub_key
        if max_fee_hop_index > 0:
            src_pub_key = route.hops[max_fee_hop_index - 1].pub_key
        else:
            src_pub_key = self.lnd.get_own_pubkey()
        debug("Ignoring %s (from %s to %s) because of high fees (%s msat)."
              % (max_fee_hop.chan_id, src_pub_key, dest_pub_key, max_fee_msat))
        self.ignore_edge_from_to(max_fee_hop.chan_id, src_pub_key, dest_pub_key)

    def ignore_edge_from_to(self, chan_id, from_pubkey, to_pubkey):
        direction_reverse = from_pubkey > to_pubkey
        edge = {"channel_id": chan_id, "direction_reverse": direction_reverse}
        self.ignored_edges.append(edge)
