#!/usr/bin/env python3

import argparse
import math
import os
import platform
import random
import sys

from lnd import Lnd
from logic import Logic
from output import Output, format_alias, format_ppm, format_amount, format_amount_green, format_boring_string, print_bar

MAX_SATOSHIS_PER_TRANSACTION = 4294967


def main():
    argument_parser = get_argument_parser()
    arguments = argument_parser.parse_args()
    lnd = Lnd(arguments.lnddir, arguments.grpc)
    first_hop_channel_id = vars(arguments)["from"]
    to_channel = arguments.to

    if arguments.incoming is not None and not arguments.list_candidates:
        print(
            "--outgoing and --incoming only work in conjunction with --list-candidates"
        )
        sys.exit(1)

    if not arguments.list_candidates and to_channel is None and first_hop_channel_id is None:
        argument_parser.print_help()
        sys.exit(1)

    # get graph once to avoid weird delays in output
    output = Output(lnd)
    output.print_line("Requesting graph from lnd...", end='\r')
    lnd.get_graph()
    output.print_line("Requesting graph from lnd... done.")

    if arguments.list_candidates:
        incoming = arguments.incoming is None or arguments.incoming
        if incoming:
            list_incoming_candidates(lnd)
        else:
            list_outgoing_candidates(lnd)
        sys.exit(0)

    if first_hop_channel_id == -1:
        # pick a random channel as first hop
        first_hop_channel = random.choice(
            get_incoming_rebalance_candidates(lnd)
        )
    else:
        first_hop_channel = get_channel_for_channel_id(lnd, first_hop_channel_id)

    if to_channel == -1:
        # pick a random channel as last hop
        last_hop_channel = random.choice(
            get_incoming_rebalance_candidates(lnd)
        )
    else:
        last_hop_channel = get_channel_for_channel_id(lnd, to_channel)

    amount = get_amount(arguments, first_hop_channel, last_hop_channel)

    if amount == 0:
        print(f"Amount is {format_amount(0)} sat, nothing to do")
        sys.exit(0)

    min_amount = arguments.min_amount
    if amount < min_amount:
        print(f"Amount {format_amount(amount)} sat is below limit of {format_amount(min_amount)} sat, "
              f"nothing to do (see --min-amount)")
        sys.exit(0)

    fee_factor = arguments.fee_factor
    fee_limit_sat = arguments.fee_limit
    fee_ppm_limit = arguments.fee_ppm_limit
    excluded = arguments.exclude
    return Logic(
        lnd,
        first_hop_channel,
        last_hop_channel,
        amount,
        excluded,
        fee_factor,
        fee_limit_sat,
        fee_ppm_limit,
        output
    ).rebalance()


def get_amount(arguments, first_hop_channel, last_hop_channel):
    if arguments.amount:
        return min(arguments.amount, MAX_SATOSHIS_PER_TRANSACTION)

    if last_hop_channel:
        amount = get_rebalance_amount(last_hop_channel)
        remote_surplus = get_remote_surplus(last_hop_channel)
        if remote_surplus < 0:
            print(
                f"Error: last hop needs to SEND {abs(remote_surplus):,} sat to be balanced, "
                f"you want it to RECEIVE funds. Specify amount manually if this was intended."
            )
            return 0
    else:
        amount = get_rebalance_amount(first_hop_channel)
        remote_surplus = get_remote_surplus(first_hop_channel)
        if remote_surplus > 0:
            print(
                f"Error: first hop needs to RECEIVE {remote_surplus:,} sat to be balanced, you want it to SEND funds. "
                "Specify amount manually if this was intended."
            )
            return 0

    if last_hop_channel and first_hop_channel:
        rebalance_amount_from_channel = get_rebalance_amount(first_hop_channel)
        amount = min(amount, rebalance_amount_from_channel)

    amount = min(amount, MAX_SATOSHIS_PER_TRANSACTION)

    return amount


def get_channel_for_channel_id(lnd, channel_id):
    for channel in lnd.get_channels():
        if channel.chan_id == channel_id:
            return channel
    return None


def get_argument_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--lnddir",
        default="~/.lnd",
        dest="lnddir",
        help="(default ~/.lnd) lnd directory",
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

    direction_group = list_group.add_mutually_exclusive_group()
    direction_group.add_argument(
        "-o",
        "--outgoing",
        action="store_const",
        const=False,
        dest="incoming",
        help="lists channels with less than 50%% of the funds on the remote side",
    )
    direction_group.add_argument(
        "-i",
        "--incoming",
        action="store_const",
        const=True,
        dest="incoming",
        help="(default) lists channels with less than 50%% of the funds on the local side",
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
        type=int,
        help="Channel ID of the outgoing channel "
        "(funds will be taken from this channel). "
        "You may also use -1 to choose a random candidate.",
    )
    rebalance_group.add_argument(
        "-t",
        "--to",
        metavar="CHANNEL",
        type=int,
        help="Channel ID of the incoming channel "
        "(funds will be sent to this channel). "
        "You may also use -1 to choose a random candidate.",
    )
    rebalance_group.add_argument(
        "-a",
        "--amount",
        type=int,
        help="Amount of the rebalance, in satoshis. If not specified, "
        "the amount computed for a perfect rebalance will be used"
        " (up to the maximum of 4,294,967 satoshis)",
    )
    rebalance_group.add_argument(
        "--min-amount",
        default=10_000,
        type=int,
        help="(Default: 10,000) If the given or computed rebalance amount is below this limit, nothing is done.",
    )
    rebalance_group.add_argument(
        "-e",
        "--exclude",
        type=int,
        action="append",
        help="Exclude the given channel ID as the outgoing channel (no funds will be taken "
        "out of excluded channels)",
    )
    fee_group = rebalance_group.add_mutually_exclusive_group()
    fee_group.add_argument(
        "--fee-factor",
        default=1.0,
        type=float,
        help="(default: 1.0) Compare the costs against the expected "
        "income, scaled by this factor. As an example, with --fee-factor 1.5, "
        "routes that cost at most 150%% of the expected earnings are tried. Use values "
        "smaller than 1.0 to restrict routes to only consider those earning "
        "more/costing less.",
    )
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


def list_incoming_candidates(lnd):
    candidates = get_incoming_rebalance_candidates(lnd)
    list_candidates(lnd, candidates)


def list_outgoing_candidates(lnd):
    candidates = get_outgoing_rebalance_candidates(lnd)
    list_candidates(lnd, candidates)


def list_candidates(lnd, candidates):
    index = 0
    max_channel_capacity = 0
    for channel in lnd.get_channels():
        if channel.capacity > max_channel_capacity:
            max_channel_capacity = channel.capacity
    for candidate in candidates:
        index += 1
        remote_available = max(
            0, candidate.remote_balance - candidate.remote_chan_reserve_sat
        )
        local_available = max(
            0, candidate.local_balance - candidate.local_chan_reserve_sat
        )
        rebalance_amount_int = get_rebalance_amount(candidate)
        rebalance_amount = f"{rebalance_amount_int:10,}"
        if rebalance_amount_int > MAX_SATOSHIS_PER_TRANSACTION:
            rebalance_amount += (
                f" (max per transaction: {MAX_SATOSHIS_PER_TRANSACTION:,})"
            )

        print(f"Channel ID:       {format_boring_string(candidate.chan_id)}")
        print(f"Alias:            {format_alias(lnd.get_node_alias(candidate.remote_pubkey))}")
        print(f"Pubkey:           {format_boring_string(candidate.remote_pubkey)}")
        print(f"Channel Point:    {format_boring_string(candidate.channel_point)}")
        print(f"Local ratio:      {get_local_ratio(candidate):.3f}")
        print(f"Local fee rate:   {format_ppm(get_local_fee_rate(candidate, lnd))}")
        print(f"Capacity:         {candidate.capacity:10,}")
        print(f"Remote available: {format_amount(remote_available, 10)}")
        print(f"Local available:  {format_amount_green(local_available, 10)}")
        print(f"Amount for 50-50: {rebalance_amount}")
        print(get_capacity_and_ratio_bar(candidate, max_channel_capacity))
        print("")


def get_rebalance_amount(channel):
    return abs(int(math.ceil(float(get_remote_surplus(channel)) / 2)))


def get_rebalance_candidates(lnd, pred, reverse):
    active = filter(lambda c: c.active, lnd.get_channels())
    filtered = filter(pred, active)
    candidates = filter(lambda c: get_rebalance_amount(c) > 0, filtered)
    return sorted(candidates, key=get_remote_surplus, reverse=reverse)


def get_incoming_rebalance_candidates(lnd):
    return get_rebalance_candidates(
        lnd, lambda c: get_local_ratio(c) < 0.5, False
    )


def get_outgoing_rebalance_candidates(lnd):
    return get_rebalance_candidates(
        lnd, lambda c: get_local_ratio(c) > 0.5, True
    )


def get_local_ratio(channel):
    remote = channel.remote_balance
    local = channel.local_balance
    return float(local) / (remote + local)


def get_local_fee_rate(channel, lnd):
    return lnd.get_policy_to(channel.chan_id).fee_rate_milli_msat


def get_remote_surplus(channel):
    return channel.remote_balance - channel.local_balance


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
