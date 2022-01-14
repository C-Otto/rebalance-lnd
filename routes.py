import base64

MAX_ROUTES_TO_REQUEST = 100


class Routes:
    num_requested_routes = 0
    all_routes = []
    returned_routes = []
    ignored_pairs = []
    ignored_nodes = []

    def __init__(
        self,
        lnd,
        payment_request,
        first_hop_channel,
        last_hop_channel,
        fee_limit_msat,
        output
    ):
        self.lnd = lnd
        self.payment_request = payment_request
        self.first_hop_channel = first_hop_channel
        self.last_hop_channel = last_hop_channel
        self.fee_limit_msat = fee_limit_msat
        self.output = output

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
        max_fee_msat = -1
        max_fee_hop = None
        for hop in route.hops:
            if route.hops[-2].chan_id == hop.chan_id and self.last_hop_channel:
                continue
            if hop.fee_msat > max_fee_msat:
                max_fee_msat = hop.fee_msat
                max_fee_hop = hop

        if max_fee_hop:
            hops = list(route.hops)
            first_hop = hops[0]
            first_hop_fee_rate = self.lnd.get_ppm_to(first_hop.chan_id)
            missed_fee_first_hop_msat = first_hop.amt_to_forward_msat / 1_000_000 * first_hop_fee_rate
            if missed_fee_first_hop_msat > max_fee_msat and not self.first_hop_channel:
                ignore.append(first_hop)
            else:
                hop_to_ignore = hops[hops.index(max_fee_hop) + 1]
                ignore.append(hop_to_ignore)
        for hop in ignore:
            self.ignore_hop_on_route(hop, route)

    def ignore_channel(self, chan_id):
        try:
            edge = self.lnd.get_edge(chan_id)
        except Exception:
            return
        self.ignore_edge_from_to(chan_id, edge.node1_pub, edge.node2_pub)
        self.ignore_edge_from_to(chan_id, edge.node2_pub, edge.node1_pub)

    def ignore_edge_from_to(self, chan_id, from_pubkey, to_pubkey, show_message=True):
        pair = {
            "from": base64.b16decode(from_pubkey, True),
            "to": base64.b16decode(to_pubkey, True),
        }
        if pair in self.ignored_pairs:
            return
        if show_message:
            self.output.print_line(
                f"Ignoring {self.output.get_channel_representation(chan_id, to_pubkey, from_pubkey)}")
        self.ignored_pairs.append(pair)
