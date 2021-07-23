import math

from output import Output
from routes import Routes

DEFAULT_BASE_FEE_SAT_MSAT = 1000
DEFAULT_FEE_RATE_MSAT = 0.001
MAX_FEE_RATE = 2000


class Logic:
    excluded = []

    def __init__(
        self,
        lnd,
        first_hop_channel,
        last_hop_channel,
        amount,
        channel_ratio,
        excluded,
        max_fee_factor,
        econ_fee,
        econ_fee_factor,
        output: Output
    ):
        self.lnd = lnd
        self.first_hop_channel = first_hop_channel
        self.last_hop_channel = last_hop_channel
        self.amount = amount
        self.channel_ratio = channel_ratio
        if excluded:
            self.excluded = excluded
        self.max_fee_factor = max_fee_factor
        self.econ_fee = econ_fee
        self.econ_fee_factor = econ_fee_factor
        self.output = output
        if not self.econ_fee_factor:
            self.econ_fee_factor = 1.0

    def rebalance(self):
        fee_limit_msat = self.get_fee_limit_msat()
        if self.last_hop_channel:
            self.output.print_line(
                f"Sending {self.amount:,} satoshis to rebalance to channel with ID "
                f"{self.last_hop_channel.chan_id} ({self.lnd.get_node_alias(self.last_hop_channel.remote_pubkey)})"
            )
        else:
            self.output.print_line(f"Sending {self.amount:,} satoshis.")
        if self.channel_ratio != 0.5:
            self.output.print_line(f"Channel ratio used is {int(self.channel_ratio * 100)}%")
        if self.first_hop_channel:
            self.output.print_line(
                f"Forced first channel has ID {self.first_hop_channel.chan_id} "
                f"({self.lnd.get_node_alias(self.first_hop_channel.remote_pubkey)})"
            )

        payment_request = self.generate_invoice()
        min_ppm_last_hop = None
        if self.econ_fee and self.first_hop_channel:
            policy_first_hop = self.lnd.get_policy_to(self.first_hop_channel.chan_id)
            min_ppm_last_hop = self.econ_fee_factor * policy_first_hop.fee_rate_milli_msat
        routes = Routes(
            self.lnd,
            payment_request,
            self.first_hop_channel,
            self.last_hop_channel,
            fee_limit_msat,
            min_ppm_last_hop,
            self.output
        )

        self.initialize_ignored_channels(routes, fee_limit_msat)

        tried_routes = []
        while routes.has_next():
            route = routes.get_next()

            success = self.try_route(payment_request, route, routes, tried_routes)
            if success:
                return True
        self.output.print_line("Could not find any suitable route")
        return False

    def get_fee_limit_msat(self):
        fee_limit_msat = None
        if self.last_hop_channel and self.econ_fee:
            policy = self.lnd.get_policy_to(self.last_hop_channel.chan_id)
            fee_rate = policy.fee_rate_milli_msat
            if fee_rate > MAX_FEE_RATE:
                self.output.print_line(
                    f"Calculating using capped fee rate {MAX_FEE_RATE} "
                    f"for inbound channel (original fee rate {fee_rate})"
                )
                fee_rate = MAX_FEE_RATE
            fee_limit_msat = self.econ_fee_factor * self.compute_fee(
                self.amount, fee_rate, policy
            )
            self.output.print_line(
                f"Setting fee limit to {int(fee_limit_msat)} "
                f"(due to --econ-fee, factor {self.econ_fee_factor})"
            )

        return fee_limit_msat

    def try_route(self, payment_request, route, routes, tried_routes):
        if self.route_is_invalid(route, routes):
            return False

        tried_routes.append(route)
        self.output.print_line("")
        self.output.print_line(f"Trying route #{len(tried_routes)}")
        self.output.print_route(route)

        response = self.lnd.send_payment(payment_request, route)
        is_successful = response.failure.code == 0
        if is_successful:
            last_hop_alias = self.lnd.get_node_alias(route.hops[-2].pub_key)
            first_hop_alias = self.lnd.get_node_alias(route.hops[0].pub_key)
            self.output.print_line("")
            self.output.print_line("")
            self.output.print_line("")
            self.output.print_line(
                f"Decreased inbound liquidity on {last_hop_alias} by "
                f"{int(route.hops[-1].amt_to_forward)} sats"
            )
            self.output.print_line(f"Increased inbound liquidity on {first_hop_alias}")
            self.output.print_line(f"Fee: {route.total_fees} sats")
            self.output.print_line("")
            self.output.print_line("Successful route:")
            self.output.print_route(route)
            return True
        else:
            self.handle_error(response, route, routes)
            return False

    def handle_error(self, response, route, routes):
        code = response.failure.code
        failure_source_pubkey = Logic.get_failure_source_pubkey(response, route)
        if code == 15:
            self.output.print_line("Temporary channel failure")
            routes.ignore_edge_on_route(failure_source_pubkey, route)
        elif code == 18:
            self.output.print_line("Unknown next peer")
            routes.ignore_edge_on_route(failure_source_pubkey, route)
        elif code == 12:
            self.output.print_line("Fee insufficient")
            routes.ignore_edge_on_route(failure_source_pubkey, route)
        elif code == 14:
            self.output.print_line("Channel disabled")
            routes.ignore_edge_on_route(failure_source_pubkey, route)
        else:
            self.output.print_line(repr(response))
            self.output.print_line(f"Unknown error code {repr(code)}")

    @staticmethod
    def get_failure_source_pubkey(response, route):
        if response.failure.failure_source_index == 0:
            failure_source_pubkey = route.hops[-1].pub_key
        else:
            failure_source_pubkey = route.hops[
                response.failure.failure_source_index - 1
            ].pub_key
        return failure_source_pubkey

    def route_is_invalid(self, route, routes):
        first_hop = route.hops[0]
        last_hop = route.hops[-1]
        if self.low_local_ratio_after_sending(first_hop, route.total_amt):
            self.output.print_without_linebreak("Outbound channel would have low local ratio after sending, ")
            routes.ignore_first_hop(self.get_channel_for_channel_id(first_hop.chan_id))
            return True
        if self.first_hop_and_last_hop_use_same_channel(first_hop, last_hop):
            self.output.print_without_linebreak("Outbound and inbound channel are identical, ")
            hop_before_last_hop = route.hops[-2]
            routes.ignore_edge_from_to(
                last_hop.chan_id, hop_before_last_hop.pub_key, last_hop.pub_key
            )
            return True
        if self.high_local_ratio_after_receiving(last_hop):
            self.output.print_without_linebreak(
                "Inbound channel would have high local ratio after receiving, "
            )
            hop_before_last_hop = route.hops[-2]
            routes.ignore_edge_from_to(
                last_hop.chan_id, hop_before_last_hop.pub_key, last_hop.pub_key
            )
            return True
        if self.fees_too_high(route):
            routes.ignore_high_fee_hops(route)
            return True
        return False

    def low_local_ratio_after_sending(self, first_hop, total_amount):
        if self.first_hop_channel:
            # Just use the computed/specified amount to drain the first hop, ignoring fees
            return False
        channel_id = first_hop.chan_id
        channel = self.get_channel_for_channel_id(channel_id)
        if channel is None:
            self.output.print_line(f"Unable to get channel information for hop {repr(first_hop)}")
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
            self.output.print_line(f"Unable to get channel information for hop {repr(last_hop)}")
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
        lnd_fees = hops_with_fees * (
            DEFAULT_BASE_FEE_SAT_MSAT + (self.amount * DEFAULT_FEE_RATE_MSAT)
        )
        limit = self.max_fee_factor * lnd_fees
        high_fees = route.total_fees_msat > limit
        if high_fees:
            self.output.print_without_linebreak(
                f"High fees ({int((route.total_fees_msat - limit) / 1000)} "
                f"sat over limit of {int(limit / 1000)}), "
            )
        return high_fees

    def fees_too_high_econ_fee(self, route):
        policy_first_hop = self.lnd.get_policy_to(route.hops[0].chan_id)
        amount = route.total_amt
        missed_fee = self.compute_fee(
            amount, policy_first_hop.fee_rate_milli_msat, policy_first_hop
        )
        policy_last_hop = self.lnd.get_policy_to(route.hops[-1].chan_id)
        fee_rate_last_hop = policy_last_hop.fee_rate_milli_msat
        original_fee_rate_last_hop = fee_rate_last_hop
        if fee_rate_last_hop > MAX_FEE_RATE:
            fee_rate_last_hop = MAX_FEE_RATE
        expected_fee = self.econ_fee_factor * self.compute_fee(
            amount, fee_rate_last_hop, policy_last_hop
        )
        rebalance_fee = route.total_fees
        high_fees = rebalance_fee + missed_fee > expected_fee
        if high_fees:
            difference = rebalance_fee + missed_fee - expected_fee
            if fee_rate_last_hop != original_fee_rate_last_hop:
                self.output.print_line(
                    f"Calculating using capped fee rate {MAX_FEE_RATE} for inbound channel "
                    f"(original fee rate {original_fee_rate_last_hop})"
                )
            self.output.print_without_linebreak(
                f"High fees ({math.floor(expected_fee)} expected future fee income for inbound channel "
                f"(factor {self.econ_fee_factor}), have to pay {int(rebalance_fee)} now, missing out on "
                f"{math.ceil(missed_fee)} future fees for outbound channel, difference {math.ceil(difference)}), "
            )
        return high_fees

    @staticmethod
    def compute_fee(amount, fee_rate, policy):
        expected_fee_msat = amount / 1000000 * fee_rate + policy.fee_base_msat / 1000
        return expected_fee_msat

    def generate_invoice(self):
        if self.last_hop_channel:
            memo = f"Rebalance of channel with ID {self.last_hop_channel.chan_id}"
        else:
            memo = f"Rebalance of channel with ID {self.first_hop_channel.chan_id}"
        return self.lnd.generate_invoice(memo, self.amount)

    def get_channel_for_channel_id(self, channel_id):
        for channel in self.lnd.get_channels():
            if channel.chan_id == channel_id:
                if not hasattr(channel, "local_balance"):
                    channel.local_balance = 0
                if not hasattr(channel, "remote_balance"):
                    channel.remote_balance = 0
                return channel
        self.output.print_line(f"Unable to find channel with id {channel_id}!")

    def initialize_ignored_channels(self, routes, fee_limit_msat):
        if self.first_hop_channel:
            # avoid me - X - me via the same channel/peer
            chan_id = self.first_hop_channel.chan_id
            from_pub_key = self.first_hop_channel.remote_pubkey
            to_pub_key = self.lnd.get_own_pubkey()
            routes.ignore_edge_from_to(
                chan_id, from_pub_key, to_pub_key, show_message=False
            )
            if not self.last_hop_channel:
                self.ignore_last_hops_with_high_ratio(routes)
        if self.last_hop_channel:
            # avoid me - X - me via the same channel/peer
            chan_id = self.last_hop_channel.chan_id
            from_pub_key = self.lnd.get_own_pubkey()
            to_pub_key = self.last_hop_channel.remote_pubkey
            routes.ignore_edge_from_to(
                chan_id, from_pub_key, to_pub_key, show_message=False
            )
            if self.econ_fee:
                self.ignore_first_hops_with_fee_rate_higher_than_last_hop(routes)
        if self.last_hop_channel and fee_limit_msat:
            # ignore first hops with high fee rate configured by our node (causing high missed future fees)
            max_fee_rate_first_hop = math.ceil(fee_limit_msat * 1_000 / self.amount)
            for channel in self.lnd.get_channels():
                policy = self.lnd.get_policy_to(channel.chan_id)
                fee_rate = policy.fee_rate_milli_msat
                if fee_rate > max_fee_rate_first_hop and self.first_hop_channel != channel:
                    routes.ignore_first_hop(channel, show_message=False)
        for channel in self.lnd.get_channels():
            if self.low_local_ratio_after_sending(channel, self.amount):
                routes.ignore_first_hop(channel, show_message=False)
            if channel.chan_id in self.excluded:
                self.output.print_without_linebreak("Channel is excluded, ")
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
                routes.ignore_edge_from_to(
                    chan_id, from_pub_key, to_pub_key, show_message=False
                )

    def ignore_last_hops_with_high_ratio(self, routes):
        for channel in self.lnd.get_channels():
            channel_id = channel.chan_id
            if channel is None:
                return
            remote = channel.remote_balance - self.amount
            local = channel.local_balance + self.amount
            ratio = float(local) / (remote + local)
            if ratio > self.channel_ratio:
                to_pub_key = self.lnd.get_own_pubkey()
                routes.ignore_edge_from_to(
                    channel_id, channel.remote_pubkey, to_pub_key, show_message=False
                )
