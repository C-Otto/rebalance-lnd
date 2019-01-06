import sys
from routes import Routes

HIGH_FEES_THRESHOLD_MSAT = 3000000


def debug(message):
    sys.stderr.write(message + "\n")


class Logic:
    def __init__(self, lnd, first_hop_channel_id, last_hop_channel, amount):
        self.lnd = lnd
        self.first_hop_channel_id = first_hop_channel_id
        self.last_hop_channel = last_hop_channel
        self.amount = amount

    def rebalance(self):
        debug(("Sending {:,} satoshis to rebalance to channel with ID %d"
               % self.last_hop_channel.chan_id).format(self.amount))
        if self.first_hop_channel_id:
            debug("Forced first channel has ID %d" % self.first_hop_channel_id)

        payment_request = self.generate_invoice()
        routes = Routes(self.lnd, payment_request, self.first_hop_channel_id, self.last_hop_channel)

        if not routes.has_next():
            debug("Could not find any suitable route")
            return None

        tried_routes = []
        while routes.has_next():
            route = routes.get_next()
            if self.route_is_invalid(route):
                continue
            tried_routes.append(route)

            debug("Trying route #%d" % len(tried_routes))
            debug(Routes.print_route(route))

            response = self.lnd.send_payment(payment_request, [route])
            is_successful = response.payment_error == ""

            if is_successful:
                fees_msat = response.payment_route.total_fees_msat
                fees_satoshi = round(float(fees_msat) / 1000.0, 3)
                debug("Success! Paid %d Satoshi in fees" % fees_satoshi)
                debug("Tried routes:")
                debug("\n".join(Routes.print_route(route) for route in tried_routes))
                debug("Successful route:")
                debug(Routes.print_route(route))

                return response
            elif "TemporaryChannelFailure" in response.payment_error:
                debug("TemporaryChannelFailure (not enough funds along the route?)")
            else:
                debug("Error: %s" % response.payment_error)
        return None

    def route_is_invalid(self, route):
        first_hop = route.hops[0]
        if self.does_not_have_requested_first_hop(first_hop):
            return True
        if self.low_local_ratio_after_sending(first_hop, route.total_amt_msat):
            return True
        if self.target_is_first_hop(first_hop):
            return True
        if route.total_fees_msat > HIGH_FEES_THRESHOLD_MSAT:
            return True
        return False

    def low_local_ratio_after_sending(self, first_hop, total_amount_msat):
        channel_id = first_hop.chan_id
        channel = self.get_channel_for_channel_id(channel_id)

        amount = total_amount_msat // 1000
        debug("amount: %d" % amount)
        debug("before local: %d" % channel.local_balance)
        debug("before remote: %d" % channel.remote_balance)
        remote = channel.remote_balance + amount
        local = channel.local_balance - amount
        ratio = float(local) / (remote + local)
        debug("after ratio: %f" % ratio)
        return ratio < 0.5

    def target_is_first_hop(self, first_hop):
        return first_hop.chan_id == self.last_hop_channel.chan_id

    def does_not_have_requested_first_hop(self, first_hop):
        if not self.first_hop_channel_id:
            return False
        return first_hop.chan_id != self.first_hop_channel_id

    def generate_invoice(self):
        memo = "Rebalance of channel with ID %d" % self.last_hop_channel.chan_id
        return self.lnd.generate_invoice(memo, self.amount)

    def get_channel_for_channel_id(self, channel_id):
        for channel in self.lnd.get_channels():
            if channel.chan_id == channel_id:
                return channel
