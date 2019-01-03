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
    parser = argparse.ArgumentParser()

    parser.add_argument("-d", "--debug", action="store_true", default=False, help="Verbose debug mode")
    parser.add_argument("-l", "--listcandidates", action="store_true", default=False,
                        help=("List candidate channels for rebalance."
                              "Use in conjunction with -o and -i"))
    parser.add_argument("-o", "--outgoing", action="store_true",
                        help="When used with -l, lists candidate outgoing channels")
    parser.add_argument("-i", "--incoming", action="store_true",
                        help="When used with -l, lists candidate incoming channels")
    parser.add_argument("-f", "--fromchan", help="Channel id for the outgoing channel (which will be emptied)")
    parser.add_argument("-t", "--tochan", help="Channel id for the incoming channel (which will be filled)")
    # args.amount is essentially a list, and what matters to us is the first value it *may* have
    parser.add_argument("amount", help=("Amount of the rebalance, in satoshis. If not specified, the amount computed"
                                        " for a perfect rebalance will be used (up to the maximum of"
                                        " 16,777,215 satoshis)"), nargs="?")
    args = parser.parse_args()

    debug = args.debug

    if debug:
        print("from: %s\nto: %s\namount: %s" % (args.fromchan, args.tochan, args.amount))
        print("outgoing: %s\nincoming: %s" % (args.outgoing, args.incoming))

    if (args.outgoing or args.incoming) and not args.listcandidates:
        print("--outgoing and --incoming only work in conjunction with --listcandidates")
        sys.exit()

    if args.listcandidates or (args.fromchan is None and args.tochan is None):
        if args.outgoing and args.incoming:
            debug("Only one of outgoing and incoming supported at once, defaulting to incoming.")
            incoming = True
        else:
            incoming = not args.outgoing
        list_candidates(incoming=incoming)
        sys.exit()

    # If only the outgoing channel is specified, we need to find routes to any inbound channel, so there
    # is some work to do to find all channels with incoming capacity, find routes to them, rank them etc. We could
    # also think of splitting the amount to distribute it over several incoming channels to keep them at reasonable 
    # levels. Anyway, not supported yet.
    if args.fromchan and (args.tochan is None):
        debug("Outgoing-only mode is not supported yet.")
        sys.exit()

    # first we deal with the first argument, channel, to figure out what it means
    if args.tochan and len(args.tochan) < 4:
        # here we are in the "channel index" case
        index = int(args.tochan) - 1
        candidates = get_rebalance_candidates()
        candidate = candidates[index]
        remote_pubkey = candidate.remote_pubkey
    else:
        # else the channel argument should be the node's pubkey
        remote_pubkey = args.tochan
        # candidate is a channel -- we find it by filtering through all candidates
        # TODO: add protection for when that pubkey is not found etc
        candidate = [c for c in get_rebalance_candidates() if c.remote_pubkey == remote_pubkey][0]

    # then we figure out whether an amount was specified or if we compute it ourselves
    if args.amount:
        amount = int(args.amount)
    else:
        amount = int(math.ceil(float(get_remote_surplus(candidate)) / 2))
        if amount > MAX_SATOSHIS_PER_TRANSACTION:
            amount = MAX_SATOSHIS_PER_TRANSACTION

    first_hop_pubkey = args.fromchan
    response = Logic(lnd, first_hop_pubkey, remote_pubkey, amount).rebalance()
    if response:
        print(response)


def list_candidates(incoming=True):
    index = 0
    candidates = get_rebalance_candidates(incoming=incoming)
    for candidate in candidates:
        index += 1
        rebalance_amount_int = int(math.ceil(float(get_remote_surplus(candidate)) / 2))
        rebalance_amount = "{:,}".format(rebalance_amount_int)
        if rebalance_amount_int > MAX_SATOSHIS_PER_TRANSACTION:
            rebalance_amount += " (max per transaction: {:,})".format(MAX_SATOSHIS_PER_TRANSACTION)

        print("(%2d) Pubkey:      " % index + candidate.remote_pubkey)
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
    print("get_rebalance_candidates: incoming=%s" % incoming)
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
