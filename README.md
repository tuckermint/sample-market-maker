# FxADK Market Maker

This is a sample market making bot for use with [FxADK](https://fxadk.com/).

It is free to use and modify for your own strategies.

> FxADK is not responsible for any losses incurred when using this code. This code is intended for sample purposes ONLY - do not
  use this code for real trades unless you fully understand what it does and what its caveats are.

> This is not a sophisticated market making program. It is intended to show the basics of market making while abstracting some
  of the rote work of interacting with the FxADK API. It does not make smart decisions and will likely lose money.

## Getting Started

1. Install Python3 on Linux, Mac OS X, or Windows Subsystem for Linux.
2. Install git
3. Run "git clone https://github.com/tuckermint/sample-market-maker.git"
4. Create an account on FxADK and request API credentials.
5. run `python3 marketmaker setup`
    * This will create `settings.py` and `market_maker/` in the working directory.
    * Modify `settings.py` to tune parameters.
6. Edit `settings.py` to add your FxADK API Key and Secret and change bot parameters.
    * Note that user/password authentication is not supported.
    * Run with `DRY_RUN=True` to test cost and spread.
7. Run it: `python3 marketmaker [symbol]`. For example, `python3 marketmaker ADK/USDT`.


## Operation Overview

This market maker works on the following principles:

* The market maker tracks the last `bidPrice` and `askPrice` of the quoted instrument to determine where to start quoting.
* Based on parameters set by the user, the bot creates a descriptions of orders it would like to place.
  - If `settings.MAINTAIN_SPREADS` is set, the bot will start inside the current spread and work outwards.
  - Otherwise, spread is determined by interval calculations.
* If the user specifies position limits, these are checked. If the current position is beyond a limit,
  the bot stops quoting that side of the market.
* These order descriptors are compared with what the bot has currently placed in the market.
  - If an existing order can be amended to the desired value, it is amended.
  - Otherwise, a new order is created.
  - Extra orders are canceled.
* The bot then prints details of contracts traded, tickers, and total delta.

## Advanced usage

You can implement custom trading strategies using the market maker. `market_maker.OrderManager`
controls placing, updating, and monitoring orders on FxADK. To implement your own custom
strategy, subclass `market_maker.OrderManager` and override `OrderManager.place_orders()`:

```
from market_maker.market_maker import OrderManager

class CustomOrderManager(OrderManager):
    def place_orders(self) -> None:
        # implement your custom strategy here
```

Your strategy should provide a set of orders. An order is a dict containing price, quantity, and
whether the order is buy or sell. For example:

```
 buy_order = {
     'amount': 1.2,  # float
     'price': 0.15,  # float
     'symbol': 'ADK/BTC',
     'order': 'limit',  # it will default to limit if you don't pass this
     'type': 'buy',
 }
 
 sell_order = {
     'amount': 1.2,  # float
     'price': 0.15,  # float
     'symbol': 'ADK/BTC',
     'order': 'limit',  # it will default to limit if you don't pass this
     'type': 'sell',
 } 
```

Call `self.converge_orders()` to submit your orders. `converge_orders()` will create, amend,
and delete orders on BitMEX as necessary to match what you pass in:

```
def place_orders(self) -> None:
    buy_orders = []
    sell_orders = []

    # populate buy and sell orders, e.g.
    buy_orders.append(order)
    buy_orders.append(order_2)
    sell_orders.append(order_3)
    sell_orders.append(order_4)

    self.converge_orders(buy_orders, sell_orders)
```

To run your strategy, call `run_loop()`:
```
order_manager = CustomOrderManager()
order_manager.run_loop()
```

Your custom strategy will run until you terminate the program with CTRL-C. There is an example
in `custom_strategy.py`.

## Notes on Rate Limiting

By default, the FxADK API rate limit is 20 requests per 1 minute interval.


## Troubleshooting

Common errors we've seen:

* `TypeError: __init__() got an unexpected keyword argument 'json'`
  * This is caused by an outdated version of `requests`. Run `pip install -U requests` to update.

## Compatibility

This module supports Python 3.5 and later.
