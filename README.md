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

### List of channels
Run `./rebalance.py` without any arguments to see a list of channels which can be rebalanced.
This list only contains channels where less than 50% of the total funds are on the local side of the channel.

As an example the following indicates a channel with around 17.7% of the funds on the local side:

```
Pubkey:           012345[...]abcdef
Local ratio:      0.17689625535
Capacity:         5000000
Remote balance:   4110320
Local balance:    883364
Amount for 50-50: 1613478
|=====                       |
```

By sending 1613478 satoshis to yourself using this channel, a ratio of 50% can be achieved.
This number is shown as "Amount for 50-50".

The last line shows a graphical representation of the channel. 
The total width is determined by the channel's capacity, where a channel with maximum capacity (16777215 satoshis)
occupies the full width of your terminal.
The bar (`=`) indicates the funds on the local side of the channel.

### Rebalancing a channel
To actually rebalance a channel, run the script with two arguments.
The fist argument is the public key (pubkey) of the node at the other side of the channel, as shown in the output of `./rebalance.py`.
The second argument is the amount you want to send to yourself through that node.

The maximum amount you can send in one transaction currently is limited (by the protocol) to 4294967 satoshis.

## Contributing

Contributions are highly welcome!
Feel free to submit issues and pull requests on https://github.com/C-Otto/rebalance-lnd/

Please also consider opening a channel with my node:

027ce055380348d7812d2ae7745701c9f93e70c1adeb2657f053f91df4f2843c71@137.226.34.46:9735