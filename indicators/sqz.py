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
    def __init__(self, symbol):
        self.symbol = symbol

        self.length = 20
        self.mult = 2.0
        self.lengthKC = 20
        self.multKC = 1.5

        self.get_history()
        self.get_current_price()
        self.df = self.df.reset_index(drop=True)
        self.source = self.df['Close'].values
        
        self.get_BB()
        self.get_KC()
        self.get_SQZ()

    def get_history(self):
        url = "http://chart.finance.yahoo.com/table.csv?s=%s&a=2&b=1&c=2016&d=10&e=8&f=2020&g=d&ignore=.csv" % self.symbol
        df = pd.read_csv(url)
        self.df = df.iloc[::-1]

        self.df = self.df.ix[:,["Date","High", "Low", "Close"]]




    def get_current_price(self):
        url = "http://finance.yahoo.com/quote/%s" % self.symbol
        html_text = r.get(url).text.encode('utf-8')
        p = re.compile(b'regularMarketPrice":{"raw":[0-9]*\.[0-9]')
        matches = p.findall(html_text)
        #match = re.search( b'regularMarketPrice":{"raw":[0-9]*\.[0-9]', html_text, re.M|re.I).group()

        cur_price = float(str(matches[len(matches)-1]).split("raw\":")[1].replace("'",""))

        cur_date = datetime.now().strftime("%Y-%m-%d")

        # todo, update with high and low aswell
        self.df = self.df.append(pd.DataFrame([{"Date": cur_date, "Close": cur_price, "Low": cur_price,  "High": cur_price}]))




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
            y_mean = stat.mean([x_mean, y])

            y_mean_list.append(y_mean)


        self.df['lazy_bear_mean'] = self.source - y_mean_list

        self.df = self.df.dropna()
        result_list = []
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
        self.df['SQZ'] = result_list




        self.df = self.df.ix[:,['Date','Close','SQZ']]
        try:
            self.df.to_csv("out.csv")
        except:
            pass
