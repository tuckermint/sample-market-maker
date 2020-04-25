import time
import requests

from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

from market_maker.settings import settings

# ----------------------------------------------------------------------------------------------------------------------
# Config

base_url = 'https://fxadk.com/api/'

session = requests.Session()
retries = Retry(total=5, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
session.mount('https://', HTTPAdapter(max_retries=retries))


# ----------------------------------------------------------------------------------------------------------------------
# Public API


class FxAdkImpl(object):
    def __init__(self, api_key, api_secret):
        self.api_key = api_key
        self.api_secret = api_secret
        self.max_attempts = 5

    def get_post_json_impl(self, url, data, attempt=1):
        if attempt > 1:
            print('Attempt %i' % attempt)

        try:
            res = session.post(url, data)
        except:
            time.sleep(settings.API_ERROR_INTERVAL)

            if attempt > self.max_attempts:
                raise

            return self.get_post_json_impl(url, data, attempt=attempt+1)

        try:
            return res.json()
        except:
            print('FxADK error: %s' % res.content)

            time.sleep(settings.API_ERROR_INTERVAL)

            if attempt > self.max_attempts:
                raise

            return self.get_post_json_impl(url, data, attempt=attempt+1)

    def get_post_json(self, url, data):
        print('Calling %s' % url)
        post_json = self.get_post_json_impl(url, data)
        time.sleep(settings.API_REST_INTERVAL)
        return post_json

    def get_currency_details(self, url='%s%s' % (base_url, 'getCurrencies')):
        data = {
            'api_key': self.api_key,
            'api_secret': self.api_secret,
        }
        
        res_json = self.get_post_json(url, data)
        return res_json

    def get_pair_details(self, pair='ADK/BTC', url='%s%s' % (base_url, 'getPairDetails')):
        data = {
            'api_key': self.api_key,
            'api_secret': self.api_secret,
            'pair': pair,
        }

        res_json = self.get_post_json(url, data)
        return res_json

    def get_market_history(self, pair='ADK/BTC', url='%s%s' % (base_url, 'getMarketHistory')):
        data = {
            'api_key': self.api_key,
            'api_secret': self.api_secret,
            'pair': pair,
        }
        
        res_json = self.get_post_json(url, data)
        return res_json

    def get_buy_orders(self, pair='ADK/BTC', url='%s%s' % (base_url, 'getBuyOrders')):
        data = {
            'api_key': self.api_key,
            'api_secret': self.api_secret,
            'pair': pair,
        }

        res_json = self.get_post_json(url, data)
        return res_json

    def get_sell_orders(self, pair='ADK/BTC', url='%s%s' % (base_url, 'getSellOrders')):
        data = {
            'api_key': self.api_key,
            'api_secret': self.api_secret,
            'pair': pair,
        }

        res_json = self.get_post_json(url, data)

        return res_json

    # ----------------------------------------------------------------------------------------------------------------------
    # Private API

    ORDER_ID_KEY = 'orderid'

    def create_order(self, amount=0.00000011, price=0.0, order='limit', type='buy', pair='ADK/BTC', url='%s%s' % (base_url, 'createOrder')):
        asset = pair.split('/')[0]

        pair = pair.replace('/', '_')  # this will probably not be needed in the future

        data = {
            'api_key': self.api_key,
            'api_secret': self.api_secret,
            'amount': amount,
            'price': price,
            'order': order,
            'type': type,
            'pair': pair,
        }
        
        res_json = self.get_post_json(url, data)

        if self.ORDER_ID_KEY in res_json:
            order_id = res_json[self.ORDER_ID_KEY]
            print('Created order %s' % order_id)
            return res_json  # return the whole order object

        print(res_json)
        raise RuntimeError('Failed to create order to %s %s %s' % (type, amount, asset))

    def cancel_order(self, order_id,  url='%s%s' % (base_url, 'cancelOrder')):
        data = {
            'api_key': self.api_key,
            'api_secret': self.api_secret,
            'orderid': order_id,
        }

        res_json = self.get_post_json(url, data)

        if res_json.get('status') != 'success':
            raise RuntimeError('Failed to cancel order %s' % order_id)

        print('Successfully cancelled order %s' % order_id)

    def get_trade_history(self, pair='ADK/BTC', url='%s%s' % (base_url, 'getTradeHistory')):
        data = {
            'api_key': self.api_key,
            'api_secret': self.api_secret,
            'pair': pair,
        }
        
        res_json = self.get_post_json(url, data)
        return res_json

    def get_cancel_history(self, pair='ADK/BTC', url='%s%s' % (base_url, 'getCancelHistory')):
        data = {
            'api_key': self.api_key,
            'api_secret': self.api_secret,
            'pair': pair,
        }

        res_json = self.get_post_json(url, data)
        return res_json

    def get_stop_orders(self, pair='ADK/BTC', url='%s%s' % (base_url, 'getStopOrders')):
        """These are active stop loss orders"""
        data = {
            'api_key': self.api_key,
            'api_secret': self.api_secret,
            'pair': pair,
        }
        
        res_json = self.get_post_json(url, data)
        return res_json

    def get_open_orders(self, pair='ADK/BTC', url='%s%s' % (base_url, 'getOpenOrders')):
        data = {
            'api_key': self.api_key,
            'api_secret': self.api_secret,
            'pair': pair,
        }

        res_json = self.get_post_json(url, data)
        return res_json

    def get_withdraw_history(self, url='%s%s' % (base_url, 'getWithdrawhistory')):
        data = {
            'api_key': self.api_key,
            'api_secret': self.api_secret,
        }

        res_json = self.get_post_json(url, data)
        return res_json

    def get_deposit_history(self, url='%s%s' % (base_url, 'getDeposithistory')):
        data = {
            'api_key': self.api_key,
            'api_secret': self.api_secret,
        }
        
        res_json = self.get_post_json(url, data)
        return res_json

    def get_account_balance(self, url='%s%s' % (base_url, 'getAccountbalance')):
        """Get account balance"""
        data = {
            'api_key': self.api_key,
            'api_secret': self.api_secret,
        }

        res_json = self.get_post_json(url, data)
        return res_json

