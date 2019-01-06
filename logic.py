import sys
from routes import Routes


def debug(message):
    sys.stderr.write(message + "\n")


class Logic:
    def __init__(self, lnd, first_hop_channel_id, last_hop_channel_id, amount):
        self.lnd = lnd
        self.first_hop_channel_id = first_hop_channel_id
        self.last_hop_channel_id = last_hop_channel_id
        self.amount = amount

    def rebalance(self):
        debug(("Sending {:,} satoshis to rebalance to channel with ID %d" % self.last_hop_channel_id).format(self.amount))
        if self.first_hop_channel_id:
            debug("Forced first channel has ID %d" % self.first_hop_channel_id)

        payment_request = self.generate_invoice()
        routes = Routes(self.lnd, payment_request, self.first_hop_channel_id, self.last_hop_channel_id)

        if not routes.has_next():
            debug("Could not find any suitable route")
            return None

        tried_routes = []
        while routes.has_next():
            route = routes.get_next()
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

    def generate_invoice(self):
        memo = "Rebalance of channel to %d" % self.last_hop_channel_id
        return self.lnd.generate_invoice(memo, self.amount)
