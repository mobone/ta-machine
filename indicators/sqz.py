import sys
from time import sleep
import pandas as pd
import MySQLdb
from datetime import datetime, timedelta, time
from math import ceil
import configparser
import calendar
import operator
import talib as ta
import statistics as stat
from sklearn import linear_model, datasets
import requests as r
import numpy as np
import re

class stock():
    def __init__(self, symbol, caller=None):
        self.symbol = symbol
        self.caller = caller

        self.length = 20
        self.mult = 2.0
        self.lengthKC = 20
        self.multKC = 1.5

        try:
            self.get_history()


        except Exception as e:
            print(self.symbol, e)
            return

        if int(datetime.now().strftime('%H')) < 19:
            self.get_current_price()

        self.df = self.df.reset_index(drop=True)

        self.source = self.df['Close'].values

        self.get_BB()
        self.get_KC()
        self.get_SQZ()

    def get_history(self):
        if self.caller=='automate':
            url = "http://chart.finance.yahoo.com/table.csv?s=%s&a=8&b=1&c=2016&d=10&e=8&f=2020&g=d&ignore=.csv" % self.symbol
        else:
            url = "http://chart.finance.yahoo.com/table.csv?s=%s&a=2&b=1&c=2016&d=10&e=8&f=2020&g=d&ignore=.csv" % self.symbol
        try:
            df = pd.read_csv(url)
            self.df = df.iloc[::-1]

            self.df = self.df.ix[:,["Date","High", "Low", "Open", "Volume", "Close"]]
            self.last_day_volume = self.df.tail(1)['Volume'].values[0]

        except Exception as e:
            print(e)

    def get_current_price(self):
        url = "http://www.marketwatch.com/investing/stock/%s" % self.symbol.replace("-",".")
        html_text = r.get(url).text.replace(' class="bgVolume"',"")
        try:
            open_price = re.findall("Open: [0-9]*\.[0-9]*", html_text)[0].split(" ")[1]
            current_price = re.findall("data bgLast\">[0-9]*\.[0-9]*", html_text)[0].split(">")[1]
            volume = re.findall("Volume </span><span>[0-9,]*", html_text)[0].split(">")[2].replace(",","")

            html_text = html_text.split("rangesection")[2]
            html_text = html_text.split("rangeopen")[0]
            low_price = re.findall("data\">\$[0-9]*\.[0-9]*", html_text)[0].split("$")[1]
            high_price = re.findall("lastcolumn\">\$[0-9]*\.[0-9]*", html_text)[0].split("$")[1]
        except Exception as e:
            print(self.symbol, e)
            
            sleep(5000)



        cur_date = datetime.now().strftime("%Y-%m-%d")
        # todo, update with high and low aswell
        self.df = self.df.append(pd.DataFrame([{
            "Date": cur_date,
            "Open": float(open_price),
            "Close": float(current_price),
            "Low": float(low_price),
            "High": float(high_price),
            "Volume": int(volume)}]))






    def get_BB(self):
        basis = ta.SMA(self.source, timeperiod=self.length)
        dev = 1.5 * stat.stdev(self.source, self.length)
        self.df['upperBB'] = basis + dev
        self.df['lowerBB'] = basis - dev

    def get_KC(self):
        self.ma = ta.SMA(self.source, self.lengthKC)
        trueRange = (self.df['High'] - self.df['Low']).values

        rangema = ta.SMA(trueRange, self.lengthKC)
        self.df['upperKC'] = self.ma + rangema * self.multKC
        self.df['lowerKC'] = self.ma - rangema * self.multKC

    def get_SQZ(self):
        df = self.df
        sqzOn = df[(df['lowerBB']>df['lowerKC']) & (df['upperBB']<df['upperKC'])]
        sqzOff = df[(df['lowerBB']<df['lowerKC']) & (df['upperBB']>df['upperKC'])]

        regr = linear_model.LinearRegression()

        highest_high = self.df.ix[:self.lengthKC,'High'].max()
        lowest_low = self.df.ix[:self.lengthKC,'Low'].min()

        x_mean = stat.mean([highest_high, lowest_low])
        y_mean_list = []
        for y in self.ma:
            y_mean_list.append(stat.mean([x_mean, y]))

        self.df['lazy_bear_mean'] = self.source - y_mean_list

        self.df = self.df.dropna(subset=['upperBB'])

        result_list = []
        coef_list = []
        cur_coef = None
        for i in self.df.iterrows():

            cur_linreg_data = self.df.ix[i[0]:i[0]+self.lengthKC, ['lazy_bear_mean']].values

            if len(cur_linreg_data)!=self.lengthKC+1:
                continue

            x = np.arange(self.lengthKC+1, dtype=float).reshape((self.lengthKC+1, 1))
            y = cur_linreg_data.reshape(self.lengthKC+1, 1)
            regr.fit(x,y)
            prev_coef = cur_coef
            cur_coef = regr.coef_[0][0]


            if prev_coef is None:
                continue
            coef_list.append(prev_coef)
            if (cur_coef>0):
                if cur_coef>prev_coef:
                    result_list.append('lime')
                else:
                    result_list.append('green')
            else:
                if cur_coef<prev_coef:
                    result_list.append('red')
                else:
                    result_list.append('maroon')


        self.df = self.df[self.lengthKC+1:]

        self.df['COEF'] = coef_list
        self.df['SQZ'] = result_list

        self.df = self.df.ix[:,['Date','Open', 'Close','Volume', 'COEF', 'SQZ']]
