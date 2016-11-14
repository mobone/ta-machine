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

tickers = pd.read_csv('sp500.csv')

for i in tickers.iterrows():
    symbol = i[1]['Symbol']
    list_type = i[1]['list_type']

    x = stock(symbol)

    pd.set_option('display.max_rows', len(x.df))

    trade = 'Put'
    prev_trade = None

    trades_df = pd.DataFrame(columns=['Date', 'Type', 'Stock_Open', 'Stock_Close', 'Stock_ROI'])

    for day in x.df.iterrows():


        if day[1]['SQZ'] == 'maroon' and trade == 'Put':
            trade = 'Call'




        if day[1]['SQZ'] == 'green' and trade == 'Call':
            trade = 'Put'

        # sell previous trade
        if prev_trade != None and prev_trade != trade:
            trades_df.ix[len(trades_df)-1, 'Stock_Close'] = day[1]['Open']

        # buy new trade
        if prev_trade != trade:
            trades_df = trades_df.append([{'Date': day[1]['Date'], 'Type': trade, 'Stock_Open': day[1]['Open']}])
            trades_df = trades_df.reset_index(drop=True)

        if day[0]-39 == len(x.df):
            trades_df.ix[len(trades_df)-1, 'Stock_Close'] = day[1]['Open']

        prev_trade = trade
        x.df.ix[day[0], 'trade'] = trade


    trades_df['Stock_ROI'] = (trades_df['Stock_Close']-trades_df['Stock_Open']) / trades_df['Stock_Open']

    trades_df.loc[trades_df['Type']=='Put', 'Stock_ROI'] *= -1


    trades_df = trades_df[trades_df['Type']=='Call']

    print(symbol, list_type, len(trades_df), trades_df['Stock_ROI'].sum())
