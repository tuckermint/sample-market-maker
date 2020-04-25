import sys
import threading
import traceback
import ssl
from time import sleep
import json
import decimal
import logging
from market_maker.settings import settings
from market_maker.auth.APIKeyAuth import generate_expires, generate_signature
from market_maker.utils.log import setup_custom_logger
from market_maker.utils.math import toNearest
from future.utils import iteritems
from .fxadk_impl import FxAdkImpl
from future.standard_library import hooks
with hooks():  # Python 2/3 compat
    from urllib.parse import urlparse, urlunparse

# FxADK REST API stuffed into Bitmex Websocket format


class FxADKInterface:
    def __init__(self):
        self.logger = logging.getLogger('root')
        self.__reset()
        self.fx_adk_api = FxAdkImpl(settings.API_KEY, settings.API_SECRET)

    def __del__(self):
        self.exit()

    def connect(self, endpoint=None, symbol=None, shouldAuth=False):
        pass

    #
    # Data methods
    #
    @staticmethod
    def get_bid_or_ask(orders, last_price):
        for order in orders:
            if 'total' in order and float(order['total']):
                return float(order['price'])

        return last_price

    def get_instrument(self, symbol):
        pair_details = self.fx_adk_api.get_pair_details(symbol)
        buy_orders = self.fx_adk_api.get_buy_orders(symbol)
        sell_orders = self.fx_adk_api.get_sell_orders(symbol)

        # last from pair details
        last = float(pair_details['message']['trade_data']['lastprice'])

        # bid from buy orders
        buy_order_list = buy_orders['message']['buy_orders']
        bid = self.get_bid_or_ask(buy_order_list, last)

        # ask from sell orders
        sell_order_list = sell_orders['message']['sell_orders']
        ask = self.get_bid_or_ask(sell_order_list, last)

        return {
            'symbol': symbol,
            'instrument': symbol,
            'lastPrice': last,
            'bidPrice': bid,
            'askPrice': ask,
            'midPrice': (bid + ask) / 2,
            'tickSize': 0.00000001,
        }

    def get_ticker(self, symbol):
        '''Return a ticker object. Generated from instrument.'''

        instrument = self.get_instrument(symbol)

        bid = instrument['bidPrice']
        ask = instrument['askPrice']
        mid = instrument['midPrice']

        ticker = {
            "last": instrument['lastPrice'],
            "buy": bid,
            "sell": ask,
            "mid": mid,
        }

        return ticker

    def funds(self):
        return self.fx_adk_api.get_account_balance()['message']

    def market_depth(self, symbol):
        raise NotImplementedError('orderBook is not subscribed; use askPrice and bidPrice on instrument')

    def open_orders(self, symbol):
        res = self.fx_adk_api.get_open_orders(symbol)['message']

        if res == 'No elements to show':
            return []

        for order in res:
            order['amount'] = float(order['amount'])
            order['price'] = float(order['price'])
            order['total'] = float(order['total'])
            order['type'] = order['type'].lower()

        return res

    def position(self, symbol, qty_only=False):
        # get current quantity of first asset in pair

        asset_symbol = symbol.split('/')[0]

        funds = self.funds()

        current_qty = 0.0

        for fund in funds:
            if fund['symbol'] == asset_symbol:
                current_qty = float(fund['balance'])
                break

        if qty_only:
            return {'currentQty': current_qty, 'symbol': symbol}

        # get average cost based on pair trading history
        trades = self.recent_trades(symbol)

        total_cost = 0.0
        quantity_reviewed = 0.0

        for trade in trades:
            if trade['type'] != 'buy':
                continue  # this trade won't give us info about average cost

            total_cost += float(trade['total'])
            total_cost += float(trade['fees'])  # include fees in cost calculation

            quantity_reviewed += float(trade['amount'])

            if quantity_reviewed >= current_qty:
                break  # these trades already cover the current quantity on hand

        average_cost = total_cost / quantity_reviewed if quantity_reviewed else 0.0

        return {'avgCostPrice': average_cost, 'avgEntryPrice': average_cost, 'currentQty': current_qty, 'symbol': symbol}

    def recent_trades(self, symbol):
        res = self.fx_adk_api.get_trade_history(symbol)['message']

        if res == 'No elements to show':
            return []

        for recent_trade in res:
            recent_trade['type'] = recent_trade['type'].lower()

        return res

    def cancel_orders(self, order_ids):
        for order_id in order_ids:
            self.fx_adk_api.cancel_order(order_id)

    def create_order(self, amount=0.0, price=0.0, order='limit', type='buy', pair='ADK/BTC'):
        return self.fx_adk_api.create_order(amount=amount, price=price, order=order, type=type, pair=pair)

    #
    # Lifecycle methods
    #
    def error(self, err):
        self._error = err
        self.logger.error(err)
        self.exit()

    def exit(self):
        self.exited = True

    #
    # Private methods
    #

    def __connect(self, wsURL):
        pass

    def __get_auth(self):
        pass

    def __wait_for_account(self):
        pass

    def __wait_for_symbol(self, symbol):
        pass

    def __send_command(self, command, args):
        pass

    def __on_message(self, message):
        pass

    def __on_open(self):
        pass

    def __on_close(self):
        self.exit()

    def __on_error(self, error):
        if not self.exited:
            self.error(error)

    def __reset(self):
        self.data = {}
        self.keys = {}
        self.exited = False
        self._error = None


if __name__ == "__main__":
    # create console handler and set level to debug
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    # create formatter
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    # add formatter to ch
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    ws = FxADKInterface()
    ws.logger = logger

