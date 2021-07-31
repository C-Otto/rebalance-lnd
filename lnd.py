import base64
import os
from pathlib import Path
from functools import lru_cache
from os.path import expanduser

from lndgrpc import LNDClient

MESSAGE_SIZE_MB = 50 * 1024 * 1024


class Lnd:
    def __init__(self, lnd_dir, server):
        credential_path = os.getenv("LND_CRED_PATH", None)
        if credential_path == None:
            credential_path = Path("/home/skorn/.lnd/")
            mac = str(credential_path.joinpath("data/chain/bitcoin/mainnet/admin.macaroon").absolute())
        else:
            credential_path = Path(credential_path)
            mac = str(credential_path.joinpath("admin.macaroon").absolute())
            

        node_ip = os.getenv("LND_NODE_IP","localhost")
        tls = str(credential_path.joinpath("tls.cert").absolute())

        self.lnd = LNDClient(
            f"{node_ip}:10009",
            macaroon_filepath=mac,
            cert_filepath=tls
        )

    @lru_cache(maxsize=None)
    def get_info(self):
        return self.lnd.get_info()

    @lru_cache(maxsize=None)
    def get_node_alias(self, pub_key):
        return self.lnd.get_node_info(pub_key, include_channels=False).node.alias

    def get_own_pubkey(self):
        return self.get_info().identity_pubkey

    def generate_invoice(self, memo, amount):
        return self.lnd.decode_pay_req(
            self.lnd.add_invoice(
                memo=memo,
                value=int(amount),
            ).payment_request
        )

    @lru_cache(maxsize=None)
    def get_channels(self, active_only=False):
        return self.lnd.list_channels(active_only=active_only).channels

    @lru_cache(maxsize=None)
    def get_max_channel_capacity(self):
        max_channel_capacity = 0
        for channel in self.get_channels(active_only=False):
            if channel.capacity > max_channel_capacity:
                max_channel_capacity = channel.capacity
        return max_channel_capacity

    def get_route(
        self,
        pub_key,
        amount,
        ignored_pairs,
        ignored_nodes,
        first_hop_channel_id,
        fee_limit_msat,
    ):
        if fee_limit_msat:
            fee_limit = {"fixed_msat": int(fee_limit_msat)}
        else:
            fee_limit = None
        if pub_key:
            last_hop_pubkey = base64.b16decode(pub_key, True)
        else:
            last_hop_pubkey = None
        # request = ln.QueryRoutesRequest(
        #     pub_key=self.get_own_pubkey(),
        #     last_hop_pubkey=last_hop_pubkey,
        #     amt=amount,
        #     ignored_pairs=ignored_pairs,
        #     fee_limit=fee_limit,
        #     ignored_nodes=ignored_nodes,
        #     use_mission_control=True,
        #     outgoing_chan_id=first_hop_channel_id,
        # )

        try:
            # response = self.stub.QueryRoutes(request)
            response = self.lnd.query_routes(
                pub_key=self.get_own_pubkey(),
                last_hop_pubkey=last_hop_pubkey,
                amt=amount,
                ignored_pairs=ignored_pairs,
                fee_limit=fee_limit,
                ignored_nodes=ignored_nodes,
                use_mission_control=True,
                outgoing_chan_id=first_hop_channel_id,            
            )
            return response.routes
        except:
            return None

    @lru_cache(maxsize=None)
    def get_edge(self, channel_id):
        return self.lnd.get_chan_info(channel_id)

    def get_policy_to(self, channel_id):
        edge = self.get_edge(channel_id)
        # node1_policy contains the fee base and rate for payments from node1 to node2
        if edge.node1_pub == self.get_own_pubkey():
            return edge.node1_policy
        return edge.node2_policy

    def get_policy_from(self, channel_id):
        edge = self.get_edge(channel_id)
        # node1_policy contains the fee base and rate for payments from node1 to node2
        if edge.node1_pub == self.get_own_pubkey():
            return edge.node2_policy
        return edge.node1_policy

    def get_ppm_to(self, channel_id):
        return self.get_policy_to(channel_id).fee_rate_milli_msat

    def get_ppm_from(self, channel_id):
        return self.get_policy_from(channel_id).fee_rate_milli_msat

    def send_payment(self, payment_request, route):
        last_hop = route.hops[-1]
        last_hop.mpp_record.payment_addr = payment_request.payment_addr
        last_hop.mpp_record.total_amt_msat = payment_request.num_msat
        # request = lnrouter.SendToRouteRequest(route=route)
        # request.payment_hash = self.hex_string_to_bytes(payment_request.payment_hash)

        route.hops[-1].mpp_record.total_amt_msat = payment_request.num_msat
        route.hops[-1].mpp_record.payment_addr = payment_request.payment_addr
        return self.lnd.send_to_route(
            pay_hash = bytes.fromhex(payment_request.payment_hash),
            route=route
        )
