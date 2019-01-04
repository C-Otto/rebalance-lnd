# rebalance-lnd

Using this script you can easily rebalance individual channels of your lnd node.

## Installation

This script needs an active lnd (https://github.com/lightningnetwork/lnd) instance running.
You need to have admin rights to control this node.
By default this script connects to `localhost:10009`, using the macaroon file in `~/.lnd/data/chain/bitcoin/mainnet/admin.macaroon`.
If you need to change this, please have a look at the sources.

You need to install the gRPC dependencies for Python:

```
$ pip install grpcio googleapis-common-protos
```

## Usage

### Command line arguments
```
usage: rebalance.py [-h] [-l] [-o | -i] [-f FROMCHAN] [-t TOCHAN] [amount]

positional arguments:
  amount                Amount of the rebalance, in satoshis. If not
                        specified, the amount computed for a perfect rebalance
                        will be used (up to the maximum of 16,777,215
                        satoshis)

optional arguments:
  -h, --help            show this help message and exit
  -l, --list-candidates
                        List candidate channels for rebalance. Use in
                        conjunction with -o and -i
  -o, --outgoing        When used with -l, lists candidate outgoing channels
  -i, --incoming        When used with -l, lists candidate incoming channels
  -f FROMCHAN, --fromchan FROMCHAN
                        Channel id for the outgoing channel (which will be
                        emptied)
  -t TOCHAN, --tochan TOCHAN
                        Channel id for the incoming channel (which will be
                        filled)
```

### List of channels
Run `./rebalance.py` without any arguments to see a list of channels which can be rebalanced.
This list only contains channels where less than 50% of the total funds are on the local side of the channel.

As an example the following indicates a channel with around 17.7% of the funds on the local side:

```
(23) Pubkey:      012345[...]abcdef
Channel ID:       123[...]456
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

The number next to the pubkey (23 in the example) can be used to directly reference this channel.

### Rebalancing a channel
To actually rebalance a channel, run the script with two arguments.
The fist argument is the public key (pubkey) of the node at the other side of the channel, as shown in the output of `./rebalance.py`.
The second argument is the amount you want to send to yourself through that node.

`./rebalance.py 012345[...]abcdef 1613478`

It is also possible to indicate the channel by the number shown next to the Pubkey (23 in the example).

`./rebalance.py 23`

The maximum amount you can send in one transaction currently is limited (by the protocol) to 4294967 satoshis.

## Contributing

Contributions are highly welcome!
Feel free to submit issues and pull requests on https://github.com/C-Otto/rebalance-lnd/

Please also consider opening a channel with one of our nodes:

C-Otto: `027ce055380348d7812d2ae7745701c9f93e70c1adeb2657f053f91df4f2843c71@137.226.34.46:9735`

wamde: `0269b91661812bae52280a68eec2b89d38bf26b33966441ad70aa365e120a125ff@82.36.141.97:9735`
