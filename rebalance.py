#!/usr/bin/env python
import codecs
import grpc
import json
import math
import os
from subprocess import check_output
import sys

import rpc_pb2 as ln, rpc_pb2_grpc as lnrpc

HIGH_FEES_THRESHOLD_MSAT = 3000000
LND_DIR = "/home/wamde/.lnd/"
macaroon = codecs.encode(open(LND_DIR + 'data/chain/bitcoin/mainnet/admin.macaroon', 'rb').read(), 'hex')
os.environ['GRPC_SSL_CIPHER_SUITES'] = 'HIGH+ECDSA'
cert = open(LND_DIR + 'tls.cert', 'rb').read()
ssl_creds = grpc.ssl_channel_credentials(cert)
channel = grpc.secure_channel('localhost:10009', ssl_creds)
stub = lnrpc.LightningStub(channel)


def debug(message):
    sys.stderr.write(message + "\n")


def get_own_pubkey():
    response = stub.GetInfo(ln.GetInfoRequest(), metadata=[('macaroon', macaroon)])
    return response.identity_pubkey


def get_current_height():
    response = stub.GetInfo(ln.GetInfoRequest(), metadata=[('macaroon', macaroon)])
    return response.block_height


def get_edges():
    response = stub.DescribeGraph(ln.ChannelGraphRequest(), metadata=[('macaroon', macaroon)])
    return response.edges


def generate_invoice(remote_pubkey):
    request = ln.Invoice(
        memo="Rebalance of channel to " + remote_pubkey,
        amt_paid_sat=amount,
    )
    response = stub.AddInvoice(request, metadata=[('macaroon', macaroon)])

    request = ln.PayReqString(
        pay_req=response.payment_request,
    )
    response = stub.DecodePayReq(request, metadata=[('macaroon', macaroon)])
    return response.payment_hash


def get_channels():
    request = ln.ListChannelsRequest(
        active_only=True,
    )
    response = stub.ListChannels(request, metadata=[('macaroon', macaroon)])
    return response.channels


own_pubkey = get_own_pubkey()
current_height = get_current_height()
max_routes = 30
total_time_lock = 0
amount = 10000
channels = get_channels()
edges = get_edges()
payment_request_hash = None


def get_local_ratio(channel):
    remote = channel.remote_balance
    local = channel.local_balance
    return float(local) / (remote + local)


def get_capacity(channel):
    return channel.capacity


def get_remote_surplus(channel):
    return channel.remote_balance - channel.local_balance


def get_rebalance_candidates():
    low_local = list(filter(lambda c: get_local_ratio(c) < 0.5, channels))
    return sorted(low_local, key=get_remote_surplus, reverse=True)


def get_routes(destination):
    request = ln.QueryRoutesRequest(
        pub_key=destination,
        amt=amount,
        num_routes=max_routes,
    )
    response = stub.QueryRoutes(request, metadata=[('macaroon', macaroon)])
    return response.routes


def add_channel_to_routes(routes, rebalance_channel):
    result = []
    for route in routes:
        modified_route = add_channel(route, rebalance_channel)
        if modified_route:
            result.append(modified_route)
    return result


def get_policy(channel_id, target_pubkey):
    for edge in edges:
        if edge.channel_id == channel_id:
            if edge.node1_pub == target_pubkey:
                result = edge.node1_policy
            else:
                result = edge.node2_policy
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

    expiry_last_hop = current_height + get_expiry_delta_last_hop()
    total_time_lock = expiry_last_hop

    update_amounts(hops)
    update_expiry(hops)

    hops.extend([create_new_hop(amount_msat, channel, expiry_last_hop)])

    if update_route_totals(route):
        return route
    else:
        return None


def get_expiry_delta_last_hop():
    request = ln.PaymentHash(
        r_hash_str=payment_request_hash,
    )
    response = stub.LookupInvoice(request, metadata=[('macaroon', macaroon)])
    return response.cltv_expiry


def get_fee_msat(amount_msat, channel_id, target_pubkey):
    policy = get_policy(channel_id, target_pubkey)
    # sometimes that field seems not to be set -- interpret it as 0
    if hasattr(policy, "fee_base_msat"):
        fee_base_msat = int(policy.fee_base_msat)
    else:
        fee_base_msat = int(0)
    fee_rate_milli_msat = int(policy.fee_rate_milli_msat)
    result = fee_base_msat + fee_rate_milli_msat * amount_msat / 1000000
    return result

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
        pub_key=own_pubkey,
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
        policy = get_policy(channel_id, target_pubkey)

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
    for channel in channels:
        if channel.remote_pubkey == pubkey:
            return channel


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
    request = ln.SendToRouteRequest()

    request.payment_hash_string = payment_request_hash
    request.routes.extend(routes)

    response = stub.SendToRouteSync(request, metadata=[('macaroon', macaroon)])

    if response.payment_error == "":
        fees_msat = response.payment_route.total_fees_msat
        fees = round(float(fees_msat) / 1000.0, 3)
        debug("Success! Paid fees: " + str(fees) + " Satoshi")
    elif "TemporaryChannelFailure" in response.payment_error:
        debug("TemporaryChannelFailure (not enough funds along the route?)")
    else:
        debug("Error: " + response.payment_error)
    print response


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

    rebalance(modified_routes)



main()
