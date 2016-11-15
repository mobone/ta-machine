from indicators.sqz import stock
import pandas as pd
from datetime import datetime, timedelta, time
import calendar
import configparser
import MySQLdb

config = configparser.RawConfigParser()
config.read("sql_statements.cfg")

con = MySQLdb.connect(host="192.168.1.20", user="user", passwd="cookie", db="options")
cur = con.cursor()

tickers = pd.read_csv('trader_input.csv')
total_trades_df = []

for i in tickers.iterrows():
    symbol = i[1]['Symbol']
    list_type = i[1]['list_type']
    
    df = stock(symbol).df

    pd.set_option('display.max_rows', len(df))

    trade = 'Put'
    prev_trade = None

    trades_df = pd.DataFrame(columns=['Date', 'Type', 'Stock_Open', 'Stock_Close', 'Stock_ROI'])

    # get avearge volume
    if df['Volume'].mean()<100000:
        continue

    for i in range(df.index[0]+5,df.tail(1).index[0]):
        # previous days must all be the same
        before_turn = df.loc[i-3:i-1]['SQZ']
        print(before_turn)
        input()
        # recent two days must be the same
        #after_turn = df.loc[i-1:i]['SQZ']

        if len(before_turn.unique()) != 1:
            continue

        # if current day switched to maroon
        if df.loc[i]['SQZ'] == 'maroon' and trade == 'Put':
            trade = 'Call'

        # if current day switched to green
        if df.loc[i]['SQZ'] == 'green' and trade == 'Call':
            trade = 'Put'

        # sell previous trade
        if prev_trade != None and prev_trade != trade:
            trades_df.ix[len(trades_df)-1, 'Stock_Close'] = df.loc[i]['Open']

        # buy new trade
        if prev_trade != trade:
            trades_df = trades_df.append([{'Date': df.loc[i]['Date'], 'Type': trade, 'Stock_Open': df.loc[i]['Open']}])
            trades_df = trades_df.reset_index(drop=True)

        # if last day, then set the open price as the close price
        if i == len(df)-1:

            trades_df.ix[len(trades_df)-1, 'Stock_Close'] = df.loc[i]['Open']

        df.ix[i,'Trade'] = trade
        prev_trade = trade

    if len(trades_df)<3:
        continue
    # get ROI
    trades_df['Stock_ROI'] = (trades_df['Stock_Close']-trades_df['Stock_Open']) / trades_df['Stock_Open']

    # inverse the put ROI as puts would be profitable on stock downturns
    trades_df.loc[trades_df['Type']=='Put', 'Stock_ROI'] *= -1

    # only analyze the calls
    trades_df = trades_df[trades_df['Type']=='Call']

    result = [symbol, list_type, len(trades_df), trades_df['Stock_ROI'].mean(), trades_df['Stock_ROI'].sum()]
    print(str(result).replace("]",""))
    total_trades_df.append(result)
    print(pd.DataFrame(total_trades_df, columns=['Symbol', 'Listing', 'Trades', 'Avg Trade ROI', 'Total ROI']).mean())
    print(pd.DataFrame(total_trades_df, columns=['Symbol', 'Listing', 'Trades', 'Avg Trade ROI', 'Total ROI']).median())
