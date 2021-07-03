import base64

from utils import debug

MAX_ROUTES_TO_REQUEST = 100


class Routes:
    def __init__(
        self,
        lnd,
        payment_request,
        first_hop_channel,
        last_hop_channel,
        fee_limit_msat,
        min_fee_msat_last_hop,
    ):
        self.lnd = lnd
        self.payment_request = payment_request
        self.first_hop_channel = first_hop_channel
        self.last_hop_channel = last_hop_channel
        self.all_routes = []
        self.returned_routes = []
        self.ignored_pairs = []
        self.ignored_nodes = []
        self.num_requested_routes = 0
        self.fee_limit_msat = fee_limit_msat
        self.min_fee_msat_last_hop = min_fee_msat_last_hop

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
        amount = self.get_amount()
        if self.last_hop_channel:
            last_hop_pubkey = self.last_hop_channel.remote_pubkey
        else:
            last_hop_pubkey = None
        if self.first_hop_channel:
            first_hop_channel_id = self.first_hop_channel.chan_id
        else:
            first_hop_channel_id = None
        routes = self.lnd.get_route(
            last_hop_pubkey,
            amount,
            self.ignored_pairs,
            self.ignored_nodes,
            first_hop_channel_id,
            self.fee_limit_msat,
        )
        if routes is None:
            self.num_requested_routes = MAX_ROUTES_TO_REQUEST
        else:
            self.num_requested_routes += 1
            for route in routes:
                self.add_route(route)

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

    def ignore_first_hop(self, channel, show_message=True):
        own_key = self.lnd.get_own_pubkey()
        other_key = channel.remote_pubkey
        self.ignore_edge_from_to(channel.chan_id, own_key, other_key, show_message)

    def ignore_edge_on_route(self, failure_source_pubkey, route):
        ignore_next = False
        for hop in route.hops:
            if ignore_next:
                self.ignore_edge_from_to(
                    hop.chan_id, failure_source_pubkey, hop.pub_key
                )
                return
            if hop.pub_key == failure_source_pubkey:
                ignore_next = True

    def ignore_hop_on_route(self, hop_to_ignore, route):
        previous_pubkey = self.lnd.get_own_pubkey()
        for hop in route.hops:
            if hop == hop_to_ignore:
                self.ignore_edge_from_to(hop.chan_id, previous_pubkey, hop.pub_key)
                return
            previous_pubkey = hop.pub_key

    def ignore_high_fee_hops(self, route):
        ignore = []
        if self.min_fee_msat_last_hop:
            last_hop = route.hops[-1]
            if last_hop.fee_msat < self.min_fee_msat_last_hop:
                ignore.append(last_hop)
        max_fee_msat = 0
        max_fee_hop = None
        for hop in route.hops:
            if self.last_hop_channel and self.last_hop_channel.chan_id == hop.chan_id:
                continue
            if self.first_hop_channel and self.first_hop_channel.chan_id == hop.chan_id:
                continue
            if hop.fee_msat > max_fee_msat:
                max_fee_msat = hop.fee_msat
                max_fee_hop = hop

        if max_fee_hop:
            ignore.append(max_fee_hop)
        for hop in ignore:
            self.ignore_hop_on_route(hop, route)

    def ignore_edge_from_to(self, chan_id, from_pubkey, to_pubkey, show_message=True):
        if show_message:
            debug(f"ignoring channel {chan_id} (from {from_pubkey} to {to_pubkey})")
        pair = {
            "from": base64.b16decode(from_pubkey, True),
            "to": base64.b16decode(to_pubkey, True),
        }
        self.ignored_pairs.append(pair)

    def ignore_node(self, pub_key):
        debug(f"ignoring node {pub_key}")
        self.ignored_nodes.append(base64.b16decode(pub_key, True))
