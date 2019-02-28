# rebalance-lnd

Using this script you can easily rebalance individual channels of your lnd node.

## Installation

This script needs an active lnd (https://github.com/lightningnetwork/lnd) instance running.
You need to have admin rights to control this node.
By default this script connects to `localhost:10009`, using the macaroon file in `~/.lnd/data/chain/bitcoin/mainnet/admin.macaroon`.
If you need to change this, please have a look at the sources.

You need to install Python. The gRPC dependencies can be installed by running:

```
$ pip install -r requirements.txt
```

## Usage

### Command line arguments
```
usage: rebalance.py [-h] [-r RATIO] [-l] [-o | -i] [-f CHANNEL] [-t CHANNEL]
                    [-a AMOUNT]

optional arguments:
  -h, --help            show this help message and exit
  -r RATIO, --ratio RATIO
                        ratio for channel imbalance between 1 and 50%, eg. 45
                        for 45%

list candidates:
  Show the unbalanced channels.

  -l, --list-candidates
                        list candidate channels for rebalance
  -o, --outgoing        lists channels with more than 50% of the funds on the
                        local side
  -i, --incoming        (default) lists channels with more than 50% of the
                        funds on the remote side

rebalance:
  Rebalance a channel. You need to specify at least the 'to' channel (-t).

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
```

### List of channels
Run `rebalance.py -l` (or `rebalance.py -l -i`) to see a list of channels which can be rebalanced.
This list only contains channels where more than 50% of the total funds are on the remote side of the channel.  

You can also see the list of channels where more than 50% of the total funds are on the local side of the channel by running `rebalance.py -l -o`.

Use `-r/--ratio` to configure the sensitivity ratio (default is 50%).

As an example the following indicates a channel with around 17.7% of the funds on the local side:

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
To actually rebalance a channel, run the script and specify the channel to send funds to using `-t`.
Optionally you can also specify the channel to take the funds from (using `-f`), and the amount to send (using `-a`).
You specify the channel(s) using the channel ID, as shown in the output of `rebalance.py`.

`rebalance.py -t 123[...]456 -a 1613478`

It is also possible to indicate the `--to/-t` channel by the number shown next to the channel ID (23 in the example).

`rebalance.py -t 23 -a 1613478`

If you do not specify the amount, the rebalance amount for the destination channel (`-t`) is determined automatically.

If you specify a channel using `-f`, the funds are taken from that channel. 

The maximum amount you can send in one transaction currently is limited (by the protocol) to 4,294,967 satoshis.

## Contributing

Contributions are highly welcome!
Feel free to submit issues and pull requests on https://github.com/C-Otto/rebalance-lnd/

Please also consider opening a channel with one of our nodes:

* C-Otto: `027ce055380348d7812d2ae7745701c9f93e70c1adeb2657f053f91df4f2843c71@137.226.34.46:9735`
* wamde: `0269b91661812bae52280a68eec2b89d38bf26b33966441ad70aa365e120a125ff@82.36.141.97:9735`
