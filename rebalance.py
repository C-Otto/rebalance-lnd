#!/usr/bin/env python
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

    if len(sys.argv) == 1:
        list_candidates()
        sys.exit()

    if len(sys.argv) == 2:
        index = int(sys.argv[1]) - 1
        candidates = get_rebalance_candidates()
        candidate = candidates[index]
        remote_pubkey = candidate.remote_pubkey
        amount = int(math.ceil(float(get_remote_surplus(candidate)) / 2))
        if amount > MAX_SATOSHIS_PER_TRANSACTION:
            amount = MAX_SATOSHIS_PER_TRANSACTION

    if len(sys.argv) == 3:
        remote_pubkey = sys.argv[1]
        amount = int(sys.argv[2])

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
