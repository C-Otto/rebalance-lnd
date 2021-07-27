# rebalance-lnd

Using this script you can easily rebalance individual channels of your `lnd` node by
sending funds out one channel, through the lightning network, back to yourself.

This script helps you move funds between your channels so that you can increase the outbound liquidity in one channel,
while decreasing the outbound liquidity in another channel.
This way you can, for example, make sure that all of your channels have enough outbound liquidity to send/route
transactions.

Because you are both the sender and the receiver of the corresponding transactions, you only have to pay for routing
fees.
Aside from paid fees, your total liquidity does not change.

## Installation

### lnd

This script needs an active `lnd` (tested with v0.13.0, https://github.com/lightningnetwork/lnd) instance running.
If you compile `lnd` yourself, you need to include the `routerrpc` build tag:

Example:
`make tags="autopilotrpc signrpc walletrpc chainrpc invoicesrpc routerrpc"`

You need to have admin rights to control this node.
By default, this script connects to `localhost:10009`, using the macaroon file in `~/.lnd/data/chain/bitcoin/mainnet/admin.macaroon`.
If you need to change this, please have a look at the optional arguments `--grpc` and `--lnddir`.

### Python Dependencies

You need to install Python 3. You also need to install the gRPC dependencies which can be done by running:

```
$ pip install -r requirements.txt
```

If this fails, make sure you are running Python 3.

To test if your installation works, you can run `rebalance.py` without any arguments.
Depending on your system, you can do this in one of the following ways:
 - `python3 rebalance.py`
 - `./rebalance.py`
 - `python rebalance.py`

## Updating

If you already have a version of `rebalance-lnd` checked out via `git`, you can just use `git pull` to update to the
latest version. You may also delete everything and start over with a fresh installation, as the script does not store
any data that needs to be kept.

Do not forget to update the Python dependencies as described above.

# Usage

### List of channels
Run `rebalance.py -l` (or `rebalance.py -l -i`) to see a list of channels which can be rebalanced.
This list only contains channels where you should increase the outbound liquidity (you can specify `--show-all` to see
all channels).

You can also see the list of channels where the outbound liquidity should be increased by running `rebalance.py -l -o`.

As an example the following indicates a channel with around 17.7% of the funds
on the local side:

```
Channel ID:       11111111
Alias:            The Best Node Ever
Pubkey:           012345[...]abcdef
Channel Point:    abc0123[...]abc:0
Local ratio:      0.176
Local fee ratio:  123ppm
Capacity:         5,000,000
Remote available: 4,110,320
Local available:    883,364
Rebalance amount:   616,636
[█████░░░░░░░░░░░░░░░░░░░░░░░]
```

By sending 116,636 satoshis to yourself using this channel, an outbound liquidity of 1,000,000 satoshis can be achieved.
This number is shown as "Rebalance amount" (where negative amounts indicate that you need to increase your inbound
liquidity).

The last line shows a graphical representation of the channel. 
The total width is determined by the channel's capacity, where your largest channel (maximum capacity) occupies the full
width of your terminal.
The bar (`█`) indicates the funds on the local side of the channel, i.e. your outbound liquidity.

## Rebalancing a channel
### Basic Scenario
In this scenario you already know what you want to do, possibly because you identified a channel with high
outbound liquidity.

Let us assume you want to move some funds from this channel to another channel with low outbound
liquidity:

- move 100,000 satoshis around
- take those funds (plus fees) out of channel `11111111`
- move those funds back into channel `22222222`

You can achieve this by running:

```
rebalance.py --amount 100000 --from 11111111 --to 22222222
```

The script now tries to find a route through the lightning network that starts with channel `11111111` and ends with
channel `22222222`. If successful, you take 100,000 satoshis (plus fees) out of channel `11111111` (which means that you
decrease your outbound liquidity and increase your inbound liquidity). In return, you get 100,000 satoshis back through
channel `22222222` (which means that you increase your outbound liquidity and decrease your inbound liquidity).

### Automatically determined amount

If you do not specify the amount, i.e. you invoke `rebalance.py --from 11111111 --to 22222222`, the script
automatically determines the amount.
For this two main constraints are taken into consideration:

After the rebalance transaction is finished, 

 - the destination channel (`22222222`) should have (up to) 1,000,000 satoshis outbound liquidity
 - the source channel (`11111111`) should have (at least) 1,000,000 satoshis outbound liquidity

If the source channel has enough surplus outbound liquidity, the script constructs a transaction that ensures
1,000,000 satoshis of outbound liquidity in the destination channel.
However, if the source channel does not have enough outbound liquidity, the amount is determined so that (after the
rebalance transaction is performed) the source channel has 1,000,000 satoshis of outbound liquidity and the destination
channel has more outbound liquidity than before (but not necessarily 1,000,000 satoshis).

Note that for smaller channels these criteria cannot be met.
If that is the case, a ratio of 50% is targeted instead: the destination channel receives up to 50% outbound
liquidity, and for the sending channel at least 50% outbound liquidity are maintained.

### Only specifying one channel 

Instead of specifying both `--from` and `--to`, you can also just pick one of those options.
The script then considers all of your other channels as possible "partners", still taking into account the constraints
described above.

As an example, if you run `rebalance.py --amount 100000 --to 22222222`, the script tries to find source channels
that, after sending 100,000 satoshis (plus fees), still have at least 1,000,000 satoshis of outbound liquidity.
In other words, the script does not send funds from already "empty" channels.

Likewise, when only specifying `--from`, the script only considers target channels which still have at least 1,000,000
satoshis of outbound liquidity after receiving the payment.

If you also let the script determine the amount, e.g. you run `rebalance.py --to 22222222`, the script first
computes the amount that is necessary to reach 1,000,000 satoshis of outbound liquidity in channel `22222222`, 
and then tries to find source channels for the computed amount.

### Safety Checks and Limitations

Note that, by default, nothing is done if the amount (either given or computed) is smaller than 10,000 satoshis.
You can change this number using `--min-amount`.

The maximum amount you can send in one transaction currently is limited (by the protocol) to 4,294,967 satoshis.

Furthermore, a rebalance transaction is only sent if it is economically viable as described below.
This way, by default, you only send rebalance transactions that improve your node's situation, for example by providing
outbound liquidity to channels where you charge a lot, and taking those funds out of channels where you charge less.

To protect you from making mistakes, in the fee computation (described below) the fee rate of the destination channel
is capped at 2,000ppm (which corresponds to a 0.2% fee), even if the channel is configured with a higher fee rate.

## Fees

In order for the network to route your rebalance transaction, you have to pay fees.
In addition to the fees charged by the nodes routing your transaction, two other values are taken into account:

1. The fee you would earn if, instead of sending the funds out of the source channel as part of the rebalance transaction, your node is paid to forward the amount
2. The fee you would earn if, after the rebalance transaction is done, your node forwards the amount through the destination channel

The first bullet point describes opportunity/implicit costs.
If you take lots of funds out of the source channel, you cannot use those funds to earn routing fees via that channel.
As such, taking funds out of a channel where you configured a high fee rate can be considered costly.

The second bullet points describes future earnings.
If you send funds to the destination channel and increase your outbound liquidity in that channel, you might earn fees
for routing those funds.
As such, increasing the outbound liquidity of the destination is a good idea, assuming the fee rate configured for the
destination channel is higher than the fee rate you configured for the source channel.
However, keep in mind that you will only earn those fees if your node actually forwards the funds via the channel!

The rebalance transaction is not performed if the transaction fees plus the implicit costs (1) are higher than the
possible future earnings (2).

**If you really want to, you may disable these safety checks with `--reckless`.**

### Example
You have lots of funds in channel `11111111` and nothing in channel `22222222`.
You would like to send funds through channel `11111111` (source channel) through the lightning network, and finally
back into channel `22222222`.
This incurs a transaction fee you would have to pay for the transaction.

Furthermore, if in the future there is demand for your node to route funds
through channel `11111111`, you cannot do that as much (because you decreased your outbound liquidity in the channel).
The associated fees are the implicit cost (1).

Finally, you send funds into channel `22222222` in the hope that later on someone requests your node to forward funds
from your own node through channel `22222222` towards the peer at the other end, so that you can earn fees for this.
These fees are the possible future income (2).

### Fee Factor

The value set with `--fee-factor` is used to scale the future income used in the computation outlined above.
As such, you can fool the script into believing that the fee rate configured for the destination channel is
higher (fee factor > 1) or lower (fee factor < 1) than it actually is.

As such, if you set `--fee-factor` to a value higher than 1, more routes are considered.
As an example, with `--fee-factor 1.5` you can include routes that cost up to 150% of the future income.

With values smaller than 1 only cheaper routes are considered.

### Fee Limit

As an alternative to `--fee-factor` (which is the default, with a value of 1), you can also specify an absolute fee
limit using `--fee-limit`. If you decide to do so, only routes that cost up to the given number (in satoshis) are
considered.

Note that the script rejects routes/channels that are deemed uneconomical based on the configured fee rates
(i.e. with `--fee-factor` set to 1) (as explained above).

### Fee Rate (ppm) Limit

You can use `--fee-ppm-limit` as another alternative to specify a fee limit.
In this case the amount sent as part of the rebalance is considered, so that the fee is at most

```
amount * fee-ppm-limit / 1_000_000
```

Note that the script rejects routes/channels that are deemed uneconomical based on the configured fee rates
(i.e. with `--fee-factor` set to 1) (as explained above).

### Warning

To determine the future income, the fee rate you configured for the destination channel is used in the computation.
As such, if you set an unrealistic fee rate that will not lead to forward transactions, you would allow more expensive
rebalance transactions without earning anything in return.
Please make sure to set realistic fee rates, which at best are already known to attract forwardings.

### Command line arguments
```
usage: rebalance.py [-h] [--lnddir LNDDIR] [--grpc GRPC] [-l] [--show-all] [-o | -i] [-f CHANNEL] [-t CHANNEL] [-a AMOUNT | -p PERCENTAGE] [--min-amount MIN_AMOUNT] [--min-local MIN_LOCAL] [--min-remote MIN_REMOTE] [-e EXCLUDE] [--reckless]
                    [--fee-factor FEE_FACTOR | --fee-limit FEE_LIMIT | --fee-ppm-limit FEE_PPM_LIMIT]

optional arguments:
  -h, --help            show this help message and exit
  --lnddir LNDDIR       (default ~/.lnd) lnd directory
  --grpc GRPC           (default localhost:10009) lnd gRPC endpoint

list candidates:
  Show the unbalanced channels.

  -l, --list-candidates
                        list candidate channels for rebalance
  --show-all            also show channels with zero rebalance amount
  -o, --outgoing        lists channels with less than 1,500,00 satoshis inbound liquidity
  -i, --incoming        (default) lists channels with less than 1,500,00 satoshis outbound liquidity

rebalance:
  Rebalance a channel. You need to specify at least the 'from' channel (-f) or the 'to' channel (-t).

  -f CHANNEL, --from CHANNEL
                        Channel ID of the outgoing channel (funds will be taken from this channel). You may also use -1 to choose a random candidate.
  -t CHANNEL, --to CHANNEL
                        Channel ID of the incoming channel (funds will be sent to this channel). You may also use -1 to choose a random candidate.
  -a AMOUNT, --amount AMOUNT
                        Amount of the rebalance, in satoshis. If not specified, the amount computed for a perfect rebalance will be used (up to the maximum of 4,294,967 satoshis)
  -p PERCENTAGE, --percentage PERCENTAGE
                        Set the amount to a percentage of the computed amount. As an example, if this is set to 50, half of the computed amount will be used. See --amount.
  --min-amount MIN_AMOUNT
                        (Default: 10,000) If the given or computed rebalance amount is below this limit, nothing is done.
  --min-local MIN_LOCAL
                        (Default: 1,000,000) Ensure that the channels have at least this amount as outbound liquidity.
  --min-remote MIN_REMOTE
                        (Default: 1,000,000) Ensure that the channels have at least this amount as inbound liquidity.
  -e EXCLUDE, --exclude EXCLUDE
                        Exclude the given channel ID as the outgoing channel (no funds will be taken out of excluded channels)
  --reckless            Allow rebalance transactions that are not economically viable. You might also want to set --min-local 0 and --min-local 0. If set, you also need to set --amount and either --fee-limit or --fee-ppm-limit.
  --fee-factor FEE_FACTOR
                        (default: 1.0) Compare the costs against the expected income, scaled by this factor. As an example, with --fee-factor 1.5, routes that cost at most 150% of the expected earnings are tried. Use values smaller than 1.0 to restrict
                        routes to only consider those earning more/costing less. This factor is ignored with --reckless.
  --fee-limit FEE_LIMIT
                        If set, only consider rebalance transactions that cost up to the given number of satoshis.
  --fee-ppm-limit FEE_PPM_LIMIT
                        If set, only consider rebalance transactions that cost up to the given number of satoshis per 1M satoshis sent.
```

## Contributing

Contributions are highly welcome!
Feel free to submit issues and pull requests on https://github.com/C-Otto/rebalance-lnd/

You can also send donations via keysend.
For example, to send 500 satoshis to C-Otto with a message "Thank you for rebalance-lnd":
```
lncli sendpayment --amt=500 --data 7629168=5468616e6b20796f7520666f7220726562616c616e63652d6c6e64 --keysend --dest=027ce055380348d7812d2ae7745701c9f93e70c1adeb2657f053f91df4f2843c71
```

You can also specify an arbitrary message:
```
lncli sendpayment --amt=500 --data 7629168=$(echo -n "your message here" | xxd -pu -c 10000) --keysend --dest=027ce055380348d7812d2ae7745701c9f93e70c1adeb2657f053f91df4f2843c71
```