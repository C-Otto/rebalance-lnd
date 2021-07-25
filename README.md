# rebalance-lnd

Using this script you can easily rebalance individual channels of your lnd node.

## Installation

This script needs an active lnd 0.9.0+ (https://github.com/lightningnetwork/lnd) instance running.
If you compile lnd yourself, you need to include the `routerrpc` build tag.

Example:
`make tags="autopilotrpc signrpc walletrpc chainrpc invoicesrpc routerrpc"`

You need to have admin rights to control this node.
By default, this script connects to `localhost:10009`, using the macaroon file in `~/.lnd/data/chain/bitcoin/mainnet/admin.macaroon`.
If you need to change this, please have a look at the optional arguments `--grpc` and `--lnddir`.

You need to install Python 3. You also need to install the gRPC dependencies which can be done by running:

```
$ pip install -r requirements.txt
```

If this fails, make sure you're running Python 3.

To test if your installation works, you can run `rebalance.py` without any arguments.
Depending on your system, you can do this in one of the following ways:
 - `python3 rebalance.py`
 - `./rebalance.py`
 - `python rebalance.py`

## Updating

If you already have a version of `rebalance-lnd` checked out via `git`, you can just use `git pull` to update to the
latest version. You may also delete everything and start over with a fresh installation, as the script does not store
any data that needs to be kept.

## Usage

See below for an explanation.

### Command line arguments
```
usage: rebalance.py [-h] [--lnddir LNDDIR] [--grpc GRPC] [-l] [-o | -i] [-f CHANNEL] [-t CHANNEL] [-a AMOUNT] [--min-amount MIN_AMOUNT] [-e EXCLUDE] [--fee-factor FEE_FACTOR | --fee-limit FEE_LIMIT | --fee-ppm-limit FEE_PPM_LIMIT]

optional arguments:
  -h, --help            show this help message and exit
  --lnddir LNDDIR       (default ~/.lnd) lnd directory
  --grpc GRPC           (default localhost:10009) lnd gRPC endpoint

list candidates:
  Show the unbalanced channels.

  -l, --list-candidates
                        list candidate channels for rebalance
  -o, --outgoing        lists channels with less than 50% of the funds on the remote side
  -i, --incoming        (default) lists channels with less than 50% of the funds on the local side

rebalance:
  Rebalance a channel. You need to specify at least the 'from' channel (-f) or the 'to' channel (-t).

  -f CHANNEL, --from CHANNEL
                        Channel ID of the outgoing channel (funds will be taken from this channel). You may also use -1 to choose a random candidate.
  -t CHANNEL, --to CHANNEL
                        Channel ID of the incoming channel (funds will be sent to this channel). You may also use -1 to choose a random candidate.
  -a AMOUNT, --amount AMOUNT
                        Amount of the rebalance, in satoshis. If not specified, the amount computed for a perfect rebalance will be used (up to the maximum of 4,294,967 satoshis)
  --min-amount MIN_AMOUNT
                        (Default: 10,000) If the given or computed rebalance amount is below this limit, nothing is done.
  -e EXCLUDE, --exclude EXCLUDE
                        Exclude the given channel ID as the outgoing channel (no funds will be taken out of excluded channels)
  --fee-factor FEE_FACTOR
                        (default: 1.0) Compare the costs against the expected income, scaled by this factor. As an example, with --fee-factor 1.5, routes that cost at most 150% of the expected earnings are tried. Use values smaller than 1.0 to restrict routes to only consider those earning
                        more/costing less.
  --fee-limit FEE_LIMIT
                        If set, only consider rebalance transactions that cost up to the given number of satoshis.
  --fee-ppm-limit FEE_PPM_LIMIT
                        If set, only consider rebalance transactions that cost up to the given number of satoshis per 1M satoshis sent.
```

### List of channels
Run `rebalance.py -l` (or `rebalance.py -l -i`) to see a list of channels which
can be rebalanced.
This list only contains channels where less than 50% of the total funds are on
the local side of the channel.

You can also see the list of channels where less than 50% of the total funds
are on the remote side of the channel by running `rebalance.py -l -o`.

As an example the following indicates a channel with around 17.7% of the funds
on the local side:

```
Channel ID:  123[...]456
Alias:            The Best Node Ever
Pubkey:           012345[...]abcdef
Channel Point:    abc0123[...]abc:0
Local ratio:      0.176
Local fee ratio:  123ppm
Capacity:         5,000,000
Remote balance:   4,110,320
Local balance:    883,364
Amount for 50-50: 1,613,478
[█████░░░░░░░░░░░░░░░░░░░░░░░]
```

By sending 1,613,478 satoshis to yourself using this channel, a ratio of 50% can be achieved.
This number is shown as "Amount for 50-50".

The last line shows a graphical representation of the channel. 
The total width is determined by the channel's capacity, where your largest channel (maximum capacity) #occupies the full
width of your terminal.
The bar (`█`) indicates the funds on the local side of the channel.

### Rebalancing a channel
To actually rebalance a channel, run the script and specify the channel to send funds to (`-t`) or from (`-f`).
Use `--from` (or `-f`) to specify a channel that too many funds on your _local_ side (ratio > 0.5).
Likewise, use `--to` (or `-t`) to specify a channel that has too many funds on the _remote_ side (ratio < 0.5). 

It is possible to use both `-t` and `-f`, but at least one of these arguments must be given.
You can also specify the amount to send (using `-a`).
You specify the channel(s) using the channel ID, as shown in the output of `rebalance.py`.

`rebalance.py -t 123[...]456 -a 1613478`

If you do not specify the amount, the script automatically determines the rebalance amount.
Note that, by default, nothing is done if the amount (either given or computed) is below 10,000 satoshis.
You can change this number using `--min-amount`.

The maximum amount you can send in one transaction currently is limited (by the protocol) to 4,294,967 satoshis.

### Fees

In order for the network to route your rebalance transaction, you have to pay fees.
Three different fees are taken into account:

1. The actual fee you'd have to pay for the rebalance transaction
2. The fee you'd earn if, instead of sending the funds due to your own rebalance transaction, your node is paid to forward the amount through the outbound (`--from`) channel
3. The fee you'd earn if, after the rebalance transaction is done, your node forwards the amount back again through the inbound (`--to`) channel

The rebalance transaction is not performed if the direct costs (1) plus the implicit costs (2) are higher than the
possible future income (3).

#### Example
You have lots of funds in channel A and nothing in channel B. You would like to send half of the funds through
channel A (outbound channel) through the lightning network, and finally back into channel B. This incurs a transaction
fee you'd have to pay for the transaction. This is the direct cost (1).

Furthermore, if in the future there is demand for your node to route funds
through channel A, you cannot do that as much (because you reduced outbound liquidity in the channel).
The associated fees are the implicit cost (2).

Finally, you rebalance channel B in the hope that later on someone requests your node to forward funds from your own node
through channel B towards the peer at the other end, so that you can earn fees for this.
These fees are the possible future income (3).

### Factor

The value set with `--fee-factor` is used to scale the future income used in the computation outlined above.

As such, if you set `--fee-factor` to a value higher than 1.0, routes that cost more than the future income are
considered. As an example, with `--fee-factor 1.5` you can include routes that cost up to 150% of the
future income.

You can also use values smaller than 1.0 to restrict which routes are considered, i.e. routes that are cheaper.

### Fee Limit

As an alternative to `--fee-factor` (which is the default, with a value of 1), you can also specify an absolute fee
limit using `--fee-limit`. If you decide to do so, only routes that cost up to the given number (in satoshis) are
considered.

Note that the script rejects routes/channels that are deemed uneconomical (as explained above).

### Fee Rate (ppm) Limit

You can use `--fee-ppm-limit` as another alternative to specify a fee limit.
In this case the amount sent as part of the rebalance is considered, so that the fee is at most

```
amount * fee-ppm-limit / 1_000_000
```

Note that the script rejects routes/channels that are deemed uneconomical (as explained above).

#### Warning
To determine the future income, the fee set as part of the channel policy is used in the computation.
As such, if you set a too high fee rate, you'd allow more expensive rebalance transactions.
Please make sure to set realistic fee rates, which at best are already known to attract forwardings.
To protect you from making mistakes, this script uses a fee rate of at most 2,000 sat per 1M sat (which corresponds
to a 0.2% fee), even if the inbound channel is configured with a higher fee rate.

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