import sys

from yachalk import chalk


class Output:
    def __init__(self, lnd):
        self.lnd = lnd

    @staticmethod
    def print_line(message, end='\n'):
        sys.stdout.write(f"{message}{end}")

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
        channel_id_formatted = chalk.gray(chan_id)
        if pubkey_from:
            alias_to_formatted = chalk.bold(self.lnd.get_node_alias(pubkey_to))
            alias_from = chalk.bold(self.lnd.get_node_alias(pubkey_from))
            return f"{channel_id_formatted} ({alias_from} to {alias_to_formatted})"
        alias_to_formatted = chalk.bold(f"{self.lnd.get_node_alias(pubkey_to):32}")
        return f"{channel_id_formatted} to {alias_to_formatted}"

    @staticmethod
    def get_fee_information(next_hop, route):
        hops = list(route.hops)
        if hops[0] == next_hop:
            return ""
        hop = hops[hops.index(next_hop) - 1]
        ppm = int(hop.fee_msat * 1_000_000 / hop.amt_to_forward_msat)
        fee_formatted = "fee " + chalk.cyan(f"{hop.fee_msat:8,} mSAT")
        ppm_formatted = chalk.bold(f"{ppm:5,}ppm")
        return f"({fee_formatted}, {ppm_formatted})"
