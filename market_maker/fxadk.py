"""BitMEX API Connector."""
from __future__ import absolute_import
import logging
from market_maker.ws.ws_thread import FxADKInterface
from builtins import str


class FxADK(object):

    """FxADK Connector"""

    def __init__(self, symbol=None):
        """Init connector."""
        self.logger = logging.getLogger('root')
        self.symbol = symbol
        self.ws = FxADKInterface()

    def __del__(self):
        self.exit()

    def exit(self):
        self.ws.exit()

    #
    # Public methods
    #
    def ticker_data(self, symbol=None):
        """Get ticker data."""
        if symbol is None:
            symbol = self.symbol
        return self.ws.get_ticker(symbol)

    def instrument(self, symbol=None):
        """Get an instrument's details."""
        if symbol is None:
            symbol = self.symbol
        return self.ws.get_instrument(symbol)

    def instruments(self, filter=None):
        if filter is None:
            filter = self.symbol
        return self.ws.get_instrument(filter)  # I doubt we need this

    def market_depth(self, symbol=None):
        """Get market depth / orderbook."""
        if symbol is None:
            symbol = self.symbol
        return self.ws.market_depth(symbol)  # this is not implemented

    def recent_trades(self, symbol=None):
        """Get recent trades.

        Returns
        -------
        A list of dicts:
              {u'amount': 60,
               u'date': 1306775375,
               u'price': 8.7401099999999996,
               u'tid': u'93842'},

        """
        if symbol is None:
            symbol = self.symbol

        recent_trades = self.ws.recent_trades(symbol)

        return recent_trades

    def funds(self):
        """Get your current balance."""
        return self.ws.funds()
    
    def position(self, symbol=None, qty_only=False):
        """Get your open position."""
        if symbol is None:
            symbol = self.symbol
        return self.ws.position(symbol, qty_only=qty_only)

    def isolate_margin(self, symbol, leverage, rethrow_errors=False):
        raise NotImplementedError('There is no API call for this yet')

    def delta(self):
        raise NotImplementedError('There is no API call for this yet')
    
    def buy(self, quantity, price, symbol=None, order='limit'):
        """Place a buy order.

        Returns order object. ID: orderID
        """

        if price < 0:
            raise Exception("Price must be positive.")

        if quantity < 0:
            raise Exception("Quantity must be positive.")

        if symbol is None:
            symbol = self.symbol

        return self.ws.create_order(amount=quantity, price=price, order=order, type='buy', pair=symbol)
    
    def sell(self, quantity, price, symbol=None, order='limit'):
        """Place a sell order.

        Returns order object. ID: orderID
        """

        if price < 0:
            raise Exception("Price must be positive.")

        if quantity < 0:
            raise Exception("Quantity must be positive.")

        if symbol is None:
            symbol = self.symbol

        return self.ws.create_order(amount=quantity, price=price, order=order, type='sell', pair=symbol)
    
    def amend_bulk_orders(self, orders):
        """Amend multiple orders.

        Input is a list of dicts with the orderid and the new values
        [
            {
                'amount': 1.2,
                'price': 0.15,
                'symbol': 'ADK/BTC',
                'order': 'limit',  # it will default to limit if you don't pass this
                'orderid': 'sdfiouhsdfoiusdfoisud',
                'type': 'buy',
            }
        ]

        """
        self.ws.cancel_orders([o['orderid'] for o in orders])

        return self.create_bulk_orders(orders)

    def create_bulk_orders(self, orders):
        """Create multiple orders. Same format as above with no orderid"""

        orders_created = []

        for order in orders:
            try:
                orders_created.append(
                    self.ws.create_order(amount=order['amount'], price=order['price'], order=order.get('order', 'limit'), type=order['type'], pair=order.get('symbol', self.symbol))
                )
            except RuntimeError:
                continue  # failed to create this order, you probably don't have a high enough balance

        return orders_created

    def open_orders(self, symbol=None):
        """Get open orders."""
        if symbol is None:
            symbol = self.symbol
        return self.ws.open_orders(symbol)

    def http_open_orders(self):
        """Get open orders via HTTP. Used on close to ensure we catch them all."""
        return []  # this is not needed

    def cancel(self, orderIDs):
        """Cancel existing orders"""
        if isinstance(orderIDs, str):
            orderIDs = [orderIDs]

        self.ws.cancel_orders(orderIDs)
    
    def withdraw(self, amount, fee, address):
        raise NotImplementedError('No FxADK api call for this')