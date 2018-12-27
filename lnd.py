import os
from os.path import expanduser
import codecs
import grpc

import rpc_pb2 as ln
import rpc_pb2_grpc as lnrpc

SERVER = 'localhost:10009'
LND_DIR = expanduser("~/.lnd")
MESSAGE_SIZE_MB = 50 * 1024 * 1024


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
        self.graph = None

    @staticmethod
    def get_credentials(lnd_dir):
        tls_certificate = open(lnd_dir + '/tls.cert', 'rb').read()
        ssl_credentials = grpc.ssl_channel_credentials(tls_certificate)
        macaroon = codecs.encode(open(lnd_dir + '/data/chain/bitcoin/mainnet/admin.macaroon', 'rb').read(), 'hex')
        auth_credentials = grpc.metadata_call_credentials(lambda _, callback: callback([('macaroon', macaroon)], None))
        combined_credentials = grpc.composite_channel_credentials(ssl_credentials, auth_credentials)
        return combined_credentials

    def get_info(self):
        return self.stub.GetInfo(ln.GetInfoRequest())

    def get_graph(self):
        if self.graph is None:
            self.graph = self.stub.DescribeGraph(ln.ChannelGraphRequest())
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
            amt_paid_sat=amount,
        )
        invoice = self.stub.AddInvoice(invoice_request)
        return self.get_payment_hash(invoice)

    def get_payment_hash(self, invoice):
        request = ln.PayReqString(
            pay_req=invoice.payment_request,
        )
        return self.stub.DecodePayReq(request).payment_hash

    def get_channels(self):
        request = ln.ListChannelsRequest(
            active_only=True,
        )
        return self.stub.ListChannels(request).channels

    def get_routes(self, pub_key, amount, num_routes):
        request = ln.QueryRoutesRequest(
            pub_key=pub_key,
            amt=amount,
            num_routes=num_routes,
        )
        response = self.stub.QueryRoutes(request)
        return response.routes

    def get_policy(self, channel_id, target_pubkey):
        for edge in self.get_edges():
            if edge.channel_id == channel_id:
                if edge.node1_pub == target_pubkey:
                    result = edge.node1_policy
                else:
                    result = edge.node2_policy
                return result

    def get_expiry(self, payment_request_hash):
        request = ln.PaymentHash(
            r_hash_str=payment_request_hash,
        )
        return self.stub.LookupInvoice(request).cltv_expiry

    def send_payment(self, payment_request_hash, routes):
        request = ln.SendToRouteRequest()

        request.payment_hash_string = payment_request_hash
        request.routes.extend(routes)

        return self.stub.SendToRouteSync(request)
