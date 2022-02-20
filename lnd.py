import base64
import codecs
import os
from functools import lru_cache
from os.path import expanduser

import grpc

from grpc_generated import router_pb2 as lnrouter
from grpc_generated import router_pb2_grpc as lnrouterrpc
from grpc_generated import lightning_pb2 as ln
from grpc_generated import lightning_pb2_grpc as lnrpc
from grpc_generated import invoices_pb2 as invoices
from grpc_generated import invoices_pb2_grpc as invoicesrpc

MESSAGE_SIZE_MB = 50 * 1024 * 1024


class Lnd:
    def __init__(self, macaroon_hex, tls_cert, server):
        os.environ["GRPC_SSL_CIPHER_SUITES"] = "HIGH+ECDSA"
        
        combined_credentials = self.get_credentials(macaroon_hex, tls_cert)
        channel_options = [
            ("grpc.max_message_length", MESSAGE_SIZE_MB),
            ("grpc.max_receive_message_length", MESSAGE_SIZE_MB),
        ]
        grpc_channel = grpc.secure_channel(
            server, combined_credentials, channel_options
        )
        self.stub = lnrpc.LightningStub(grpc_channel)
        self.router_stub = lnrouterrpc.RouterStub(grpc_channel)
        self.invoices_stub = invoicesrpc.InvoicesStub(grpc_channel)

    @staticmethod
    def get_credentials(macaroon, tls_certificate):
        ssl_credentials = grpc.ssl_channel_credentials(base64.b64decode(tls_certificate))
        auth_credentials = grpc.metadata_call_credentials(
            lambda _, callback: callback([("macaroon", macaroon)], None)
        )
        combined_credentials = grpc.composite_channel_credentials(
            ssl_credentials, auth_credentials
        )
        return combined_credentials

    @lru_cache(maxsize=None)
    def get_info(self):
        return self.stub.GetInfo(ln.GetInfoRequest())

    @lru_cache(maxsize=None)
    def get_node_alias(self, pub_key):
        return self.stub.GetNodeInfo(
            ln.NodeInfoRequest(pub_key=pub_key, include_channels=False)
        ).node.alias

    def get_own_pubkey(self):
        return self.get_info().identity_pubkey

    def generate_invoice(self, memo, amount):
        invoice_request = ln.Invoice(
            memo=memo,
            value=amount,
        )
        add_invoice_response = self.stub.AddInvoice(invoice_request)
        return self.decode_payment_request(add_invoice_response.payment_request)

    def cancel_invoice(self, payment_hash):
        payment_hash_bytes = self.hex_string_to_bytes(payment_hash)
        return self.invoices_stub.CancelInvoice(invoices.CancelInvoiceMsg(payment_hash=payment_hash_bytes))

    def decode_payment_request(self, payment_request):
        request = ln.PayReqString(
            pay_req=payment_request,
        )
        return self.stub.DecodePayReq(request)

    @lru_cache(maxsize=None)
    def get_channels(self, active_only=False):
        return self.stub.ListChannels(
            ln.ListChannelsRequest(
                active_only=active_only,
            )
        ).channels

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
        request = ln.QueryRoutesRequest(
            pub_key=self.get_own_pubkey(),
            last_hop_pubkey=last_hop_pubkey,
            amt=amount,
            ignored_pairs=ignored_pairs,
            fee_limit=fee_limit,
            ignored_nodes=ignored_nodes,
            use_mission_control=True,
            outgoing_chan_id=first_hop_channel_id,
        )
        try:
            response = self.stub.QueryRoutes(request)
            return response.routes
        except:
            return None

    @lru_cache(maxsize=None)
    def get_edge(self, channel_id):
        try:
            return self.stub.GetChanInfo(ln.ChanInfoRequest(chan_id=channel_id))
        except Exception:
            print(f"Unable to find channel edge {channel_id}")
            raise

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
        request = lnrouter.SendToRouteRequest(route=route)
        request.payment_hash = self.hex_string_to_bytes(payment_request.payment_hash)
        return self.router_stub.SendToRoute(request)

    @staticmethod
    def hex_string_to_bytes(hex_string):
        decode_hex = codecs.getdecoder("hex_codec")
        return decode_hex(hex_string)[0]
