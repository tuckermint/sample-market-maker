from __future__ import absolute_import
from time import sleep
import sys
from datetime import datetime
from os.path import getmtime
import random
import requests
import atexit
import signal

from market_maker import fxadk
from market_maker.settings import settings
from market_maker.utils import log, constants, errors, math

# Used for reloading the bot - saves modified times of key files
import os
watched_files_mtimes = [(f, getmtime(f)) for f in settings.WATCHED_FILES]


#
# Helpers
#
logger = log.setup_custom_logger('root')


class ExchangeInterface:
    def __init__(self, dry_run=False):
        self.dry_run = dry_run
        if len(sys.argv) > 1:
            self.symbol = sys.argv[1]
        else:
            self.symbol = settings.SYMBOL
        self.fxadk = fxadk.FxADK(symbol=self.symbol)

    def cancel_order(self, order_id):
        logger.info("Canceling: %s" % order_id)
        while True:
            try:
                self.fxadk.cancel(order_id)
            except ValueError as e:
                logger.info(e)
                sleep(settings.API_ERROR_INTERVAL)
            else:
                break

    def cancel_all_orders(self):
        if self.dry_run:
            return

        logger.info("Resetting current position. Canceling all existing orders.")

        current_order_ids = [o['orderid'] for o in self.get_orders()]

        for order_id in current_order_ids:
            logger.info("Canceling: %s" % order_id)

        if len(current_order_ids):
            self.fxadk.cancel(current_order_ids)

    def get_portfolio(self):
        funds = self.fxadk.funds()
        return funds

    def calc_delta(self):
        """Calculate currency delta for portfolio"""
        raise NotImplementedError('This is not implemented')

    def get_delta(self, symbol=None):
        if symbol is None:
            symbol = self.symbol

        qty = self.get_position(symbol, qty_only=True)['currentQty']
        return qty

    def get_instrument(self, symbol=None):
        if symbol is None:
            symbol = self.symbol

        instrument = self.fxadk.instrument(symbol)
        return instrument

    def get_margin(self):
        if self.dry_run:
            return [
                {'symbol': 'BTC', 'balance': float(settings.DRY_BTC)}
            ]

        funds = self.fxadk.funds()
        return funds

    def get_orders(self):
        if self.dry_run:
            return []

        open_orders = self.fxadk.open_orders()

        return open_orders

    def get_recent_trades(self, symbol=None):
        if symbol is None:
            symbol = self.symbol

        return self.fxadk.recent_trades(symbol)

    def get_highest_buy(self, recent_trades):
        if not len(recent_trades):
            return {'price': -2**32}

        buys = [o for o in recent_trades if o['type'] == 'buy']

        for buy in buys:
            buy['price'] = float(buy['price'])

        smallest_val = {'price': -2**32}
        highest_buy = max(buys, key=lambda o: o['price']) if buys else smallest_val
        return highest_buy if highest_buy else smallest_val

    def get_lowest_sell(self, recent_trades):
        if not len(recent_trades):
            return {'price': 2 ** 32}

        sells = [o for o in recent_trades if o['type'] == 'sell']

        for sell in sells:
            sell['price'] = float(sell['price'])

        biggest_val = {'price': 2 ** 32}
        lowest_sell = min(sells, key=lambda o: o['price']) if sells else biggest_val
        return lowest_sell if lowest_sell else biggest_val

    def get_position(self, symbol=None, qty_only=False):
        if symbol is None:
            symbol = self.symbol

        position = self.fxadk.position(symbol, qty_only=qty_only)
        return position

    def get_ticker(self, symbol=None):
        if symbol is None:
            symbol = self.symbol

        ticker = self.fxadk.ticker_data(symbol)
        return ticker

    def is_open(self):
        """Check that websockets are still open."""
        return True  # it's not a real websocket

    def check_market_open(self):
        pass  # this is not implemented

    def check_if_orderbook_empty(self):
        """This function checks whether the order book is empty"""
        instrument = self.get_instrument()

        if instrument['midPrice'] is None:
            raise errors.MarketEmptyError("Orderbook is empty, cannot quote")

        return instrument

    def amend_bulk_orders(self, orders):
        if self.dry_run:
            return orders

        self.fxadk.amend_bulk_orders(orders)

    def create_bulk_orders(self, orders):
        if self.dry_run:
            return orders

        self.fxadk.create_bulk_orders(orders)

    def cancel_bulk_orders(self, orders):
        if self.dry_run:
            return orders

        current_order_ids = [order['orderid'] for order in orders]
        self.fxadk.cancel(current_order_ids)


class OrderManager:
    def __init__(self):
        self.exchange = ExchangeInterface(settings.DRY_RUN)
        # Once exchange is created, register exit handler that will always cancel orders
        # on any error.
        atexit.register(self.exit)
        signal.signal(signal.SIGTERM, self.exit)

        logger.info("Using symbol %s." % self.exchange.symbol)

        if settings.DRY_RUN:
            logger.info("Initializing dry run. Orders printed below represent what would be posted to FxADK.")
        else:
            logger.info("Order Manager initializing, connecting to FxADK. Live run: executing real trades.")

        self.start_time = datetime.now()
        self.instrument = self.exchange.get_instrument()
        self.starting_qty = self.exchange.get_delta()
        self.running_qty = self.starting_qty
        self.reset()

    def reset(self):
        self.exchange.cancel_all_orders()
        position = self.sanity_check()
        self.print_status(position)

        # Create orders and converge.
        self.place_orders(position)

    def print_status(self, position):
        """Print the current MM status."""

        self.running_qty = position['currentQty']  # this was get_delta

        logger.info("Current Contract Position: %d" % self.running_qty)
        if settings.CHECK_POSITION_LIMITS:
            logger.info("Position limits: %d/%d" % (settings.MIN_POSITION, settings.MAX_POSITION))
        if position['currentQty'] != 0:
            logger.info("Avg Cost Price: %f" % float(position['avgCostPrice']))
            logger.info("Avg Entry Price: %f" % float(position['avgEntryPrice']))
        logger.info("Contracts Traded This Run: %d" % (self.running_qty - self.starting_qty))

    def get_ticker(self, ticker):
        # Set up our buy & sell positions as the smallest possible unit above and below the current spread
        # and we'll work out from there. That way we always have the best price but we don't kill wide
        # and potentially profitable spreads.
        self.start_position_buy = ticker["buy"] + self.instrument['tickSize']
        self.start_position_sell = ticker["sell"] - self.instrument['tickSize']

        # If we're maintaining spreads and we already have orders in place,
        # make sure they're not ours. If they are, we need to adjust, otherwise we'll
        # just work the orders inward until they collide.

        recent_trades = self.exchange.get_recent_trades()

        if settings.MAINTAIN_SPREADS:
            if ticker['buy'] == self.exchange.get_highest_buy(recent_trades)['price']:
                self.start_position_buy = ticker["buy"]
            if ticker['sell'] == self.exchange.get_lowest_sell(recent_trades)['price']:
                self.start_position_sell = ticker["sell"]

        # Back off if our spread is too small.
        if self.start_position_buy * (1.00 + settings.MIN_SPREAD) > self.start_position_sell:
            self.start_position_buy *= (1.00 - (settings.MIN_SPREAD / 2))
            self.start_position_sell *= (1.00 + (settings.MIN_SPREAD / 2))

        # Midpoint, used for simpler order placement.
        self.start_position_mid = ticker["mid"]
        logger.info(
            "%s Ticker: buy: %f, sell: %f" %
            (self.instrument['symbol'], ticker["buy"], ticker["sell"])
        )
        logger.info('Start Positions: buy: %f, sell: %f, Mid: %f' %
                    (self.start_position_buy, self.start_position_sell,
                     self.start_position_mid))
        return ticker

    def get_price_offset(self, index):
        """Given an index (1, -1, 2, -2, etc.) return the price for that side of the book.
           Negative is a buy, positive is a sell."""
        # Maintain existing spreads for max profit
        if settings.MAINTAIN_SPREADS:
            start_position = self.start_position_buy if index < 0 else self.start_position_sell
            # First positions (index 1, -1) should start right at start_position, others should branch from there
            index = index + 1 if index < 0 else index - 1
        else:
            # Offset mode: ticker comes from a reference exchange and we define an offset.
            start_position = self.start_position_buy if index < 0 else self.start_position_sell

            # If we're attempting to sell, but our sell price is actually lower than the buy,
            # move over to the sell side.
            if index > 0 and start_position < self.start_position_buy:
                start_position = self.start_position_sell
            # Same for buys.
            if index < 0 and start_position > self.start_position_sell:
                start_position = self.start_position_buy

        return math.toNearest(start_position * (1 + settings.INTERVAL) ** index, self.instrument['tickSize'])

    ###
    # Orders
    ###

    def place_orders(self, position):
        """Create order items for use in convergence."""

        buy_orders = []
        sell_orders = []
        # Create orders from the outside in. This is intentional - let's say the inner order gets taken;
        # then we match orders from the outside in, ensuring the fewest number of orders are amended and only
        # a new order is created in the inside. If we did it inside-out, all orders would be amended
        # down and a new order would be created at the outside.

        delta = position['currentQty']
        long_position_exceeded = self.long_position_limit_exceeded(delta)
        short_position_exceeded = self.short_position_limit_exceeded(delta)

        for i in reversed(range(1, settings.ORDER_PAIRS + 1)):
            if not long_position_exceeded:
                buy_orders.append(self.prepare_order(-i))
            if not short_position_exceeded:
                sell_orders.append(self.prepare_order(i))

        return self.converge_orders(buy_orders, sell_orders)

    def prepare_order(self, index):
        """Create an order object."""

        if settings.RANDOM_ORDER_SIZE is True:
            quantity = random.randint(settings.MIN_ORDER_SIZE, settings.MAX_ORDER_SIZE)
        else:
            quantity = settings.ORDER_START_SIZE + ((abs(index) - 1) * settings.ORDER_STEP_SIZE)

        price = self.get_price_offset(index)

        return {
            'amount': quantity,
            'price': price,
            'symbol': self.instrument['symbol'],
            'order': 'limit',
            'type': "buy" if index < 0 else "sell",
        }

    def converge_orders(self, buy_orders, sell_orders):
        """Converge the orders we currently have in the book with what we want to be in the book.
           This involves amending any open orders and creating new ones if any have filled completely.
           We start from the closest orders outward."""

        to_amend = []
        to_create = []
        to_cancel = []
        buys_matched = 0
        sells_matched = 0
        existing_orders = self.exchange.get_orders()

        # Check all existing orders and match them up with what we want to place.
        # If there's an open one, we might be able to amend it to fit what we want.
        for order in existing_orders:
            try:
                if order['type'] == 'buy':
                    desired_order = buy_orders[buys_matched]
                    buys_matched += 1
                else:
                    desired_order = sell_orders[sells_matched]
                    sells_matched += 1

                # Found an existing order. Do we need to amend it?
                if desired_order['amount'] != order['amount'] or (
                        # If price has changed, and the change is more than our RELIST_INTERVAL, amend.
                        desired_order['price'] != order['price'] and
                        abs((desired_order['price'] / order['price']) - 1) > settings.RELIST_INTERVAL):
                    to_amend.append({'orderid': order['orderid'], 'amount': order['amount'] + desired_order['amount'],
                                     'price': desired_order['price'], 'type': order['type']})
            except IndexError:
                # Will throw if there isn't a desired order to match. In that case, cancel it.
                to_cancel.append(order)

        while buys_matched < len(buy_orders):
            to_create.append(buy_orders[buys_matched])
            buys_matched += 1

        while sells_matched < len(sell_orders):
            to_create.append(sell_orders[sells_matched])
            sells_matched += 1

        if len(to_amend) > 0:
            for amended_order in reversed(to_amend):
                reference_order = [o for o in existing_orders if o['orderid'] == amended_order['orderid']][0]
                logger.info("Amending %4s: %d @ %f to %d @ %f (%f)" % (
                    amended_order['type'],
                    reference_order['amount'], reference_order['price'],
                    (amended_order['amount'] - reference_order['amount']), amended_order['price'],
                    (amended_order['price'] - reference_order['price'])
                ))
            # This can fail if an order has closed in the time we were processing.
            # The API will send us `invalid ordStatus`, which means that the order's status (Filled/Canceled)
            # made it not amendable.
            # If that happens, we need to catch it and re-tick.
            try:
                self.exchange.amend_bulk_orders(to_amend)
            except requests.exceptions.HTTPError as e:
                errorObj = e.response.json()
                logger.error("Unknown error on amend: %s. Exiting" % errorObj)
                sys.exit(1)

        if len(to_create) > 0:
            logger.info("Creating %d orders:" % (len(to_create)))
            for order in reversed(to_create):
                logger.info("%4s %d @ %f" % (order['type'], order['amount'], order['price']))
            self.exchange.create_bulk_orders(to_create)

        # Could happen if we exceed a delta limit
        if len(to_cancel) > 0:
            logger.info("Canceling %d orders:" % (len(to_cancel)))
            for order in reversed(to_cancel):
                logger.info("%4s %d @ %f" % (order['type'], order['amount'], order['price']))
            self.exchange.cancel_bulk_orders(to_cancel)

    ###
    # Position Limits
    ###

    def short_position_limit_exceeded(self, position):
        """Returns True if the short position limit is exceeded"""
        if not settings.CHECK_POSITION_LIMITS:
            return False

        return position <= settings.MIN_POSITION

    def long_position_limit_exceeded(self, position):
        """Returns True if the long position limit is exceeded"""
        if not settings.CHECK_POSITION_LIMITS:
            return False
        return position >= settings.MAX_POSITION

    ###
    # Sanity
    ##
    @staticmethod
    def convert_instrument_to_ticker(instrument):
        return {
            "last": instrument['lastPrice'],
            "buy": instrument['bidPrice'],
            "sell": instrument['askPrice'],
            "mid": instrument['midPrice'],
        }

    def sanity_check(self):
        """Perform checks before placing orders."""

        # Check if OB is empty - if so, can't quote.
        instrument = self.exchange.check_if_orderbook_empty()

        # Get ticker, which sets price offsets and prints some debugging info.
        ticker = self.convert_instrument_to_ticker(instrument)
        ticker = self.get_ticker(ticker)

        # Sanity check:
        if self.get_price_offset(-1) >= ticker["sell"] or self.get_price_offset(1) <= ticker["buy"]:
            logger.error("buy: %s, sell: %s" % (self.start_position_buy, self.start_position_sell))
            logger.error("First buy position: %s\nFxADK Best Ask: %s\nFirst sell position: %s\nFxADK Best Bid: %s" %
                         (self.get_price_offset(-1), ticker["sell"], self.get_price_offset(1), ticker["buy"]))
            logger.error("Sanity check failed, exchange data is inconsistent")
            self.exit()

        position = self.exchange.get_position()
        delta = position['currentQty']

        # Messaging if the position limits are reached
        if self.long_position_limit_exceeded(delta):
            logger.info("Long delta limit exceeded")
            logger.info("Current Position: %.f, Maximum Position: %.f" %
                        (delta, settings.MAX_POSITION))

        if self.short_position_limit_exceeded(delta):
            logger.info("Short delta limit exceeded")
            logger.info("Current Position: %.f, Minimum Position: %.f" %
                        (delta, settings.MIN_POSITION))

        return position

    ###
    # Running
    ###

    def check_file_change(self):
        """Restart if any files we're watching have changed."""
        for f, mtime in watched_files_mtimes:
            if getmtime(f) > mtime:
                self.restart()

    def check_connection(self):
        """Ensure the WS connections are still open."""
        return True  # it's not a real websocket

    def exit(self):
        logger.info("Shutting down. All open orders will be cancelled.")
        try:
            self.exchange.cancel_all_orders()
            self.exchange.fxadk.exit()
        except errors.AuthenticationError as e:
            logger.info("Was not authenticated; could not cancel orders.")
        except Exception as e:
            logger.info("Unable to cancel orders: %s" % e)

        sys.exit()

    def run_loop(self):
        while True:
            sys.stdout.write("-----\n")
            sys.stdout.flush()

            self.check_file_change()
            sleep(settings.LOOP_INTERVAL)

            position = self.sanity_check()  # Ensures health of mm - several cut-out points here
            self.print_status(position)  # Print skew, delta, etc
            self.place_orders(position)  # Creates desired orders and converges to existing orders

    def restart(self):
        logger.info("Restarting the market maker...")
        os.execv(sys.executable, [sys.executable] + sys.argv)

#
# Helpers
#


def run():
    logger.info('FxADK Market Maker Version: %s\n' % constants.VERSION)

    om = OrderManager()
    # Try/except just keeps ctrl-c from printing an ugly stacktrace
    try:
        om.run_loop()
    except (KeyboardInterrupt, SystemExit):
        sys.exit()
