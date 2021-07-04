#!/usr/bin/env python3

import argparse
import math
import os
import platform
import random
import sys

from lnd import Lnd
from logic import Logic

MAX_CHANNEL_CAPACITY = 16777215
MAX_SATOSHIS_PER_TRANSACTION = 4294967


def main():
    argument_parser = get_argument_parser()
    arguments = argument_parser.parse_args()
    lnd = Lnd(arguments.lnddir, arguments.grpc)
    first_hop_channel_id = vars(arguments)["from"]
    to_channel = arguments.to

    if arguments.ratio < 1 or arguments.ratio > 50:
        print("--ratio must be between 1 and 50")
        sys.exit(1)
    channel_ratio = float(arguments.ratio) / 100

    if arguments.incoming is not None and not arguments.list_candidates:
        print(
            "--outgoing and --incoming only work in conjunction with --list-candidates"
        )
        sys.exit(1)

    if arguments.list_candidates:
        incoming = arguments.incoming is None or arguments.incoming
        if incoming:
            list_incoming_candidates(lnd, channel_ratio)
        else:
            list_outgoing_candidates(lnd, channel_ratio)
        sys.exit(0)

    if to_channel is None and first_hop_channel_id is None:
        argument_parser.print_help()
        sys.exit(1)

    percentage = arguments.percentage
    if percentage:
        if percentage < 1 or percentage > 100:
            print("--percentage must be between 1 and 100")
            argument_parser.print_help()
            sys.exit(1)

    # the 'to' argument might be an index, or a channel ID, or random
    if to_channel and 0 < to_channel < 10000:
        # here we are in the "channel index" case
        index = int(to_channel) - 1
        last_hop_channel = get_incoming_rebalance_candidates(lnd, channel_ratio)[index]
    elif to_channel == -1:
        # here is the random case
        last_hop_channel = random.choice(
            get_incoming_rebalance_candidates(lnd, channel_ratio)
        )
    else:
        # else the channel argument should be the channel ID
        last_hop_channel = get_channel_for_channel_id(lnd, to_channel)

    # the 'from' argument might be an index, or a channel ID, or random
    if first_hop_channel_id and 0 < first_hop_channel_id < 10000:
        # here we are in the "channel" index case
        index = int(first_hop_channel_id) - 1
        candidates = get_outgoing_rebalance_candidates(lnd, channel_ratio)
        first_hop_channel = candidates[index]
    elif first_hop_channel_id == -1:
        # here is the random case
        last_hop_channel = random.choice(
            get_incoming_rebalance_candidates(lnd, channel_ratio)
        )
    else:
        # else the channel argument should be the channel ID
        first_hop_channel = get_channel_for_channel_id(lnd, first_hop_channel_id)

    amount = get_amount(arguments, first_hop_channel, last_hop_channel)

    if amount == 0:
        print("Amount is 0, nothing to do")
        sys.exit(0)

    max_fee_factor = arguments.max_fee_factor
    econ_fee = arguments.econ_fee
    econ_fee_factor = arguments.econ_fee_factor
    excluded = arguments.exclude
    return Logic(
        lnd,
        first_hop_channel,
        last_hop_channel,
        amount,
        channel_ratio,
        excluded,
        max_fee_factor,
        econ_fee,
        econ_fee_factor,
    ).rebalance()


def get_amount(arguments, first_hop_channel, last_hop_channel):
    if arguments.amount:
        return min(arguments.amount, MAX_SATOSHIS_PER_TRANSACTION)

    if last_hop_channel:
        amount = get_rebalance_amount(last_hop_channel)
        remote_surplus = get_remote_surplus(last_hop_channel)
        if remote_surplus < 0:
            print(
                f"Error: last hop needs to SEND {abs(remote_surplus):,} sat to be balanced, you want it to RECEIVE funds. "
                "Specify amount manually if this was intended."
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

    if arguments.percentage:
        amount = int(round(amount * arguments.percentage / 100))

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
    parser.add_argument(
        "-r",
        "--ratio",
        type=int,
        default=50,
        help="(default: 50) ratio for channel imbalance between 1 and 50, "
        "eg. 45 to only show channels (-l) with less than 45%% of the "
        "funds on the local (-i) or remote (-o) side",
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
        help="lists channels with less than x%% of the funds on the remote side (see --ratio)",
    )
    direction_group.add_argument(
        "-i",
        "--incoming",
        action="store_const",
        const=True,
        dest="incoming",
        help="(default) lists channels with less than x%% of the funds on the local side "
        "(see --ratio)",
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
        "You may also use the index as shown in the incoming candidate list (-l -o), "
        "or -1 to choose a random candidate.",
    )
    rebalance_group.add_argument(
        "-t",
        "--to",
        metavar="CHANNEL",
        type=int,
        help="Channel ID of the incoming channel "
        "(funds will be sent to this channel). "
        "You may also use the index as shown in the incoming candidate list (-l -i), "
        "or -1 to choose a random candidate.",
    )
    amount_group = rebalance_group.add_mutually_exclusive_group()
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
        help="Set the amount to send to a percentage of the amount required to rebalance. "
        "As an example, if this is set to 50, the amount will half of the default. "
        "See --amount.",
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
        "--max-fee-factor",
        type=float,
        default=10,
        help="(default: 10) Reject routes that cost more than x times the lnd default "
        "(base: 1 sat, rate: 1 millionth sat) per hop on average",
    )
    fee_group.add_argument(
        "--econ-fee",
        default=False,
        action="store_true",
        help="(default: disabled) Economy Fee Mode, see README.md",
    )
    rebalance_group.add_argument(
        "--econ-fee-factor",
        default=1.0,
        type=float,
        help="(default: 1.0) When using --econ-fee, compare the costs against the expected "
        "income, scaled by this factor. As an example, with --econ-fee-factor 1.5, "
        "routes that cost at most 150%% of the expected earnings are tried. Use values "
        "smaller than 1.0 to restrict routes to only consider those earning "
        "more/costing less.",
    )
    return parser


def list_incoming_candidates(lnd, channel_ratio):
    candidates = get_incoming_rebalance_candidates(lnd, channel_ratio)
    list_candidates(lnd, candidates)


def list_outgoing_candidates(lnd, channel_ratio):
    candidates = get_outgoing_rebalance_candidates(lnd, channel_ratio)
    list_candidates(lnd, candidates)


def list_candidates(lnd, candidates):
    index = 0
    for candidate in candidates:
        index += 1
        remote_available = max(
            0, candidate.remote_balance - candidate.remote_chan_reserve_sat
        )
        local_available = max(
            0, candidate.local_balance - candidate.local_chan_reserve_sat
        )
        rebalance_amount_int = get_rebalance_amount(candidate)
        rebalance_amount = f"{rebalance_amount_int:,}"
        if rebalance_amount_int > MAX_SATOSHIS_PER_TRANSACTION:
            rebalance_amount += (
                f" (max per transaction: {MAX_SATOSHIS_PER_TRANSACTION:,})"
            )

        print(f"({index:2}) Channel ID:  {str(candidate.chan_id)}")
        print(f"Alias:            {lnd.get_node_alias(candidate.remote_pubkey)}")
        print(f"Pubkey:           {candidate.remote_pubkey}")
        print(f"Channel Point:    {candidate.channel_point}")
        print(f"Local ratio:      {get_local_ratio(candidate):.3f}")
        print(f"Capacity:         {candidate.capacity:,}")
        print(f"Remote available: {remote_available:,}")
        print(f"Local available:  {local_available:,}")
        print(f"Amount for 50-50: {rebalance_amount}")
        print(get_capacity_and_ratio_bar(candidate))
        print("")


def get_rebalance_amount(channel):
    return abs(int(math.ceil(float(get_remote_surplus(channel)) / 2)))


def get_rebalance_candidates(lnd, pred, reverse):
    active = filter(lambda c: c.active, lnd.get_channels())
    filtered = filter(pred, active)
    candidates = filter(lambda c: get_rebalance_amount(c) > 0, filtered)
    return sorted(candidates, key=get_remote_surplus, reverse=reverse)


def get_incoming_rebalance_candidates(lnd, channel_ratio):
    return get_rebalance_candidates(
        lnd, lambda c: get_local_ratio(c) < channel_ratio, False
    )


def get_outgoing_rebalance_candidates(lnd, channel_ratio):
    return get_rebalance_candidates(
        lnd, lambda c: get_local_ratio(c) > 1 - channel_ratio, True
    )


def get_local_ratio(channel):
    remote = channel.remote_balance
    local = channel.local_balance
    return float(local) / (remote + local)


def get_remote_surplus(channel):
    return channel.remote_balance - channel.local_balance


def get_capacity_and_ratio_bar(candidate):
    columns = get_columns()
    columns_scaled_to_capacity = int(
        round(columns * float(candidate.capacity) / MAX_CHANNEL_CAPACITY)
    )
    if candidate.capacity >= MAX_CHANNEL_CAPACITY:
        columns_scaled_to_capacity = columns

    bar_width = columns_scaled_to_capacity - 2
    result = "|"
    ratio = get_local_ratio(candidate)
    length = int(round(ratio * bar_width))
    for _ in range(0, length):
        result += "="
    for _ in range(length, bar_width):
        result += " "
    return f"{result}|"


def get_columns():
    if platform.system() == "Linux" and sys.__stdin__.isatty():
        return int(os.popen("stty size", "r").read().split()[1])
    else:
        return 80


success = main()
if success:
    sys.exit(0)
sys.exit(1)
