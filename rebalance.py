#!/usr/bin/env python
import json
import sys
import os
import math
from subprocess import check_output


def debug(message):
    sys.stderr.write(message + "\n")


def lncli(*arguments):
    # debug(str(arguments))
    result = check_output(["lncli"] + list(arguments))
    return json.loads(result)


def get_own_pubkey():
    return lncli("getinfo")["identity_pubkey"]


def get_current_height():
    return int(lncli("getinfo")["block_height"])


def get_edges():
    return lncli("describegraph")["edges"]


def generate_invoice(remote_pubkey):
    return lncli("addinvoice", "--memo", "Rebalance of channel to " + remote_pubkey, "--amt", str(amount))["r_hash"]


def get_channels():
    return lncli("listchannels", "--active_only")["channels"]


own_pubkey = get_own_pubkey()
current_height = get_current_height()
max_routes = 30
total_time_lock = 0
amount = 10000
channels = get_channels()
edges = get_edges()
payment_request_hash = None


def get_local_ratio(channel):
    remote = int(channel["remote_balance"])
    local = int(channel["local_balance"])
    return float(local) / (remote + local)


def get_capacity(channel):
    return int(channel["capacity"])


def get_remote_surplus(channel):
    return int(channel["remote_balance"]) - int(channel["local_balance"])


def get_rebalance_candidates():
    low_local = list(filter(lambda c: get_local_ratio(c) < 0.5, channels))
    return sorted(low_local, key=get_remote_surplus, reverse=True)


def get_routes(destination):
    return lncli("queryroutes", "--dest", destination, "--amt", str(amount), "--num_max_routes", str(max_routes))[
        "routes"]


def add_channel_to_routes(routes, rebalance_channel):
    result = []
    for route in routes:
        # print("Before:")
        # print(json.dumps(route))
        modified_route = add_channel(route, rebalance_channel)
        if len(modified_route) > 0:
            # print("After:")
            # print(json.dumps(modified_route))
            result.append(modified_route)
    return result


def get_policy(channel_id, target_pubkey):
    for edge in edges:
        if edge["channel_id"] == channel_id:
            if edge["node1_pub"] == target_pubkey:
                result = edge["node1_policy"]
            else:
                result = edge["node2_policy"]
            return result


def add_channel(route, channel):
    global payment_request_hash
    global total_time_lock
    hops = route["hops"]
    if low_local_ratio_after_sending(hops):
        # debug("Ignoring route, channel is low on funds")
        return []
    if is_first_hop(hops, channel):
        # debug("Ignoring route, channel to add already is part of route")
        return []
    amount_msat = int(hops[-1]["amt_to_forward_msat"])

    expiry_last_hop = current_height + get_expiry_delta_last_hop()
    total_time_lock = expiry_last_hop

    update_amounts(hops)
    update_expiry(hops)

    hops.append(create_new_hop(amount_msat, channel, expiry_last_hop))

    update_route_totals(route)
    return route


def get_expiry_delta_last_hop():
    return int(lncli("lookupinvoice", payment_request_hash)["cltv_expiry"])


def get_fee_msat(amount_msat, channel_id, target_pubkey):
    policy = get_policy(channel_id, target_pubkey)
    fee_base_msat = int(policy["fee_base_msat"])
    fee_rate_milli_msat = int(policy["fee_rate_milli_msat"])
    result = fee_base_msat + fee_rate_milli_msat * amount_msat / 1000000
    return result


def update_route_totals(route):
    total_fee_msat = 0
    for hop in route["hops"]:
        total_fee_msat += int(hop["fee_msat"])
    if total_fee_msat > 3000000:
        debug("High fees! " + str(total_fee_msat))
        sys.exit()

    total_amount_msat = route["hops"][-1]["amt_to_forward_msat"] + total_fee_msat

    route["total_amt_msat"] = total_amount_msat
    route["total_amt"] = total_amount_msat // 1000
    route["total_fees_msat"] = total_fee_msat
    route["total_fees"] = total_fee_msat // 1000

    route["total_time_lock"] = total_time_lock


def create_new_hop(amount_msat, channel, expiry):
    return {"chan_capacity": channel["capacity"],
            "fee_msat": 0,
            "fee": 0,
            "expiry": expiry,
            "amt_to_forward_msat": amount_msat,
            "amt_to_forward": amount_msat // 1000,
            "chan_id": channel["chan_id"],
            "pub_key": own_pubkey}


def update_amounts(hops):
    additional_fees = 0
    for hop in reversed(hops):
        amount_to_forward_msat = int(hop["amt_to_forward_msat"]) + additional_fees
        hop["amt_to_forward_msat"] = amount_to_forward_msat
        hop["amt_to_forward"] = amount_to_forward_msat / 1000

        fee_msat_before = int(hop["fee_msat"])
        new_fee_msat = get_fee_msat(amount_to_forward_msat, hop["chan_id"], hop["pub_key"])
        hop["fee_msat"] = new_fee_msat
        hop["fee"] = new_fee_msat / 1000
        additional_fees += new_fee_msat - fee_msat_before


def update_expiry(hops):
    global total_time_lock
    for hop in reversed(hops):
        hop["expiry"] = total_time_lock

        channel_id = hop["chan_id"]
        target_pubkey = hop["pub_key"]
        policy = get_policy(channel_id, target_pubkey)

        time_lock_delta = policy["time_lock_delta"]
        total_time_lock += time_lock_delta


def is_first_hop(hops, channel):
    return hops[0]["pub_key"] == channel["remote_pubkey"]


def low_local_ratio_after_sending(hops):
    pub_key = hops[0]["pub_key"]
    channel = get_channel(pub_key)

    remote = int(channel["remote_balance"]) + amount
    local = int(channel["local_balance"]) - amount
    ratio = float(local) / (remote + local)
    return ratio < 0.5


def get_channel(pubkey):
    for channel in channels:
        if channel["remote_pubkey"] == pubkey:
            return channel


def main():
    if len(sys.argv) != 3:
        list_candidates()
        sys.exit()

    global amount
    amount = int(sys.argv[2])

    global payment_request_hash
    remote_pubkey = sys.argv[1]
    rebalance_channel = get_channel(remote_pubkey)

    debug("Sending " + str(amount) + " satoshis to rebalance, remote pubkey: " + remote_pubkey)

    routes = get_routes(remote_pubkey)

    payment_request_hash = generate_invoice(remote_pubkey)
    modified_routes = add_channel_to_routes(routes, rebalance_channel)
    if len(modified_routes) == 0:
        debug("Could not find any suitable route")
        return
    debug("Constructed " + str(len(modified_routes)) + " routes to try")

    routes_json = json.dumps({"routes": modified_routes})
    rebalance(routes_json)


def get_capacity_and_ratio_bar(candidate):
    columns = get_columns()
    max_channel_capacity = 16777215
    columns_scaled_to_capacity = int(round(columns * float(get_capacity(candidate)) / max_channel_capacity))

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

        print("Pubkey:           " + candidate["remote_pubkey"])
        print("Local ratio:      " + str(get_local_ratio(candidate)))
        print("Capacity:         " + candidate["capacity"])
        print("Remote balance:   " + candidate["remote_balance"])
        print("Local balance:    " + candidate["local_balance"])
        print("Amount for 50-50: " + str(rebalance_amount))
        print(get_capacity_and_ratio_bar(candidate))
        print("")
    print("")
    print("Run with two arguments: 1) pubkey of channel to fill 2) amount")


def rebalance(routes_json):
    result = lncli("sendtoroute", "--pay_hash", payment_request_hash, "--routes", routes_json)
    if result["payment_error"] == "":
        fees_msat = result["payment_route"]["total_fees_msat"]
        fees = round(float(fees_msat) / 1000.0, 3)
        debug("Success! Paid fees: " + str(fees) + " Satoshi")
    elif "TemporaryChannelFailure" in result["payment_error"]:
        debug("TemporaryChannelFailure (not enough funds along the route?)")
    else:
        debug("Error: " + result["payment_error"])
    print(json.dumps(result))


main()
