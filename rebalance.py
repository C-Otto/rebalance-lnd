#!/usr/bin/env python3

import argparse
import os
import platform
import random
import sys

from yachalk import chalk

from lnd import Lnd
from logic import Logic
from output import Output, format_alias, format_ppm, format_amount, format_amount_green, format_boring_string, \
    print_bar, format_channel_id, format_error

MAX_SATOSHIS_PER_TRANSACTION = 4294967


class Rebalance:
    def __init__(self, arguments):
        self.lnd = Lnd(arguments.macaroon_hex, arguments.tls_cert, arguments.grpc)
        self.output = Output(self.lnd)
        self.min_amount = arguments.min_amount
        self.arguments = arguments
        self.first_hop_channel_id = self.parse_channel_id(vars(arguments)["from"])
        self.last_hop_channel_id = self.parse_channel_id(arguments.to)
        self.first_hop_channel = None
        self.last_hop_channel = None
        self.min_local = arguments.min_local
        self.min_remote = arguments.min_remote

    @staticmethod
    def parse_channel_id(id_string):
        if not id_string:
            return None
        arr = None
        if ":" in id_string:
            arr = id_string.rstrip().split(":")
        elif "x" in id_string:
            arr = id_string.rstrip().split("x")
        if arr:
            return (int(arr[0]) << 40) + (int(arr[1]) << 16) + int(arr[2])
        return int(id_string)

    def get_sort_key(self, channel):
        rebalance_amount = self.get_rebalance_amount(channel)
        if rebalance_amount >= 0:
            return (
                self.lnd.get_ppm_to(channel.chan_id) * rebalance_amount,
                get_remote_available(channel) - get_local_available(channel)
            )
        return rebalance_amount, self.lnd.get_ppm_to(channel.chan_id)

    def get_scaled_min_local(self, channel):
        local_available = get_local_available(channel)
        remote_available = get_remote_available(channel)
        if local_available + remote_available >= self.min_local + self.min_remote:
            return self.min_local
        return self.min_local / (self.min_local + self.min_remote) * (local_available + remote_available)

    def get_scaled_min_remote(self, channel):
        local_available = get_local_available(channel)
        remote_available = get_remote_available(channel)
        if local_available + remote_available >= self.min_local + self.min_remote:
            return self.min_remote
        return self.min_remote / (self.min_local + self.min_remote) * (local_available + remote_available)

    def get_rebalance_amount(self, channel):
        local_available = get_local_available(channel)
        remote_available = get_remote_available(channel)
        too_small = local_available + remote_available < self.min_local + self.min_remote
        if too_small:
            return int(self.get_scaled_min_local(channel) - local_available)
        if local_available < self.min_local:
            return self.min_local - local_available
        if remote_available < self.min_remote:
            return remote_available - self.min_remote
        return 0

    def get_amount(self):
        amount = None
        if self.arguments.amount:
            if self.arguments.reckless and self.arguments.amount > MAX_SATOSHIS_PER_TRANSACTION:
                self.output.print_line(format_error("Trying to send wumbo transaction"))
                return self.arguments.amount
            else:
                amount = min(self.arguments.amount, MAX_SATOSHIS_PER_TRANSACTION)
                if not self.arguments.adjust_amount_to_limits:
                    return amount

        should_send = 0
        can_send = 0
        if self.first_hop_channel:
            should_send = -self.get_rebalance_amount(self.first_hop_channel)
            can_send = self.get_amount_can_send(self.first_hop_channel)

            if can_send < 0:
                from_alias = self.lnd.get_node_alias(self.first_hop_channel.remote_pubkey)
                print(
                    f"Error: source channel {format_channel_id(self.first_hop_channel.chan_id)} to "
                    f"{format_alias(from_alias)} needs to {chalk.green('receive')} funds to be within bounds,"
                    f" you want it to {chalk.red('send')} funds. "
                    "Specify amount manually if this was intended."
                )
                return 0

        should_receive = 0
        can_receive = 0
        if self.last_hop_channel:
            should_receive = self.get_rebalance_amount(self.last_hop_channel)
            can_receive = self.get_amount_can_receive(self.last_hop_channel)

            if can_receive < 0:
                to_alias = self.lnd.get_node_alias(self.last_hop_channel.remote_pubkey)
                print(
                    f"Error: target channel {format_channel_id(self.last_hop_channel.chan_id)} to "
                    f"{format_alias(to_alias)} needs to {chalk.green('send')} funds to be within bounds, "
                    f"you want it to {chalk.red('receive')} funds."
                    f" Specify amount manually if this was intended."
                )
                return 0

        if self.first_hop_channel and self.last_hop_channel:
            computed_amount = max(min(can_receive, should_send), min(can_send, should_receive))
        elif self.first_hop_channel:
            computed_amount = should_send
        else:
            computed_amount = should_receive

        computed_amount = int(computed_amount)
        if computed_amount >= 0:
            computed_amount = min(computed_amount, MAX_SATOSHIS_PER_TRANSACTION)
        computed_amount = max(computed_amount, -MAX_SATOSHIS_PER_TRANSACTION)
        if amount is not None:
            if computed_amount >= 0:
                computed_amount = min(amount, computed_amount)
            else:
                computed_amount = max(-amount, computed_amount)
        return computed_amount

    def get_amount_can_send(self, channel):
        return get_local_available(channel) - self.get_scaled_min_local(channel)

    def get_amount_can_receive(self, channel):
        return get_remote_available(channel) - self.get_scaled_min_remote(channel)

    def get_channel_for_channel_id(self, channel_id):
        for channel in self.lnd.get_channels():
            if channel.chan_id == channel_id:
                return channel
        return None

    def list_channels(self, reverse=False):
        sorted_channels = sorted(
            self.lnd.get_channels(active_only=True),
            key=lambda c: self.get_sort_key(c),
            reverse=reverse
        )
        for channel in sorted_channels:
            self.show_channel(channel, reverse)

    def show_channel(self, channel, reverse=False):
        rebalance_amount = self.get_rebalance_amount(channel)
        if not self.arguments.show_all and not self.arguments.show_only:
            if rebalance_amount < 0 and not reverse:
                return
            if rebalance_amount > 0 and reverse:
                return
            if abs(rebalance_amount) < self.min_amount:
                return
        rebalance_amount_formatted = f"{rebalance_amount:10,}"
        if rebalance_amount > MAX_SATOSHIS_PER_TRANSACTION:
            rebalance_amount_formatted += (
                f" (max per transaction: {MAX_SATOSHIS_PER_TRANSACTION:,})"
            )
        own_ppm = self.lnd.get_ppm_to(channel.chan_id)
        remote_ppm = self.lnd.get_ppm_from(channel.chan_id)
        print(f"Channel ID:       {format_channel_id(channel.chan_id)}")
        print(f"Alias:            {format_alias(self.lnd.get_node_alias(channel.remote_pubkey))}")
        print(f"Pubkey:           {format_boring_string(channel.remote_pubkey)}")
        print(f"Channel Point:    {format_boring_string(channel.channel_point)}")
        print(f"Local ratio:      {get_local_ratio(channel):.3f}")
        print(f"Fee rates:        {format_ppm(own_ppm)} (own), {format_ppm(remote_ppm)} (peer)")
        print(f"Capacity:         {channel.capacity:10,}")
        print(f"Remote available: {format_amount(get_remote_available(channel), 10)}")
        print(f"Local available:  {format_amount_green(get_local_available(channel), 10)}")
        print(f"Rebalance amount: {rebalance_amount_formatted}")
        print(get_capacity_and_ratio_bar(channel, self.lnd.get_max_channel_capacity()))
        print("")

    def list_channels_compact(self):
        candidates = sorted(
            self.lnd.get_channels(active_only=True),
            key=lambda c: self.get_sort_key(c),
            reverse=False
            )
        for candidate in candidates:
            id_formatted = format_channel_id(candidate.chan_id)
            local_formatted = format_amount_green(get_local_available(candidate), 11)
            remote_formatted = format_amount(get_remote_available(candidate), 11)
            alias_formatted = format_alias(self.lnd.get_node_alias(candidate.remote_pubkey))
            print(f"{id_formatted} | {local_formatted} | {remote_formatted} | {alias_formatted}")

    def start(self):
        if self.arguments.list_candidates and self.arguments.show_only:
            channel_id = self.parse_channel_id(self.arguments.show_only)
            channel = self.get_channel_for_channel_id(channel_id)
            self.show_channel(channel)
            sys.exit(0)

        if self.arguments.listcompact:
            self.list_channels_compact()
            sys.exit(0)

        if self.arguments.list_candidates:
            incoming = self.arguments.incoming is None or self.arguments.incoming
            if incoming:
                self.list_channels(reverse=False)
            else:
                self.list_channels(reverse=True)
            sys.exit(0)

        if self.first_hop_channel_id == -1:
            self.first_hop_channel = random.choice(self.get_first_hop_candidates())
        else:
            self.first_hop_channel = self.get_channel_for_channel_id(self.first_hop_channel_id)

        if self.last_hop_channel_id == -1:
            self.last_hop_channel = random.choice(self.get_last_hop_candidates())
        else:
            self.last_hop_channel = self.get_channel_for_channel_id(self.last_hop_channel_id)

        amount = self.get_amount()
        if self.arguments.percentage:
            new_amount = int(round(amount * self.arguments.percentage / 100))
            print(f"Using {self.arguments.percentage}% of amount {format_amount(amount)}: {format_amount(new_amount)}")
            amount = new_amount

        if amount == 0:
            print(f"Amount is {format_amount(0)} sat, nothing to do")
            sys.exit(1)

        if amount < self.min_amount:
            print(f"Amount {format_amount(amount)} sat is below limit of {format_amount(self.min_amount)} sat, "
                  f"nothing to do (see --min-amount)")
            sys.exit(1)

        if self.arguments.reckless:
            self.output.print_line(format_error("Reckless mode enabled!"))

        fee_factor = self.arguments.fee_factor
        fee_limit_sat = self.arguments.fee_limit
        fee_ppm_limit = self.arguments.fee_ppm_limit
        excluded = []
        if self.arguments.exclude:
            for chan_id in self.arguments.exclude:
                excluded.append(self.parse_channel_id(chan_id))
        return Logic(
            self.lnd,
            self.first_hop_channel,
            self.last_hop_channel,
            amount,
            excluded,
            fee_factor,
            fee_limit_sat,
            fee_ppm_limit,
            self.min_local,
            self.min_remote,
            self.output,
            self.arguments.reckless
        ).rebalance()

    def get_first_hop_candidates(self):
        result = []
        for channel in self.lnd.get_channels(active_only=True):
            if self.get_rebalance_amount(channel) < 0:
                result.append(channel)
        return result

    def get_last_hop_candidates(self):
        result = []
        for channel in self.lnd.get_channels(active_only=True):
            if self.get_rebalance_amount(channel) > 0:
                result.append(channel)
        return result


def main():
    argument_parser = get_argument_parser()
    arguments = argument_parser.parse_args()
    if arguments.incoming is not None and not arguments.list_candidates:
        print(
            "--outgoing and --incoming only work in conjunction with --list-candidates"
        )
        sys.exit(1)

    if arguments.percentage:
        if arguments.percentage < 1 or arguments.percentage > 100:
            print("--percentage must be between 1 and 100")
            argument_parser.print_help()
            sys.exit(1)

    if arguments.reckless and not arguments.amount:
        print("You need to specify an amount for --reckless")
        argument_parser.print_help()
        sys.exit(1)

    if arguments.reckless and arguments.adjust_amount_to_limits:
        print("You must not use -A/--adjust-amount-to-limits in combination with --reckless")
        argument_parser.print_help()
        sys.exit(1)

    if arguments.reckless and not arguments.fee_limit and not arguments.fee_ppm_limit:
        print("You need to specify a fee limit (-fee-limit or --fee-ppm-limit) for --reckless")
        argument_parser.print_help()
        sys.exit(1)

    first_hop_channel_id = vars(arguments)["from"]
    last_hop_channel_id = arguments.to

    no_channel_id_given = not last_hop_channel_id and not first_hop_channel_id
    if not arguments.listcompact and not arguments.list_candidates and no_channel_id_given:
        argument_parser.print_help()
        sys.exit(1)

    return Rebalance(arguments).start()


def get_argument_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--macaroon_hex",
        default="_DEFAULT_",
        dest="macaroon_hex",
        help="hex encoded admin macaroon",
    )
    parser.add_argument(
        "--tls_cert",
        default="_DEFAULT_",
        dest="tls_cert",
        help="base64 encoded tls cert",
    )
    parser.add_argument(
        "--network", 
        default='mainnet',
        dest='network',
        help='(default mainnet) lnd network (mainnet, testnet, simnet, ...)'
    )
    parser.add_argument(
        "--grpc",
        default="localhost:10009",
        dest="grpc",
        help="(default localhost:10009) lnd gRPC endpoint",
    )
    list_group = parser.add_argument_group(
        "list candidates", "Show the unbalanced channels."
    )
    list_group.add_argument(
        "-l",
        "--list-candidates",
        action="store_true",
        help="list candidate channels for rebalance",
    )

    show_options = list_group.add_mutually_exclusive_group()
    show_options.add_argument(
        "--show-all",
        default=False,
        action="store_true",
        help="also show channels with zero rebalance amount",
    )
    show_options.add_argument(
        "--show-only",
        type=str,
        metavar="CHANNEL",
        help="only show information about the given channel",
    )
    show_options.add_argument(
        "-c",
        "--compact",
        action="store_true",
        dest="listcompact",
        help="Shows a compact list of all channels, one per line including ID, inbound/outbound liquidity, and alias",
    )

    direction_group = list_group.add_mutually_exclusive_group()
    direction_group.add_argument(
        "-o",
        "--outgoing",
        action="store_const",
        const=False,
        dest="incoming",
        help="lists channels with less than 1,000,000 (--min-remote) satoshis inbound liquidity",
    )
    direction_group.add_argument(
        "-i",
        "--incoming",
        action="store_const",
        const=True,
        dest="incoming",
        help="(default) lists channels with less than 1,000,000 (--min-local) satoshis outbound liquidity",
    )

    rebalance_group = parser.add_argument_group(
        "rebalance",
        "Rebalance a channel. You need to specify at least"
        " the 'from' channel (-f) or the 'to' channel (-t).",
    )
    rebalance_group.add_argument(
        "-f",
        "--from",
        metavar="CHANNEL",
        type=str,
        help="Channel ID of the outgoing channel (funds will be taken from this channel). "
             "You may also specify the ID using the colon notation (12345:12:1), or the x notation (12345x12x1). "
             "You may also use -1 to choose a random candidate.",
    )
    rebalance_group.add_argument(
        "-t",
        "--to",
        metavar="CHANNEL",
        type=str,
        help="Channel ID of the incoming channel (funds will be sent to this channel). "
             "You may also specify the ID using the colon notation (12345:12:1), or the x notation (12345x12x1). "
             "You may also use -1 to choose a random candidate.",
    )
    amount_group = rebalance_group.add_mutually_exclusive_group()
    rebalance_group.add_argument(
        "-A",
        "--adjust-amount-to-limits",
        action="store_true",
        help="If set, adjust the amount to the limits (--min-local and --min-remote). The script will exit if the "
             "adjusted amount is below the --min-amount threshold. As such, this switch can be used if you do NOT want "
             "to rebalance if the channel is within the limits.",
    )
    amount_group.add_argument(
        "-a",
        "--amount",
        type=int,
        help="Amount of the rebalance, in satoshis. If not specified, "
             "the amount computed for a perfect rebalance will be used"
             " (up to the maximum of 4,294,967 satoshis)",
    )
    amount_group.add_argument(
        "-p",
        "--percentage",
        type=int,
        help="Set the amount to a percentage of the computed amount. "
             "As an example, if this is set to 50, half of the computed amount will be used. "
             "See --amount.",
    )
    rebalance_group.add_argument(
        "--min-amount",
        default=10_000,
        type=int,
        help="(Default: 10,000) If the given or computed rebalance amount is below this limit, nothing is done.",
    )
    rebalance_group.add_argument(
        "--min-local",
        type=int,
        default=1_000_000,
        help="(Default: 1,000,000) Ensure that the channels have at least this amount as outbound liquidity."
    )
    rebalance_group.add_argument(
        "--min-remote",
        type=int,
        default=1_000_000,
        help="(Default: 1,000,000) Ensure that the channels have at least this amount as inbound liquidity."
    )
    rebalance_group.add_argument(
        "-e",
        "--exclude",
        type=str,
        action="append",
        help="Exclude the given channel. Can be used multiple times.",
    )
    rebalance_group.add_argument(
        "--reckless",
        action="store_true",
        default=False,
        help="Allow rebalance transactions that are not economically viable. "
             "You might also want to set --min-local 0 and --min-remote 0. "
             "If set, you also need to set --amount and either --fee-limit or --fee-ppm-limit, and you must not enable "
             "--adjust-amount-to-limits (-A)."
    )
    rebalance_group.add_argument(
        "--fee-factor",
        default=1.0,
        type=float,
        help="(default: 1.0) Compare the costs against the expected "
        "income, scaled by this factor. As an example, with --fee-factor 1.5, "
        "routes that cost at most 150%% of the expected earnings are tried. Use values "
        "smaller than 1.0 to restrict routes to only consider those earning "
        "more/costing less. This factor is ignored with --reckless.",
    )
    fee_group = rebalance_group.add_mutually_exclusive_group()
    fee_group.add_argument(
        "--fee-limit",
        type=int,
        help="If set, only consider rebalance transactions that cost up to the given number of satoshis."
    )
    fee_group.add_argument(
        "--fee-ppm-limit",
        type=int,
        help="If set, only consider rebalance transactions that cost up to the given number of satoshis per "
             "1M satoshis sent."
    )
    return parser


def get_local_available(channel):
    return max(0, channel.local_balance - channel.local_chan_reserve_sat)


def get_remote_available(channel):
    return max(0, channel.remote_balance - channel.remote_chan_reserve_sat)


def get_local_ratio(channel):
    remote = channel.remote_balance
    local = channel.local_balance
    return float(local) / (remote + local)


def get_capacity_and_ratio_bar(candidate, max_channel_capacity):
    columns = get_columns()
    columns_scaled_to_capacity = int(
        round(columns * float(candidate.capacity) / max_channel_capacity)
    )
    if candidate.capacity >= max_channel_capacity:
        columns_scaled_to_capacity = columns

    bar_width = columns_scaled_to_capacity - 2
    ratio = get_local_ratio(candidate)
    length = int(round(ratio * bar_width))
    return print_bar(bar_width, length)


def get_columns():
    if platform.system() == "Linux" and sys.__stdin__.isatty():
        return int(os.popen("stty size", "r").read().split()[1])
    else:
        return 80


success = main()
if success:
    sys.exit(0)
sys.exit(1)
