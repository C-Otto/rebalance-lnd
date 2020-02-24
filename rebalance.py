#!/usr/bin/env python

import argparse
import math
import os
import platform
import sys

from lnd import Lnd
from logic import Logic

MAX_CHANNEL_CAPACITY = 16777215
MAX_SATOSHIS_PER_TRANSACTION = 4294967


def main():
    argument_parser = get_argument_parser()
    arguments = argument_parser.parse_args()
    lnd = Lnd(arguments.lnddir, arguments.grpc)
    first_hop_channel_id = vars(arguments)['from']
    to_channel = arguments.to

    if arguments.ratio < 1 or arguments.ratio > 50:
        print("--ratio must be between 1 and 50")
        sys.exit(1)
    channel_ratio = float(arguments.ratio) / 100

    if arguments.incoming is not None and not arguments.list_candidates:
        print("--outgoing and --incoming only work in conjunction with --list-candidates")
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

    # the 'to' argument might be an index, or a channel ID
    if to_channel and to_channel < 10000:
        # here we are in the "channel index" case
        index = int(to_channel) - 1
        candidates = get_incoming_rebalance_candidates(lnd, channel_ratio)
        candidate = candidates[index]
        last_hop_channel = candidate
    else:
        # else the channel argument should be the channel ID
        last_hop_channel = get_channel_for_channel_id(lnd, to_channel)

    first_hop_channel = get_channel_for_channel_id(lnd, first_hop_channel_id)

    amount = get_amount(arguments, first_hop_channel, last_hop_channel)

    if amount == 0:
        print("Amount is 0, nothing to do")
        sys.exit(0)

    max_fee_factor = arguments.max_fee_factor
    excluded = arguments.exclude
    return Logic(lnd, first_hop_channel, last_hop_channel, amount, channel_ratio, excluded,
                 max_fee_factor).rebalance()


def get_amount(arguments, first_hop_channel, last_hop_channel):
    if last_hop_channel:
        amount = get_rebalance_amount(last_hop_channel)
    else:
        amount = get_rebalance_amount(first_hop_channel)

    if arguments.percentage:
        amount = int(round(amount * arguments.percentage / 100))

    if last_hop_channel and first_hop_channel:
        rebalance_amount_from_channel = get_rebalance_amount(first_hop_channel)
        amount = min(amount, rebalance_amount_from_channel)

    if arguments.amount:
        amount = min(amount, int(arguments.amount))

    amount = min(amount, MAX_SATOSHIS_PER_TRANSACTION)

    return amount


def get_channel_for_channel_id(lnd, channel_id):
    for channel in lnd.get_channels():
        if channel.chan_id == channel_id:
            return channel
    return None


def get_argument_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lnddir",
                        default="~/.lnd",
                        dest="lnddir",
                        help="(default ~/.lnd) lnd directory")
    parser.add_argument("--grpc",
                        default="localhost:10009",
                        dest="grpc",
                        help="(default localhost:10009) lnd gRPC endpoint")
    parser.add_argument("-r", "--ratio",
                        type=int,
                        default=50,
                        help="(default: 50) ratio for channel imbalance between 1 and 50, "
                             "eg. 45 to only show channels (-l) with less than 45%% of the "
                             "funds on the local (-i) or remote (-o) side")
    list_group = parser.add_argument_group("list candidates", "Show the unbalanced channels.")
    list_group.add_argument("-l", "--list-candidates", action="store_true",
                            help="list candidate channels for rebalance")

    direction_group = list_group.add_mutually_exclusive_group()
    direction_group.add_argument("-o", "--outgoing",
                                 action="store_const",
                                 const=False,
                                 dest="incoming",
                                 help="lists channels with less than x%% of the funds on the remote side (see --ratio)")
    direction_group.add_argument("-i", "--incoming",
                                 action="store_const",
                                 const=True,
                                 dest="incoming",
                                 help="(default) lists channels with less than x%% of the funds on the local side "
                                      "(see --ratio)")

    rebalance_group = parser.add_argument_group("rebalance",
                                                "Rebalance a channel. You need to specify at least"
                                                " the 'from' channel (-f) or the 'to' channel (-t).")
    rebalance_group.add_argument("-f", "--from",
                                 metavar="CHANNEL",
                                 type=int,
                                 help="channel ID of the outgoing channel "
                                      "(funds will be taken from this channel)")
    rebalance_group.add_argument("-t", "--to",
                                 metavar="CHANNEL",
                                 type=int,
                                 help="channel ID of the incoming channel "
                                      "(funds will be sent to this channel). "
                                      "You may also use the index as shown in the incoming candidate list (-l -i).")
    amount_group = rebalance_group.add_mutually_exclusive_group()
    amount_group.add_argument("-a", "--amount",
                              type=int,
                              help="Amount of the rebalance, in satoshis. If not specified, "
                                   "the amount computed for a perfect rebalance will be used"
                                   " (up to the maximum of 4,294,967 satoshis)")
    amount_group.add_argument("-p", "--percentage",
                              type=int,
                              help="Set the amount to send to a percentage of the amount required to rebalance. "
                                   "As an example, if this is set to 50, the amount will half of the default. "
                                   "See --amount.")
    rebalance_group.add_argument("-e", "--exclude",
                                 type=int,
                                 action="append",
                                 help="Exclude the given channel ID as the outgoing channel (no funds will be taken "
                                      "out of excluded channels)")
    rebalance_group.add_argument("--max-fee-factor",
                                 type=float,
                                 default=10,
                                 help="(default: 10) Reject routes that cost more than x times the lnd default "
                                      "(base: 1 sat, rate: 1 millionth sat) per hop on average")
    return parser


def list_incoming_candidates(lnd, channel_ratio):
    candidates = get_incoming_rebalance_candidates(lnd, channel_ratio)
    list_candidates(candidates)


def list_outgoing_candidates(lnd, channel_ratio):
    candidates = get_outgoing_rebalance_candidates(lnd, channel_ratio)
    list_candidates(candidates)


def list_candidates(candidates):
    index = 0
    for candidate in candidates:
        index += 1
        rebalance_amount_int = get_rebalance_amount(candidate)
        rebalance_amount = "{:,}".format(rebalance_amount_int)
        if rebalance_amount_int > MAX_SATOSHIS_PER_TRANSACTION:
            rebalance_amount += " (max per transaction: {:,})".format(MAX_SATOSHIS_PER_TRANSACTION)

        print("(%2d) Channel ID:  " % index + str(candidate.chan_id))
        print("Pubkey:           " + candidate.remote_pubkey)
        print("Local ratio:      {:.3f}".format(get_local_ratio(candidate)))
        print("Capacity:         {:,}".format(candidate.capacity))
        print("Remote balance:   {:,}".format(candidate.remote_balance))
        print("Local balance:    {:,}".format(candidate.local_balance))
        print("Amount for 50-50: " + rebalance_amount)
        print(get_capacity_and_ratio_bar(candidate))
        print("")


def get_rebalance_amount(channel):
    return abs(int(math.ceil(float(get_remote_surplus(channel)) / 2)))


def get_incoming_rebalance_candidates(lnd, channel_ratio):
    low_local = list(filter(lambda c: get_local_ratio(c) < channel_ratio, lnd.get_channels()))
    low_local = list(filter(lambda c: get_rebalance_amount(c) > 0, low_local))
    return sorted(low_local, key=get_remote_surplus, reverse=False)


def get_outgoing_rebalance_candidates(lnd, channel_ratio):
    high_local = list(filter(lambda c: get_local_ratio(c) > 1 - channel_ratio, lnd.get_channels()))
    high_local = list(filter(lambda c: get_rebalance_amount(c) > 0, high_local))
    return sorted(high_local, key=get_remote_surplus, reverse=True)


def get_local_ratio(channel):
    remote = channel.remote_balance
    local = channel.local_balance
    return float(local) / (remote + local)


def get_remote_surplus(channel):
    return channel.remote_balance - channel.local_balance


def get_capacity_and_ratio_bar(candidate):
    columns = get_columns()
    columns_scaled_to_capacity = int(round(columns * float(candidate.capacity) / MAX_CHANNEL_CAPACITY))

    bar_width = columns_scaled_to_capacity - 2
    result = "|"
    ratio = get_local_ratio(candidate)
    length = int(round(ratio * bar_width))
    for x in range(0, length):
        result += "="
    for x in range(length, bar_width):
        result += " "
    return result + "|"


def get_columns():
    if platform.system() == 'Linux' and sys.__stdin__.isatty():
        return int(os.popen('stty size', 'r').read().split()[1])
    else:
        return 80


success = main()
if success:
    sys.exit(0)
sys.exit(1)
