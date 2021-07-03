import base64
import os
from os.path import expanduser
import codecs
import grpc
import sys
from functools import cache

from grpc_generated import router_pb2_grpc as lnrouterrpc, router_pb2 as lnrouter, rpc_pb2_grpc as lnrpc, rpc_pb2 as ln

MESSAGE_SIZE_MB = 50 * 1024 * 1024


def debug(message):
    sys.stderr.write(message + "\n")


class Lnd:
    def __init__(self, lnd_dir, server):
        os.environ['GRPC_SSL_CIPHER_SUITES'] = 'HIGH+ECDSA'
        lnd_dir = expanduser(lnd_dir)
        combined_credentials = self.get_credentials(lnd_dir)
        channel_options = [
            ('grpc.max_message_length', MESSAGE_SIZE_MB),
            ('grpc.max_receive_message_length', MESSAGE_SIZE_MB)
        ]
        grpc_channel = grpc.secure_channel(server, combined_credentials, channel_options)
        self.stub = lnrpc.LightningStub(grpc_channel)
        self.router_stub = lnrouterrpc.RouterStub(grpc_channel)

    @staticmethod
    def get_credentials(lnd_dir):
        tls_certificate = open(lnd_dir + '/tls.cert', 'rb').read()
        ssl_credentials = grpc.ssl_channel_credentials(tls_certificate)
        macaroon = codecs.encode(open(lnd_dir + '/data/chain/bitcoin/mainnet/admin.macaroon', 'rb').read(), 'hex')
        auth_credentials = grpc.metadata_call_credentials(lambda _, callback: callback([('macaroon', macaroon)], None))
        combined_credentials = grpc.composite_channel_credentials(ssl_credentials, auth_credentials)
        return combined_credentials

    @cache
    def get_info(self):
        return self.stub.GetInfo(ln.GetInfoRequest())

    def get_node_alias(self, pub_key):
        return self.stub.GetNodeInfo(ln.NodeInfoRequest(pub_key=pub_key, include_channels=False)).node.alias

    @cache
    def get_graph(self):
        return self.stub.DescribeGraph(ln.ChannelGraphRequest(include_unannounced=True))

    def get_own_pubkey(self):
        return self.get_info().identity_pubkey

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

    @cache
    def get_channels(self):
        return self.stub.ListChannels(ln.ListChannelsRequest(
            active_only=False,
        )).channels

    def get_route(self, pub_key, amount, ignored_pairs, ignored_nodes, first_hop_channel_id, fee_limit_sat):
        if fee_limit_sat:
            fee_limit = {"fixed": int(fee_limit_sat)}
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

    def get_policy_to(self, channel_id):
        # node1_policy contains the fee base and rate for payments from node1 to node2
        for edge in self.get_edges():
            if edge.channel_id == channel_id:
                if edge.node1_pub == self.get_own_pubkey():
                    result = edge.node1_policy
                else:
                    result = edge.node2_policy
                return result

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
