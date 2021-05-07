import sys

from routes import Routes

DEFAULT_BASE_FEE_SAT_MSAT = 1000
DEFAULT_FEE_RATE_MSAT = 0.001
MAX_FEE_RATE = 10000


def debug(message):
    sys.stderr.write(message + "\n")


def debugnobreak(message):
    sys.stderr.write(message)


class Logic:
    def __init__(self,
                 lnd, first_hop_channel, last_hop_channel, amount, channel_ratio, excluded, max_fee_factor, econ_fee
                 ):
        self.lnd = lnd
        self.first_hop_channel = first_hop_channel
        self.last_hop_channel = last_hop_channel
        self.amount = amount
        self.channel_ratio = channel_ratio
        self.excluded = []
        if excluded:
            self.excluded = excluded
        self.max_fee_factor = max_fee_factor
        self.econ_fee = econ_fee

    def rebalance(self):
        fee_limit = self.get_fee_limit()
        if self.last_hop_channel:
            debug(("Sending {:,} satoshis to rebalance to channel with ID %d"
                   % self.last_hop_channel.chan_id).format(self.amount))
        else:
            debug("Sending {:,} satoshis.".format(self.amount))
        if self.channel_ratio != 0.5:
            debug("Channel ratio used is %d%%" % int(self.channel_ratio * 100))
        if self.first_hop_channel:
            debug("Forced first channel has ID %d" % self.first_hop_channel.chan_id)

        payment_request = self.generate_invoice()
        routes = Routes(self.lnd, payment_request, self.first_hop_channel, self.last_hop_channel, fee_limit)

        self.initialize_ignored_channels(routes)

        tried_routes = []
        while routes.has_next():
            route = routes.get_next()

            success = self.try_route(payment_request, route, routes, tried_routes)
            if success:
                return True
        debug("Could not find any suitable route")
        return False

    def get_fee_limit(self):
        fee_limit = None
        if self.last_hop_channel and self.econ_fee:
            policy = self.lnd.get_policy_to(self.last_hop_channel.chan_id)
            if policy.fee_rate_milli_msat > MAX_FEE_RATE:
                debug("Unable to use --econ-fee, policy for inbound channel looks odd (fee rate %s)"
                      % policy.fee_rate_milli_msat)
                sys.exit(1)
            fee_limit = self.fee_for_policy(self.amount, policy)
            debug("Setting fee limit to %s (due to --econ-fee)" % int(fee_limit))

        return fee_limit

    def try_route(self, payment_request, route, routes, tried_routes):
        if self.route_is_invalid(route, routes):
            return False

        tried_routes.append(route)
        debug("")
        debug("Trying route #%d" % len(tried_routes))
        debug(Routes.print_route(route))

        response = self.lnd.send_payment(payment_request, route)
        is_successful = response.failure.code == 0
        if is_successful:
            debug("")
            debug("")
            debug("")
            debug("Success! Paid fees: %s sat (%s msat)" % (route.total_fees, route.total_fees_msat))
            debug("Successful route:")
            debug(Routes.print_route(route))
            debug("")
            debug("")
            debug("")
            return True
        else:
            self.handle_error(response, route, routes)
            return False

    @staticmethod
    def handle_error(response, route, routes):
        code = response.failure.code
        failure_source_pubkey = Logic.get_failure_source_pubkey(response, route)
        if code == 15:
            debugnobreak("Temporary channel failure, ")
            routes.ignore_edge_on_route(failure_source_pubkey, route)
        elif code == 18:
            debugnobreak("Unknown next peer, ")
            routes.ignore_edge_on_route(failure_source_pubkey, route)
        elif code == 12:
            debugnobreak("Fee insufficient, ")
            routes.ignore_edge_on_route(failure_source_pubkey, route)
        elif code == 14:
            debugnobreak("Channel disabled, ")
            routes.ignore_edge_on_route(failure_source_pubkey, route)
        else:
            debug(repr(response))
            debug("Unknown error code %s" % repr(code))

    @staticmethod
    def get_failure_source_pubkey(response, route):
        if response.failure.failure_source_index == 0:
            failure_source_pubkey = route.hops[-1].pub_key
        else:
            failure_source_pubkey = route.hops[response.failure.failure_source_index - 1].pub_key
        return failure_source_pubkey

    def route_is_invalid(self, route, routes):
        first_hop = route.hops[0]
        last_hop = route.hops[-1]
        if self.low_local_ratio_after_sending(first_hop, route.total_amt):
            debugnobreak("Outbound channel would have low local ratio after sending, ")
            routes.ignore_first_hop(self.get_channel_for_channel_id(first_hop.chan_id))
            return True
        if self.first_hop_and_last_hop_use_same_channel(first_hop, last_hop):
            debugnobreak("Outbound and inbound channel are identical, ")
            hop_before_last_hop = route.hops[-2]
            routes.ignore_edge_from_to(last_hop.chan_id, hop_before_last_hop.pub_key, last_hop.pub_key)
            return True
        if self.high_local_ratio_after_receiving(last_hop):
            debugnobreak("Inbound channel would have high local ratio after receiving, ")
            hop_before_last_hop = route.hops[-2]
            routes.ignore_edge_from_to(last_hop.chan_id, hop_before_last_hop.pub_key, last_hop.pub_key)
            return True
        if self.fees_too_high(route):
            routes.ignore_node_with_highest_fee(route)
            return True
        return False

    def low_local_ratio_after_sending(self, first_hop, total_amount):
        if self.first_hop_channel:
            # Just use the computed/specified amount to drain the first hop, ignoring fees
            return False
        channel_id = first_hop.chan_id
        channel = self.get_channel_for_channel_id(channel_id)
        if channel is None:
            debug("Unable to get channel information for hop %s" % repr(first_hop))
            return True

        remote = channel.remote_balance + total_amount
        local = channel.local_balance - total_amount
        ratio = float(local) / (remote + local)
        return ratio < self.channel_ratio

    def high_local_ratio_after_receiving(self, last_hop):
        if self.last_hop_channel:
            return False
        channel_id = last_hop.chan_id
        channel = self.get_channel_for_channel_id(channel_id)
        if channel is None:
            debug("Unable to get channel information for hop %s" % repr(last_hop))
            return True

        amount = last_hop.amt_to_forward
        remote = channel.remote_balance - amount
        local = channel.local_balance + amount
        ratio = float(local) / (remote + local)
        return ratio > self.channel_ratio

    @staticmethod
    def first_hop_and_last_hop_use_same_channel(first_hop, last_hop):
        return first_hop.chan_id == last_hop.chan_id

    def fees_too_high(self, route):
        if self.econ_fee:
            return self.fees_too_high_econ_fee(route)
        hops_with_fees = len(route.hops) - 1
        lnd_fees = hops_with_fees * (DEFAULT_BASE_FEE_SAT_MSAT + (self.amount * DEFAULT_FEE_RATE_MSAT))
        limit = self.max_fee_factor * lnd_fees
        high_fees = route.total_fees_msat > limit
        if high_fees:
            debugnobreak("High fees (%s sat over limit of %s), "
                         % (int((route.total_fees_msat - limit) / 1000), int(limit/1000)))
        return high_fees

    def fees_too_high_econ_fee(self, route):
        policy_first_hop = self.lnd.get_policy_to(route.hops[0].chan_id)
        amount = route.total_amt
        missed_fee = self.fee_for_policy(amount, policy_first_hop)
        policy_last_hop = self.lnd.get_policy_to(route.hops[-1].chan_id)
        if policy_last_hop.fee_rate_milli_msat > MAX_FEE_RATE:
            debug("Ignoring route, policy for inbound channel looks odd (fee rate %s)"
                  % policy_last_hop.fee_rate_milli_msat)
            return True
        expected_fee = self.fee_for_policy(amount, policy_last_hop)
        rebalance_fee = route.total_fees
        high_fees = rebalance_fee + missed_fee > expected_fee
        if high_fees:
            difference = rebalance_fee + missed_fee - expected_fee
            debugnobreak("High fees ("
                         "%s expected future fee income for inbound channel, "
                         "have to pay %s now, "
                         "missing out on %s future fees for outbound channel, "
                         "difference %s), "
                         % (int(expected_fee), int(rebalance_fee), int(missed_fee), int(difference)))
        return high_fees

    @staticmethod
    def fee_for_policy(amount, policy):
        expected_fee_msat = amount / 1000000 * policy.fee_rate_milli_msat + policy.fee_base_msat / 1000
        return expected_fee_msat

    def generate_invoice(self):
        if self.last_hop_channel:
            memo = "Rebalance of channel with ID %d" % self.last_hop_channel.chan_id
        else:
            memo = "Rebalance of channel with ID %d" % self.first_hop_channel.chan_id
        return self.lnd.generate_invoice(memo, self.amount)

    def get_channel_for_channel_id(self, channel_id):
        for channel in self.lnd.get_channels():
            if channel.chan_id == channel_id:
                if not hasattr(channel, 'local_balance'):
                    channel.local_balance = 0
                if not hasattr(channel, 'remote_balance'):
                    channel.remote_balance = 0
                return channel
        debug("Unable to find channel with id %d!" % channel_id)

    def initialize_ignored_channels(self, routes):
        if self.first_hop_channel:
            chan_id = self.first_hop_channel.chan_id
            from_pub_key = self.first_hop_channel.remote_pubkey
            to_pub_key = self.lnd.get_own_pubkey()
            routes.ignore_edge_from_to(chan_id, from_pub_key, to_pub_key, show_message=False)
        if self.last_hop_channel:
            chan_id = self.last_hop_channel.chan_id
            from_pub_key = self.lnd.get_own_pubkey()
            to_pub_key = self.last_hop_channel.remote_pubkey
            routes.ignore_edge_from_to(chan_id, from_pub_key, to_pub_key, show_message=False)
            if self.econ_fee:
                self.ignore_first_hops_with_fee_rate_higher_than_last_hop(routes)
        for channel in self.lnd.get_channels():
            if self.low_local_ratio_after_sending(channel, self.amount):
                routes.ignore_first_hop(channel, show_message=False)
            if channel.chan_id in self.excluded:
                debugnobreak("Channel is excluded, ")
                routes.ignore_first_hop(channel)

    def ignore_first_hops_with_fee_rate_higher_than_last_hop(self, routes):
        policy_last_hop = self.lnd.get_policy_to(self.last_hop_channel.chan_id)
        last_hop_fee_rate = policy_last_hop.fee_rate_milli_msat
        from_pub_key = self.lnd.get_own_pubkey()
        for channel in self.lnd.get_channels():
            chan_id = channel.chan_id
            policy = self.lnd.get_policy_to(chan_id)
            if policy.fee_rate_milli_msat > last_hop_fee_rate:
                to_pub_key = channel.remote_pubkey
                routes.ignore_edge_from_to(chan_id, from_pub_key, to_pub_key, show_message=False)
