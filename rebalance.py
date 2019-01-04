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
    from_channel = vars(arguments)['from']
    to_channel = arguments.to

    if arguments.incoming is not None and not arguments.list_candidates:
        print("--outgoing and --incoming only work in conjunction with --list-candidates")
        sys.exit()

    if arguments.list_candidates:
        incoming = arguments.incoming is None or arguments.incoming
        list_candidates(incoming=incoming)
        sys.exit()

    if from_channel is None and to_channel is None:
        argument_parser.print_help()
        sys.exit()

    # If only the 'from' channel is specified, we need to find routes to any 'to' channel, so there
    # is some work to do to find all channels with incoming capacity, find routes to them, rank them etc. We could
    # also think of splitting the amount to distribute it over several 'to' channels to keep them at reasonable
    # levels. Anyway, not supported yet.
    if from_channel and (to_channel is None):
        print("From-only mode is not supported yet.")
        sys.exit()

    # first we deal with the first argument, channel, to figure out what it means
    if to_channel and len(to_channel) < 4:
        # here we are in the "channel index" case
        index = int(to_channel) - 1
        candidates = get_rebalance_candidates()
        candidate = candidates[index]
        remote_pubkey = candidate.remote_pubkey
    else:
        # else the channel argument should be the node's pubkey
        remote_pubkey = to_channel
        # candidate is a channel -- we find it by filtering through all candidates
        candidate = [c for c in get_rebalance_candidates() if c.remote_pubkey == remote_pubkey][0]

    # then we figure out whether an amount was specified or if we compute it ourselves
    if arguments.amount:
        amount = int(arguments.amount)
    else:
        amount = int(math.ceil(float(get_remote_surplus(candidate)) / 2))
        if amount > MAX_SATOSHIS_PER_TRANSACTION:
            amount = MAX_SATOSHIS_PER_TRANSACTION

    first_hop_pubkey = from_channel
    response = Logic(lnd, first_hop_pubkey, remote_pubkey, amount).rebalance()
    if response:
        print(response)


def get_argument_parser():
    parser = argparse.ArgumentParser()
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
                                 help="public key identifying the outgoing channel (which will be emptied)")
    rebalance_group.add_argument("-t", "--to",
                                 metavar="CHANNEL",
                                 help="public key identifying the incoming channel (which will be filled)")
    # args.amount is essentially a list, and what matters to us is the first value it *may* have
    rebalance_group.add_argument("amount",
                                 help="Amount of the rebalance, in satoshis. If not specified,"
                                      "the amount computed for a perfect rebalance will be used"
                                      " (up to the maximum of 4,294,967 satoshis)",
                                 nargs="?")
    return parser


def list_candidates(incoming=True):
    index = 0
    candidates = get_rebalance_candidates(incoming=incoming)
    for candidate in candidates:
        index += 1
        rebalance_amount_int = abs(int(math.ceil(float(get_remote_surplus(candidate)) / 2)))
        rebalance_amount = "{:,}".format(rebalance_amount_int)
        if rebalance_amount_int > MAX_SATOSHIS_PER_TRANSACTION:
            rebalance_amount += " (max per transaction: {:,})".format(MAX_SATOSHIS_PER_TRANSACTION)

        print("(%2d) Pubkey:      " % index + candidate.remote_pubkey)
        print("Channel ID:       " + str(candidate.chan_id))
        print("Local ratio:      {:.3f}".format(get_local_ratio(candidate)))
        print("Capacity:         {:,}".format(candidate.capacity))
        print("Remote balance:   {:,}".format(candidate.remote_balance))
        print("Local balance:    {:,}".format(candidate.local_balance))
        print("Amount for 50-50: " + rebalance_amount)
        print(get_capacity_and_ratio_bar(candidate))
        print("")
    print("")
    print("Run with two arguments: 1) pubkey of channel to fill 2) amount")


def get_rebalance_candidates(incoming=True):
    if incoming:
        low_local = list(filter(lambda c: get_local_ratio(c) < 0.5, lnd.get_channels()))
        return sorted(low_local, key=get_remote_surplus, reverse=False)
    else:
        high_local = list(filter(lambda c: get_local_ratio(c) > 0.5, lnd.get_channels()))
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
    return int(os.popen('stty size', 'r').read().split()[1])


lnd = Lnd()
main()
