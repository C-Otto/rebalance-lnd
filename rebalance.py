#!/usr/bin/env python

import argparse
import math
import os
import sys

from lnd import Lnd

from logic import Logic

MAX_CHANNEL_CAPACITY = 16777215
MAX_SATOSHIS_PER_TRANSACTION = 4294967


def main():
    argument_parser = get_argument_parser()
    arguments = argument_parser.parse_args()
    first_hop_channel_id = vars(arguments)['from']
    to_channel = arguments.to

    channel_ratio = float(arguments.ratio) / 100

    if arguments.incoming is not None and not arguments.list_candidates:
        print("--outgoing and --incoming only work in conjunction with --list-candidates")
        sys.exit()

    if arguments.list_candidates:
        incoming = arguments.incoming is None or arguments.incoming
        if incoming:
            list_incoming_candidates(channel_ratio)
        else:
            list_outgoing_candidates(channel_ratio)
        sys.exit()

    if to_channel is None:
        argument_parser.print_help()
        sys.exit()

    # the 'to' argument might be an index, or a channel ID
    if to_channel and to_channel < 10000:
        # here we are in the "channel index" case
        index = int(to_channel) - 1
        candidates = get_incoming_rebalance_candidates(channel_ratio)
        candidate = candidates[index]
        last_hop_channel = candidate
    else:
        # else the channel argument should be the channel ID
        last_hop_channel = get_channel_for_channel_id(to_channel)

    amount = get_amount(arguments, first_hop_channel_id, last_hop_channel)

    if amount == 0:
        print("Amount is 0, nothing to do")
        sys.exit()

    response = Logic(lnd, first_hop_channel_id, last_hop_channel, amount, channel_ratio).rebalance()
    if response:
        print(response)


def get_amount(arguments, first_hop_channel_id, last_hop_channel):
    if arguments.amount:
        amount = int(arguments.amount)
    else:
        amount = get_rebalance_amount(last_hop_channel)
        if first_hop_channel_id:
            first_hop_channel = get_channel_for_channel_id(first_hop_channel_id)
            rebalance_amount_from_channel = get_rebalance_amount(first_hop_channel)
            if amount > rebalance_amount_from_channel:
                amount = rebalance_amount_from_channel

    if amount > MAX_SATOSHIS_PER_TRANSACTION:
        amount = MAX_SATOSHIS_PER_TRANSACTION

    return amount


def get_channel_for_channel_id(channel_id):
    for channel in lnd.get_channels():
        if channel.chan_id == channel_id:
            return channel
    return None


def get_argument_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("-r", "--ratio", action="store", type=int, dest="ratio", default=50,
                        help="ratio for channel imbalance between 1 and 50%%, eg. 45 for 45%%")
    list_group = parser.add_argument_group("list candidates", "Show the unbalanced channels.")
    list_group.add_argument("-l", "--list-candidates", action="store_true",
                            help="list candidate channels for rebalance")

    direction_group = list_group.add_mutually_exclusive_group()
    direction_group.add_argument("-o", "--outgoing",
                                 action="store_const",
                                 const=False,
                                 dest="incoming",
                                 help="lists channels with more than 50%% of the funds on the local side")
    direction_group.add_argument("-i", "--incoming",
                                 action="store_const",
                                 const=True,
                                 dest="incoming",
                                 help="(default) lists channels with more than 50%% of the funds on the remote side")

    rebalance_group = parser.add_argument_group("rebalance",
                                                "Rebalance a channel. You need to specify at least"
                                                " the 'to' channel (-t).")
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
    rebalance_group.add_argument("-a", "--amount",
                                 type=int,
                                 help="Amount of the rebalance, in satoshis. If not specified, "
                                      "the amount computed for a perfect rebalance will be used"
                                      " (up to the maximum of 4,294,967 satoshis)")
    return parser


def list_incoming_candidates(channel_ratio):
    candidates = get_incoming_rebalance_candidates(channel_ratio)
    list_candidates(candidates)


def list_outgoing_candidates(channel_ratio):
    candidates = get_outgoing_rebalance_candidates(channel_ratio)
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


def get_incoming_rebalance_candidates(channel_ratio):
    low_local = list(filter(lambda c: get_local_ratio(c) < channel_ratio, lnd.get_channels()))
    low_local = list(filter(lambda c: get_rebalance_amount(c) > 0, low_local))
    return sorted(low_local, key=get_remote_surplus, reverse=False)


def get_outgoing_rebalance_candidates(channel_ratio):
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
    if sys.__stdin__.isatty():
        return int(os.popen('stty size', 'r').read().split()[1])
    else:
        return 80


lnd = Lnd()
main()
