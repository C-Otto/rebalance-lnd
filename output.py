import sys


class Output:
    def __init__(self, lnd):
        self.lnd = lnd

    @staticmethod
    def print_line(message):
        sys.stdout.write(f"{message}\n")

    @staticmethod
    def print_without_linebreak(message):
        sys.stdout.write(message)

    def print_route(self, route):
        route_str = "\n".join(
            self.get_channel_representation(h.chan_id, h.pub_key) + "\t" +
            self.get_fee_information(h, route)
            for h in route.hops
        )
        self.print_line(route_str)

    def get_channel_representation(self, chan_id, pubkey_to, pubkey_from=None):
        alias_to = self.lnd.get_node_alias(pubkey_to)
        if pubkey_from:
            alias_from = self.lnd.get_node_alias(pubkey_from)
            return f"{chan_id} ({alias_from} to {alias_to})"
        return f"{chan_id} to {alias_to:32}"

    @staticmethod
    def get_fee_information(next_hop, route):
        hops = list(route.hops)
        if hops[0] == next_hop:
            return ""
        hop = hops[hops.index(next_hop) - 1]
        ppm = int(hop.fee_msat * 1_000_000 / hop.amt_to_forward_msat)
        return f"(fee {hop.fee_msat:7,} mSAT, {ppm:5,}ppm)"
