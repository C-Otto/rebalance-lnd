# rebalance-lnd

Using this script you can easily rebalance individual channels of your lnd node.

## Installation

This script needs an active lnd 0.9.0+ (https://github.com/lightningnetwork/lnd) instance running.
If you compile lnd yourself, you need to include the `routerrpc` build tag.

Example:
`make tags="autopilotrpc signrpc walletrpc chainrpc invoicesrpc routerrpc"`

You need to have admin rights to control this node.
By default this script connects to `localhost:10009`, using the macaroon file in `~/.lnd/data/chain/bitcoin/mainnet/admin.macaroon`.
If you need to change this, please have a look at the optional arguments `--grpc` and `--lnddir`.

You need to install Python. The gRPC dependencies can be installed by running:

```
$ pip install -r requirements.txt
```

## Usage

### Command line arguments
```
usage: rebalance.py [-h] [--lnddir LNDDIR] [--grpc GRPC] [-r RATIO] [-l]
                    [-o | -i] [-f CHANNEL] [-t CHANNEL]
                    [-a AMOUNT | -p PERCENTAGE] [-e EXCLUDE]
                    [--max-fee-factor MAX_FEE_FACTOR]

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
                        channel ID of the outgoing channel (funds will be
                        taken from this channel)
  -t CHANNEL, --to CHANNEL
                        channel ID of the incoming channel (funds will be sent
                        to this channel). You may also use the index as shown
                        in the incoming candidate list (-l -i).
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
Pubkey:           012345[...]abcdef
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
The total width is determined by the channel's capacity, where a channel with maximum capacity (16,777,215 satoshis)
occupies the full width of your terminal.
The bar (`=`) indicates the funds on the local side of the channel.

The number next to the channel ID (23 in the example) can be used to directly reference this channel.

### Rebalancing a channel
To actually rebalance a channel, run the script and specify the channel to send funds to (`-t`) or from (`-f`).
It is possible to use both `-t` and `-f`, but at least one of these arguments must be given.
You can also specify the amount to send (using `-a`).
You specify the channel(s) using the channel ID, as shown in the output of `rebalance.py`.

`rebalance.py -t 123[...]456 -a 1613478`

It is also possible to indicate the `--to/-t` channel by the number shown next to the channel ID (23 in the example).

`rebalance.py -t 23 -a 1613478`

If you do not specify the amount, the rebalance amount is determined automatically.
As an alternative to specify the amount you may also set a percentage of the rebalance amount using `-p`.
For example, the following command tries to sends 20% of the amount required to rebalance the channel:

`rebalance.py -t 23 -p 20`

The maximum amount you can send in one transaction currently is limited (by the protocol) to 4,294,967 satoshis.

## Contributing

Contributions are highly welcome!
Feel free to submit issues and pull requests on https://github.com/C-Otto/rebalance-lnd/

Please also consider opening a channel with one of our nodes, or sending tips via keysend:

* C-Otto: `027ce055380348d7812d2ae7745701c9f93e70c1adeb2657f053f91df4f2843c71@137.226.34.46:9735`
* wamde: `0269b91661812bae52280a68eec2b89d38bf26b33966441ad70aa365e120a125ff@82.36.141.97:9735`