import os
from os.path import expanduser
import codecs
import grpc
import sys

import rpc_pb2 as ln
import rpc_pb2_grpc as lnrpc
import router_pb2 as lnrouter
import router_pb2_grpc as lnrouterrpc

SERVER = 'localhost:10009'
LND_DIR = expanduser("~/.lnd")
MESSAGE_SIZE_MB = 50 * 1024 * 1024


def debug(message):
    sys.stderr.write(message + "\n")


class Lnd:
    def __init__(self):
        os.environ['GRPC_SSL_CIPHER_SUITES'] = 'HIGH+ECDSA'
        combined_credentials = self.get_credentials(LND_DIR)
        channel_options = [
            ('grpc.max_message_length', MESSAGE_SIZE_MB),
            ('grpc.max_receive_message_length', MESSAGE_SIZE_MB)
        ]
        grpc_channel = grpc.secure_channel(SERVER, combined_credentials, channel_options)
        self.stub = lnrpc.LightningStub(grpc_channel)
        self.router_stub = lnrouterrpc.RouterStub(grpc_channel)
        self.graph = None
        self.info = None
        self.channels = None

    @staticmethod
    def get_credentials(lnd_dir):
        tls_certificate = open(lnd_dir + '/tls.cert', 'rb').read()
        ssl_credentials = grpc.ssl_channel_credentials(tls_certificate)
        macaroon = codecs.encode(open(lnd_dir + '/data/chain/bitcoin/mainnet/admin.macaroon', 'rb').read(), 'hex')
        auth_credentials = grpc.metadata_call_credentials(lambda _, callback: callback([('macaroon', macaroon)], None))
        combined_credentials = grpc.composite_channel_credentials(ssl_credentials, auth_credentials)
        return combined_credentials

    def get_info(self):
        if self.info is None:
            self.info = self.stub.GetInfo(ln.GetInfoRequest())
        return self.info

    def get_graph(self):
        if self.graph is None:
            self.graph = self.stub.DescribeGraph(ln.ChannelGraphRequest(include_unannounced=True))
        return self.graph

    def get_own_pubkey(self):
        return self.get_info().identity_pubkey

    def get_current_height(self):
        return self.get_info().block_height

    def get_edges(self):
        return self.get_graph().edges

    def generate_invoice(self, memo, amount):
        invoice_request = ln.Invoice(
            memo=memo,
            value=amount,
        )
        add_invoice_response = self.stub.AddInvoice(invoice_request)
        return self.decode_payment_request(add_invoice_response.payment_request)

    def decode_payment_request(self, payment_request):
        request = ln.PayReqString(
            pay_req=payment_request,
        )
        return self.stub.DecodePayReq(request)

    def get_channels(self):
        if self.channels is None:
            request = ln.ListChannelsRequest(
                active_only=True,
            )
            self.channels = self.stub.ListChannels(request).channels
        return self.channels

    def get_route(self, pub_key, amount, ignored_edges):
        request = ln.QueryRoutesRequest(
            pub_key=pub_key,
            amt=amount,
            ignored_edges=ignored_edges,
        )
        try:
            response = self.stub.QueryRoutes(request)
            return response.routes
        except:
            return None

    def get_policy(self, channel_id, source_pubkey):
        # node1_policy contains the fee base and rate for payments from node1 to node2
        for edge in self.get_edges():
            if edge.channel_id == channel_id:
                if edge.node1_pub == source_pubkey:
                    result = edge.node1_policy
                else:
                    result = edge.node2_policy
                return result

    def send_payment(self, payment_request, route):
        request = lnrouter.SendToRouteRequest(route=route)
        request.payment_hash = self.hex_string_to_bytes(payment_request.payment_hash)
        return self.router_stub.SendToRoute(request)

    @staticmethod
    def hex_string_to_bytes(hex_string):
        return hex_string.decode("hex")
