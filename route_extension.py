import sys

from lnd_grpc.lnd_grpc import Client
from lnd_grpc.protos.rpc_pb2 import Hop


def debug(message):
    sys.stderr.write(message + "\n")


class RouteExtension:

    def __init__(self, rpc, rebalance_channel, payment):
        self.rpc: Client = rpc
        self.rebalance_channel = rebalance_channel
        self.payment = payment
        self.info = self.rpc.get_info()
        self.graph = self.rpc.describe_graph()

    def add_rebalance_channel(self, route):
        hops = route.hops
        last_hop = hops[-1]
        amount_msat = int(last_hop.amt_to_forward_msat)

        expiry_last_hop = self.info.block_height + self.get_expiry_delta_last_hop()
        total_time_lock = expiry_last_hop

        self.update_amounts(hops)
        total_time_lock = self.update_expiry(hops, total_time_lock)

        hops.extend([self.create_new_hop(amount_msat, self.rebalance_channel, expiry_last_hop)])

        self.update_route_totals(route, total_time_lock)
        return route

    @staticmethod
    def update_route_totals(route, total_time_lock):
        total_fee_msat = 0
        for hop in route.hops:
            total_fee_msat += hop.fee_msat

        total_amount_msat = route.hops[-1].amt_to_forward_msat + total_fee_msat

        route.total_amt_msat = total_amount_msat
        route.total_amt = total_amount_msat // 1000
        route.total_fees_msat = total_fee_msat
        route.total_fees = total_fee_msat // 1000

        route.total_time_lock = total_time_lock

    def create_new_hop(self, amount_msat, channel, expiry):
        new_hop = Hop(
            chan_capacity=channel.capacity,
            fee_msat=0,
            fee=0,
            expiry=expiry,
            amt_to_forward_msat=amount_msat,
            amt_to_forward=amount_msat // 1000,
            chan_id=channel.chan_id,
            pub_key=self.info.identity_pubkey,
        )
        return new_hop

    def update_amounts(self, hops):
        additional_fees = 0
        hop_out_channel_id = self.rebalance_channel.chan_id
        for hop in reversed(hops):
            amount_to_forward_msat = hop.amt_to_forward_msat + additional_fees
            hop.amt_to_forward_msat = amount_to_forward_msat
            hop.amt_to_forward = amount_to_forward_msat // 1000

            fee_msat_before = hop.fee_msat
            new_fee_msat = self.get_fee_msat(amount_to_forward_msat, hop_out_channel_id, hop.pub_key)
            hop.fee_msat = new_fee_msat
            hop.fee = new_fee_msat // 1000
            additional_fees += new_fee_msat - fee_msat_before
            hop_out_channel_id = hop.chan_id

    def get_expiry_delta_last_hop(self):
        return self.payment.cltv_expiry

    def update_expiry(self, hops, total_time_lock):
        hop_out_channel_id = self.rebalance_channel.chan_id
        for hop in reversed(hops):
            hop.expiry = total_time_lock

            policy = self.get_policy(hop_out_channel_id, hop.pub_key)

            time_lock_delta = self.get_time_lock_delta(policy)
            total_time_lock += time_lock_delta
            hop_out_channel_id = hop.chan_id
        return total_time_lock

    def get_fee_msat(self, amount_msat, channel_id, source_pubkey):
        policy = self.get_policy(channel_id, source_pubkey)
        fee_base_msat = self.get_fee_base_msat(policy)
        fee_rate_milli_msat = self.get_fee_rate_msat(policy)
        return fee_base_msat + fee_rate_milli_msat * amount_msat // 1000000

    @staticmethod
    def get_time_lock_delta(policy):
        # sometimes that field seems not to be set -- interpret it as 0
        if hasattr(policy, "time_lock_delta"):
            return policy.time_lock_delta
        return int(0)

    @staticmethod
    def get_fee_base_msat(policy):
        # sometimes that field seems not to be set -- interpret it as 0
        if hasattr(policy, "fee_base_msat"):
            return int(policy.fee_base_msat)
        return int(0)

    @staticmethod
    def get_fee_rate_msat(policy):
        # sometimes that field seems not to be set -- interpret it as 0
        if hasattr(policy, "fee_rate_milli_msat"):
            return int(policy.fee_rate_milli_msat)
        return int(0)

    def get_policy(self, channel_id, source_pubkey):
        # node1_policy contains the fee base and rate for payments from node1 to node2
        for edge in self.graph.edges:
            if edge.channel_id == channel_id:
                if edge.node1_pub == source_pubkey:
                    result = edge.node1_policy
                else:
                    result = edge.node2_policy
                return result
