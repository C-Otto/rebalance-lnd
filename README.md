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

## Usage

See below for an explanation.

### Command line arguments
```
usage: rebalance.py [-h] [--lnddir LNDDIR] [--grpc GRPC] [-r RATIO] [-l]
                    [-o | -i] [-f CHANNEL] [-t CHANNEL]
                    [-a AMOUNT | -p PERCENTAGE] [-e EXCLUDE]
                    [--max-fee-factor MAX_FEE_FACTOR | --econ-fee]
                    [--econ-fee-factor ECON_FEE_FACTOR]

optional arguments:
  -h, --help            show this help message and exit
  --lnddir LNDDIR       (default ~/.lnd) lnd directory
  --grpc GRPC           (default localhost:10009) lnd gRPC endpoint
  -r RATIO, --ratio RATIO
                        (default: 50) ratio for channel imbalance between 1
                        and 50, eg. 45 to only show channels (-l) with less
                        than 45% of the funds on the local (-i) or remote (-o)
                        side

list candidates:
  Show the unbalanced channels.

  -l, --list-candidates
                        list candidate channels for rebalance
  -o, --outgoing        lists channels with less than x% of the funds on the
                        remote side (see --ratio)
  -i, --incoming        (default) lists channels with less than x% of the
                        funds on the local side (see --ratio)

rebalance:
  Rebalance a channel. You need to specify at least the 'from' channel (-f)
  or the 'to' channel (-t).

  -f CHANNEL, --from CHANNEL
                        Channel ID of the outgoing channel (funds will be
                        taken from this channel). You may also use the index
                        as shown in the incoming candidate list (-l -o), or -1
                        to choose a random candidate.
  -t CHANNEL, --to CHANNEL
                        Channel ID of the incoming channel (funds will be sent
                        to this channel). You may also use the index as shown
                        in the incoming candidate list (-l -i), or -1 to
                        choose a random candidate.
  -a AMOUNT, --amount AMOUNT
                        Amount of the rebalance, in satoshis. If not
                        specified, the amount computed for a perfect rebalance
                        will be used (up to the maximum of 4,294,967 satoshis)
  -p PERCENTAGE, --percentage PERCENTAGE
                        Set the amount to send to a percentage of the amount
                        required to rebalance. As an example, if this is set
                        to 50, the amount will half of the default. See
                        --amount.
  -e EXCLUDE, --exclude EXCLUDE
                        Exclude the given channel ID as the outgoing channel
                        (no funds will be taken out of excluded channels)
  --max-fee-factor MAX_FEE_FACTOR
                        (default: 10) Reject routes that cost more than x
                        times the lnd default (base: 1 sat, rate: 1 millionth
                        sat) per hop on average
  --econ-fee            (default: disabled) Economy Fee Mode, see README.md
  --econ-fee-factor ECON_FEE_FACTOR
                        (default: 1.0) When using --econ-fee, compare the
                        costs against the expected income, scaled by this
                        factor. As an example, with --econ-fee-factor 1.5,
                        routes that cost at most 150% of the expected earnings
                        are tried. Use values smaller than 1.0 to restrict
                        routes to only consider those earning more/costing
                        less.  
```

### List of channels
Run `rebalance.py -l` (or `rebalance.py -l -i`) to see a list of channels which
can be rebalanced.
This list only contains channels where less than 50% of the total funds are on
the local side of the channel.

You can also see the list of channels where less than 50% of the total funds
are on the remote side of the channel by running `rebalance.py -l -o`.

Use `-r/--ratio` to configure the sensitivity ratio (default is 50 for 50%).
As an example, `rebalance.py -l -o -r 10` only shows channels where less than
10% of the total funds are on the remote side of the channel.

As an example the following indicates a channel with around 17.7% of the funds
on the local side:

```
(23) Channel ID:  123[...]456
Alias:            The Best Node Ever
Pubkey:           012345[...]abcdef
Channel Point:    abc0123[...]abc:0
Local ratio:      0.176
Capacity:         5,000,000
Remote balance:   4,110,320
Local balance:    883,364
Amount for 50-50: 1,613,478
|=====                       |
```

By sending 1,613,478 satoshis to yourself using this channel, a ratio of 50% can be achieved.
This number is shown as "Amount for 50-50".

The last line shows a graphical representation of the channel. 
The total width is determined by the channel's capacity, where a channel with maximum (non-wumbo) capacity
(16,777,215 satoshis) occupies the full width of your terminal.
The bar (`=`) indicates the funds on the local side of the channel.

The number next to the channel ID (23 in the example) can be used to directly reference this channel.

### Rebalancing a channel
To actually rebalance a channel, run the script and specify the channel to send funds to (`-t`) or from (`-f`).
Use `--from` (or `-f`) to specify a channel that too many funds on your _local_ side (ratio > 0.5).
Likewise, use `--to` (or `-t`) to specify a channel that has too many funds on the _remote_ side (ratio < 0.5). 

It is possible to use both `-t` and `-f`, but at least one of these arguments must be given.
You can also specify the amount to send (using `-a`).
You specify the channel(s) using the channel ID, as shown in the output of `rebalance.py`.

`rebalance.py -t 123[...]456 -a 1613478`

It is also possible to indicate the `--to/-t` channel by the number shown next to the channel ID (23 in the example).

`rebalance.py -t 23 -a 1613478`

If you do not specify the amount, the script automatically determines the rebalance amount.
As an alternative to specifying the amount you may also set a percentage of the rebalance amount using `-p`.
For example, the following command tries to send 20% of the amount required to rebalance the channel:

`rebalance.py -t 23 -p 20`

The maximum amount you can send in one transaction currently is limited (by the protocol) to 4,294,967 satoshis.

### Fees

In order for the network to route your rebalance transaction, you have to pay fees.
To protect yourself from "greedy" peers, certain routes are rejected by default by using `--max-fee-factor` with a
default value of 10:
> Reject routes that cost more than 10 times the lnd default (base: 1 sat, rate: 1 millionth sat) per hop on average.

Note that it may be necessary to pay higher fees, i.e. you'd need to set a higher `--max-fee-factor`.

#### Economy Fee Mode
As an alternative to `--max-fee-factor`, you can also enable the Economy Fee Mode using `--econ-fee`.
If this mode is enabled, three different fees are taken into account:

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

The value set with `--econ-fee-factor` is used to scale the future income used in the computation outlined above.

As such, if you set `--econ-fee-factor` to a value higher than 1.0, routes that cost more than the future income are
considered. As an example, with `--econ-fee --econ-fee-factor 1.5` you can include routes that cost up to 150% of the
future income.

You can also use values smaller than 1.0 to restrict which routes are considered, i.e. routes that are cheaper. 

#### Warning
To determine the future income, the fee set as part of the channel policy is used in the computation.
As such, if you set a too high fee rate, with `--econ-fee` you'd allow more expensive rebalance
transactions. Please make sure to set realistic fee rates, which at best are already known to attract forwardings.
To protect you from making mistakes, `--econ-fee` uses a fee rate of at most 1,000 sat per 1M sat (which corresponds
to a 0.1% fee), even if the inbound channel is configured with a higher fee rate.

## Contributing

Contributions are highly welcome!
Feel free to submit issues and pull requests on https://github.com/C-Otto/rebalance-lnd/

You can also send donations via keysend.
For example, to send 500 satoshi to C-Otto with a message "Thank you for rebalance-lnd":
```
lncli sendpayment --amt=500 --data 7629168=5468616e6b20796f7520666f7220726562616c616e63652d6c6e64 --keysend --dest=027ce055380348d7812d2ae7745701c9f93e70c1adeb2657f053f91df4f2843c71
```

You can also specify an arbitrary message:
```
lncli sendpayment --amt=500 --data 7629168=$(echo -n "your message here" | xxd -pu -c 10000) --keysend --dest=027ce055380348d7812d2ae7745701c9f93e70c1adeb2657f053f91df4f2843c71
```

Please also consider opening a channel with one of our nodes:

* C-Otto: `027ce055380348d7812d2ae7745701c9f93e70c1adeb2657f053f91df4f2843c71@157.90.112.145:9735`
* wamde: `0269b91661812bae52280a68eec2b89d38bf26b33966441ad70aa365e120a125ff@82.36.141.97:9735`
