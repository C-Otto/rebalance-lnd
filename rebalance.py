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
    remote_pubkey = None
    amount = None

    parser = argparse.ArgumentParser()

    parser.add_argument("-l", "--listcandidates", action="store_true", default=False)
    parser.add_argument("channel", help=("channel identifier, can be either the channel index as given by -l"
                                         " or the channel's pubkey"), nargs="?")
    # args.amount is essentially a list, and what matters to us is the first value it *may* have
    parser.add_argument("amount", help=("amount or the rebalance, in satoshis. If not specified, the amount computed"
                                        " for a perfect rebalance will be used"), nargs='?')
    args = parser.parse_args()

    if args.listcandidates or args.channel is None:
        list_candidates()
        sys.exit()

    # first we deal with the first argument, channel, to figure out what it means
    if args.channel and len(args.channel) < 4:
        # here we are in the "channel index" case
        index = int(args.channel) - 1
        candidates = get_rebalance_candidates()
        candidate = candidates[index]
        remote_pubkey = candidate.remote_pubkey
    else:
        # else the channel argument should be the node's pubkey
        remote_pubkey = args.channel

    # then we figure out whether an amount was specified or if we compute it ourselves
    if args.amount:
        amount = int(args.amount)
    else:
        amount = int(math.ceil(float(get_remote_surplus(candidate)) / 2))
        if amount > MAX_SATOSHIS_PER_TRANSACTION:
            amount = MAX_SATOSHIS_PER_TRANSACTION

    response = Logic(lnd, remote_pubkey, amount).rebalance()
    if response:
        print(response)


def list_candidates():
    index = 0
    candidates = get_rebalance_candidates()
    for candidate in candidates:
        index += 1
        rebalance_amount = int(math.ceil(float(get_remote_surplus(candidate)) / 2))
        if rebalance_amount > MAX_SATOSHIS_PER_TRANSACTION:
            rebalance_amount = str(rebalance_amount) + " (max per transaction: %d)" % MAX_SATOSHIS_PER_TRANSACTION

        print("(%2d) Pubkey:      " % index + candidate.remote_pubkey)
        print("Local ratio:      " + str(get_local_ratio(candidate)))
        print("Capacity:         " + str(candidate.capacity))
        print("Remote balance:   " + str(candidate.remote_balance))
        print("Local balance:    " + str(candidate.local_balance))
        print("Amount for 50-50: " + str(rebalance_amount))
        print(get_capacity_and_ratio_bar(candidate))
        print("")
    print("")
    print("Run with two arguments: 1) pubkey of channel to fill 2) amount")


def get_rebalance_candidates():
    low_local = list(filter(lambda c: get_local_ratio(c) < 0.5, lnd.get_channels()))
    return sorted(low_local, key=get_remote_surplus, reverse=False)


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
