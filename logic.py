import base64
import sys

from routes import Routes

DEFAULT_BASE_FEE = 1000
DEFAULT_FEE_RATE = 1
A_MILLION = 1000000


def debug(message):
    sys.stderr.write(message + "\n")


def debugnobreak(message):
    sys.stderr.write(message)


class Logic:
    def __init__(self, lnd, first_hop_channel_id, last_hop_channel, amount, channel_ratio, excluded, max_fee_factor):
        self.lnd = lnd
        self.first_hop_channel_id = first_hop_channel_id
        self.last_hop_channel = last_hop_channel
        self.amount = amount
        self.channel_ratio = channel_ratio
        self.excluded = []
        if excluded:
            self.excluded = excluded
        self.max_fee_factor = max_fee_factor

    def rebalance(self):
        debug(("Sending {:,} satoshis to rebalance to channel with ID %d"
               % self.last_hop_channel.chan_id).format(self.amount))
        if self.channel_ratio != 0.5:
            debug("Channel ratio used is %d%%" % int(self.channel_ratio * 100))
        if self.first_hop_channel_id:
            debug("Forced first channel has ID %d" % self.first_hop_channel_id)

        payment_request = self.generate_invoice()
        routes = Routes(self.lnd, payment_request, self.first_hop_channel_id, self.last_hop_channel)

        self.initialize_ignored_channels(routes)

        tried_routes = []
        while routes.has_next():
            route = routes.get_next()
            if self.route_is_invalid(route, routes):
                continue
            tried_routes.append(route)

            debug("")
            debug("Trying route #%d" % len(tried_routes))
            debug(Routes.print_route(route))

            response = self.lnd.send_payment(payment_request, route)
            is_successful = response.failure.code == 0

            if is_successful:
                debug("Success! Paid fees: %s sat (%s msat)" % (route.total_fees, route.total_fees_msat))
                debug("Successful route:")
                debug(Routes.print_route(route))
                debug("")
                debug("Tried routes:")
                debug("\n".join(Routes.print_route(route) for route in tried_routes))
                return
            else:
                code = response.failure.code
                failure_source_pubkey = self.bytes_to_hex_string(response.failure.failure_source_pubkey)
                if code == 15:
                    debugnobreak("Temporary channel failure, ")
                    routes.ignore_edge_on_route(failure_source_pubkey, route)
                elif code == 18:
                    debugnobreak("Unknown next peer, ")
                    routes.ignore_edge_on_route(failure_source_pubkey, route)
                elif code == 12:
                    debugnobreak("Fee insufficient, ")
                    routes.ignore_edge_on_route(failure_source_pubkey, route)
                else:
                    debug(repr(response))
                    debug("Unknown error code %s" % repr(code))
        debug("Could not find any suitable route")
        return None

    def route_is_invalid(self, route, routes):
        first_hop = route.hops[0]
        if self.does_not_have_requested_first_hop(first_hop):
            debug("does not have requested first hop")
            routes.ignore_first_hop(self.get_channel_for_channel_id(first_hop.chan_id))
            return True
        if self.low_local_ratio_after_sending(first_hop, route.total_amt):
            debug("Low local ratio after sending, ignoring %s" % first_hop.chan_id)
            routes.ignore_first_hop(self.get_channel_for_channel_id(first_hop.chan_id))
            return True
        if self.target_is_first_hop(first_hop):
            debug("Ignoring %s as first hop")
            routes.ignore_first_hop(self.get_channel_for_channel_id(first_hop.chan_id))
            return True
        if self.fees_too_high(route):
            return True
        return False

    def does_not_have_requested_first_hop(self, first_hop):
        if not self.first_hop_channel_id:
            return False
        return first_hop.chan_id != self.first_hop_channel_id

    def low_local_ratio_after_sending(self, first_hop, total_amount):
        if self.first_hop_channel_id:
            # Just use the computed/specified amount to drain the first hop, ignoring fees
            return False
        channel_id = first_hop.chan_id
        channel = self.get_channel_for_channel_id(channel_id)

        remote = channel.remote_balance + total_amount
        local = channel.local_balance - total_amount
        ratio = float(local) / (remote + local)
        return ratio < self.channel_ratio

    def target_is_first_hop(self, first_hop):
        return first_hop.chan_id == self.last_hop_channel.chan_id

    def fees_too_high(self, route):
        hops_with_fees = len(route.hops) - 1
        lnd_fees = hops_with_fees * (DEFAULT_BASE_FEE + (self.amount * DEFAULT_FEE_RATE / A_MILLION))
        limit = self.max_fee_factor * lnd_fees
        too_high = route.total_fees_msat > limit
        if too_high:
            debug("Skipping route due to high fees (%d msat): %s" % (route.total_fees_msat, Routes.print_route(route)))
        return too_high

    def generate_invoice(self):
        memo = "Rebalance of channel with ID %d" % self.last_hop_channel.chan_id
        return self.lnd.generate_invoice(memo, self.amount)

    def get_channel_for_channel_id(self, channel_id):
        for channel in self.lnd.get_channels():
            if channel.chan_id == channel_id:
                return channel

    def initialize_ignored_channels(self, routes):
        for channel in self.lnd.get_channels():
            if self.low_local_ratio_after_sending(channel, self.amount):
                routes.ignore_first_hop(channel)
            if channel.chan_id in self.excluded:
                debug("Ignoring %s as first hop" % channel.chan_id)
                routes.ignore_first_hop(channel)

    @staticmethod
    def bytes_to_hex_string(data):
        return base64.b16encode(data).lower()
