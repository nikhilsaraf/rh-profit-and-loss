import pandas as pd
import requests
import time
import datetime
import numpy as np
import sys
import pytz
import random
import json
import csv
import pandas as pd
pd.options.mode.chained_assignment = None  # default='warn', to silence the errors about copy
import Robinhood


folio = {}
# symbol -> [object]
# object: units, buy_price, buy_timestamp
profitm = {}
# symbol -> float

### ORDER HISTORY STUFF ###

def fetch_json_by_url(my_trader, url):
    return my_trader.session.get(url).json()

def get_symbol_from_instrument_url(url, df):

    try:
        symbol = df.loc[url]['symbol']
    
    except Exception as e:
        response = requests.get(url)
        symbol = response.json()['symbol']
        df.at[url, 'symbol'] = symbol
        # time.sleep(np.random.randint(low=0, high=2, size=(1))[0])
   
    return symbol, df


def printMaps():
    print('')
    
    print('folio')
    for symbol in sorted(folio):
        print(symbol, '--->', folio[symbol])
    print('')

    total_profit = 0.0
    print('profitm')
    for symbol in sorted(profitm):
        p = profitm[symbol]
        print(symbol, ',', p)
        total_profit += p
    print('')
    print('total_profit = {}'.format(total_profit))
    print('')

def order_item_info(order, my_trader, df):
    #side: .side,  price: .average_price, shares: .cumulative_quantity, instrument: .instrument, date : .last_transaction_at
    symbol, df = get_symbol_from_instrument_url(order['instrument'], df)

    symHistory = folio.get(symbol)
    if symHistory is None:
        symHistory = []
        profitm[symbol] = 0.0

    oside = order['side']
    for e in order['executions']:
        print(e['timestamp'], e['id'], symbol, order['id'], order['side'], order['type'], e['price'], e['quantity'])

        ep = float(e['price'])
        eq = float(e['quantity'])
        if oside == 'buy':
            symHistory.append({ 'price': ep, 'quantity': eq, 'timestamp': e['timestamp'] })
        else:   # consume from symHistory
            while len(symHistory) > 0 and eq > 0:
                obj = symHistory[0]
                if obj['quantity'] >= eq:
                    profitm[symbol] += (eq * (ep - obj['price']))
                    obj['quantity'] -= eq
                    eq = 0

                    if obj['quantity'] == 0:
                        symHistory.pop(0)
                else:
                    profitm[symbol] += (obj['quantity'] * (ep - obj['price']))
                    eq -= obj['quantity']
                    obj['quantity'] = 0
                    symHistory.pop(0)

            if len(symHistory) == 0 and eq > 0:
                print('*******************************************************************')
                print('error, len(symHistory) == 0 and eq = {} for last trade'.format(eq))
                print('*******************************************************************')
                # NS don't throw here - we encounter this with SCHW which was converted from TDA so has no history but is still in the account
                # raise Exception()
        folio[symbol] = symHistory
        
        if order['state'] != 'filled':
            print('state not \'filled\' ({}) but we have {} executions (last one printed above).'.format(order['state'], len(order['executions'])))
            # NS dont throw here - this is not correct, cancelled orders can be partially filled before cancellation
            #raise Exception()

        # printmaps after every execution
        printMaps()
    
    order_info_dict = {
        'side': order['side'],
        'avg_price': order['average_price'],
        'order_price': order['price'],
        'order_quantity': order['quantity'],
        'shares': order['cumulative_quantity'],
        'symbol': symbol,
        'id': order['id'],
        'date': order['last_transaction_at'],
        'state': order['state'],
        'type': order['type']
    }

    return order_info_dict

def get_all_history_orders(my_trader):
    
    orders = []
    past_orders = my_trader.order_history()
    orders.extend(past_orders['results'])

    while past_orders['next']:
        # print("{} order fetched".format(len(orders)))
        next_url = past_orders['next']
        past_orders = fetch_json_by_url(my_trader, next_url)
        orders.extend(past_orders['results'])
    # print("{} order fetched".format(len(orders)))

    return orders

def mark_pending_orders(row):
    if row.state == 'queued' or row.state == 'confirmed':
        order_status_is_pending = True
    else:
        order_status_is_pending = False
    return order_status_is_pending
# df_order_history.apply(mark_pending_orders, axis=1)    

def get_order_history(my_trader):
    
    # Get unfiltered list of order history
    past_orders = get_all_history_orders(my_trader)

    # Load in our pickled database of instrument-url lookups
    instruments_df = pd.read_pickle('symbol_and_instrument_urls')

    # Create a big dict of order history
    orders = [order_item_info(order, my_trader, instruments_df) for order in reversed(past_orders)]

    # Save our pickled database of instrument-url lookups
    instruments_df.to_pickle('symbol_and_instrument_urls')

    df = pd.DataFrame.from_records(orders)
    df['ticker'] = df['symbol']

    columns = ['ticker', 'state', 'order_quantity', 'shares', 'avg_price', 'date', 'id', 'order_price', 'side', 'symbol', 'type']
    df = df[columns]

    df['is_pending'] = df.apply(mark_pending_orders, axis=1)

    return df, instruments_df

def get_all_history_options_orders(my_trader):

    options_orders = []
    past_options_orders = my_trader.options_order_history()
    options_orders.extend(past_options_orders['results'])

    while past_options_orders['next']:
        # print("{} order fetched".format(len(orders)))
        next_url = past_options_orders['next']
        past_options_orders = fetch_json_by_url(my_trader, next_url)
        options_orders.extend(past_options_orders['results'])
    # print("{} order fetched".format(len(orders)))
    
    options_orders_cleaned = []
    
    for each in options_orders:
        if float(each['processed_premium']) < 1:
            continue
        else:
#             print(each['chain_symbol'])
#             print(each['processed_premium'])
#             print(each['created_at'])
#             print(each['legs'][0]['position_effect'])
#             print("~~~")
            if each['legs'][0]['position_effect'] == 'open':
                value = round(float(each['processed_premium']), 2)*-1
            else:
                value = round(float(each['processed_premium']), 2)
                
            one_order = [pd.to_datetime(each['created_at']), each['chain_symbol'], value, each['legs'][0]['position_effect']]
            options_orders_cleaned.append(one_order)
    
    df_options_orders_cleaned = pd.DataFrame(options_orders_cleaned)
    df_options_orders_cleaned.columns = ['date', 'ticker', 'value', 'position_effect']
    df_options_orders_cleaned = df_options_orders_cleaned.sort_values('date')
    df_options_orders_cleaned = df_options_orders_cleaned.set_index('date')

    return df_options_orders_cleaned


### END ORDER HISTORY GETTING STUFF ####
