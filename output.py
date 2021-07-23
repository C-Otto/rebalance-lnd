import sys


class Output:
    def __init__(self, lnd):
        self.lnd = lnd

    @staticmethod
    def print_line(message):
        sys.stderr.write(f"{message}\n")

    @staticmethod
    def print_without_linebreak(message):
        sys.stderr.write(message)

    def print_route(self, route):
        route_str = "\n".join(self.get_channel_representation(h.chan_id, h.pub_key) for h in route.hops)
        self.print_line(route_str)

    def get_channel_representation(self, chan_id, pubkey_to, pubkey_from=None):
        alias_to = self.lnd.get_node_alias(pubkey_to)
        if pubkey_from:
            alias_from = self.lnd.get_node_alias(pubkey_from)
            return f"{chan_id} ({alias_from} to {alias_to})"
        return f"{chan_id}\t to {alias_to}"

    def get_node_representation(self, pubkey):
        alias = self.lnd.get_node_alias(pubkey)
        return f"{pubkey} ({alias})"
