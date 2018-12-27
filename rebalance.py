#!/usr/bin/env python
import math
import os
import sys

import rpc_pb2 as ln
from lnd import Lnd


def debug(message):
    sys.stderr.write(message + "\n")


def generate_invoice(remote_pubkey):
    memo = "Rebalance of channel to " + remote_pubkey
    return lnd.generate_invoice(memo, amount)


def get_local_ratio(channel):
    remote = channel.remote_balance
    local = channel.local_balance
    return float(local) / (remote + local)


def get_remote_surplus(channel):
    return channel.remote_balance - channel.local_balance


def get_rebalance_candidates():
    low_local = list(filter(lambda c: get_local_ratio(c) < 0.5, lnd.get_channels()))
    return sorted(low_local, key=get_remote_surplus, reverse=True)


def get_routes(destination):
    num_routes = MAX_ROUTES
    pub_key = destination
    return lnd.get_routes(pub_key, amount, num_routes)


def add_channel_to_routes(routes, rebalance_channel):
    result = []
    for route in routes:
        modified_route = add_channel(route, rebalance_channel)
        if modified_route:
            result.append(modified_route)
    return result


# Returns a route if things went OK, an empty list otherwise
def add_channel(route, channel):
    global payment_request_hash
    global total_time_lock
    hops = route.hops
    if low_local_ratio_after_sending(hops):
        # debug("Ignoring route, channel is low on funds")
        return None
    if is_first_hop(hops, channel):
        # debug("Ignoring route, channel to add already is part of route")
        return None
    amount_msat = int(hops[-1].amt_to_forward_msat)

    expiry_last_hop = lnd.get_current_height() + get_expiry_delta_last_hop()
    total_time_lock = expiry_last_hop

    update_amounts(hops)
    update_expiry(hops)

    hops.extend([create_new_hop(amount_msat, channel, expiry_last_hop)])

    if update_route_totals(route):
        return route
    else:
        return None


def get_expiry_delta_last_hop():
    return lnd.get_expiry(payment_request_hash)


def get_fee_msat(amount_msat, channel_id, target_pubkey):
    policy = lnd.get_policy(channel_id, target_pubkey)
    fee_base_msat = get_fee_base_msat(policy)
    fee_rate_milli_msat = int(policy.fee_rate_milli_msat)
    return fee_base_msat + fee_rate_milli_msat * amount_msat / 1000000


def get_fee_base_msat(policy):
    # sometimes that field seems not to be set -- interpret it as 0
    if hasattr(policy, "fee_base_msat"):
        return int(policy.fee_base_msat)
    return int(0)


# Returns True only if everything went well, False otherwise
def update_route_totals(route):
    total_fee_msat = 0
    for hop in route.hops:
        total_fee_msat += hop.fee_msat
    if total_fee_msat > HIGH_FEES_THRESHOLD_MSAT:
        debug("High fees! " + str(total_fee_msat) + " msat")
        return False

    total_amount_msat = route.hops[-1].amt_to_forward_msat + total_fee_msat

    route.total_amt_msat = total_amount_msat
    route.total_amt = total_amount_msat // 1000
    route.total_fees_msat = total_fee_msat
    route.total_fees = total_fee_msat // 1000

    route.total_time_lock = total_time_lock
    return True


def create_new_hop(amount_msat, channel, expiry):
    new_hop = ln.Hop(
        chan_capacity=channel.capacity,
        fee_msat=0,
        fee=0,
        expiry=expiry,
        amt_to_forward_msat=amount_msat,
        amt_to_forward=amount_msat // 1000,
        chan_id=channel.chan_id,
        pub_key=lnd.get_own_pubkey(),
    )
    return new_hop


def update_amounts(hops):
    additional_fees = 0
    for hop in reversed(hops):
        amount_to_forward_msat = hop.amt_to_forward_msat + additional_fees
        hop.amt_to_forward_msat = amount_to_forward_msat
        hop.amt_to_forward = amount_to_forward_msat / 1000

        fee_msat_before = hop.fee_msat
        new_fee_msat = get_fee_msat(amount_to_forward_msat, hop.chan_id, hop.pub_key)
        hop.fee_msat = new_fee_msat
        hop.fee = new_fee_msat / 1000
        additional_fees += new_fee_msat - fee_msat_before


def update_expiry(hops):
    global total_time_lock
    for hop in reversed(hops):
        hop.expiry = total_time_lock

        channel_id = hop.chan_id
        target_pubkey = hop.pub_key
        policy = lnd.get_policy(channel_id, target_pubkey)

        time_lock_delta = policy.time_lock_delta
        total_time_lock += time_lock_delta


def is_first_hop(hops, channel):
    return hops[0].pub_key == channel.remote_pubkey


def low_local_ratio_after_sending(hops):
    pub_key = hops[0].pub_key
    channel = get_channel(pub_key)

    remote = channel.remote_balance + amount
    local = channel.local_balance - amount
    ratio = float(local) / (remote + local)
    return ratio < 0.5


def get_channel(pubkey):
    for channel in lnd.get_channels():
        if channel.remote_pubkey == pubkey:
            return channel


def get_capacity_and_ratio_bar(candidate):
    columns = get_columns()
    max_channel_capacity = 16777215
    columns_scaled_to_capacity = int(round(columns * float(candidate.capacity) / max_channel_capacity))

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


def list_candidates():
    candidates = get_rebalance_candidates()
    for candidate in reversed(candidates):
        rebalance_amount = int(math.ceil(float(get_remote_surplus(candidate)) / 2))
        if rebalance_amount > 4294967:
            rebalance_amount = str(rebalance_amount) + " (max per transaction: 4294967)"

        print("Pubkey:           " + candidate.remote_pubkey)
        print("Local ratio:      " + str(get_local_ratio(candidate)))
        print("Capacity:         " + str(candidate.capacity))
        print("Remote balance:   " + str(candidate.remote_balance))
        print("Local balance:    " + str(candidate.local_balance))
        print("Amount for 50-50: " + str(rebalance_amount))
        print(get_capacity_and_ratio_bar(candidate))
        print("")
    print("")
    print("Run with two arguments: 1) pubkey of channel to fill 2) amount")


def rebalance(routes):
    response = lnd.send_payment(payment_request_hash, routes)
    is_successful = response.payment_error == ""

    if is_successful:
        fees_msat = response.payment_route.total_fees_msat
        fees = round(float(fees_msat) / 1000.0, 3)
        debug("Success! Paid fees: " + str(fees) + " Satoshi")
    elif "TemporaryChannelFailure" in response.payment_error:
        debug("TemporaryChannelFailure (not enough funds along the route?)")
    else:
        debug("Error: " + response.payment_error)
    print(response)


def main():
    if len(sys.argv) != 3:
        list_candidates()
        sys.exit()

    global amount
    amount = int(sys.argv[2])

    remote_pubkey = sys.argv[1]
    rebalance_channel = get_channel(remote_pubkey)

    debug("Sending " + str(amount) + " satoshis to rebalance, remote pubkey: " + remote_pubkey)

    routes = get_routes(remote_pubkey)

    global payment_request_hash
    payment_request_hash = generate_invoice(remote_pubkey)

    modified_routes = add_channel_to_routes(routes, rebalance_channel)
    if len(modified_routes) == 0:
        debug("Could not find any suitable route")
        return
    debug("Constructed " + str(len(modified_routes)) + " routes to try")

    rebalance(modified_routes)


HIGH_FEES_THRESHOLD_MSAT = 3000000
MAX_ROUTES = 30

total_time_lock = 0
amount = 10000
payment_request_hash = None

lnd = Lnd()
main()
