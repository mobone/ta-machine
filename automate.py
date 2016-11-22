from indicators.sqz import stock
import pandas as pd
from datetime import datetime, timedelta, time
import calendar
import multiprocessing
import requests as r
import re
import urllib
import email
import smtplib
import configparser
import calendar
from time import sleep
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import sqlite3
import warnings
import requests_cache

#requests_cache.install_cache('request_cache')

warnings.filterwarnings('ignore')
pd.set_option('max_colwidth',120)

class stock_analyzer(multiprocessing.Process):
    def __init__(self, ticker_q, return_q):
        multiprocessing.Process.__init__(self)
        self.q = ticker_q
        self.return_q = return_q



    def run(self):
        self.con = sqlite3.connect("trades.sqlite")
        self.current_trades = self.get_current_trades()

        pd.set_option('max_colwidth',120)
        pd.set_option('precision',2)

        while self.q.qsize()>0:
            (symbol, list_type) = self.q.get()

            x = stock(symbol, caller='automate').df

            optimize_check = self.optimize_filter(x)                    # meet certain conditions to be
            if optimize_check == -1:                                    # considered for play
                continue

            play = self.get_play(x, symbol)                             # check for buy and sell signals

            if play is not None:
                x = self.format_output(x, symbol, list_type, play)      # format output for email

                print(x)
                self.return_q.put(x)                                    # add to queue for email

                self.store_play(x, play)                                # store buys and sells



    def optimize_filter(self, x):
        try:
            optimize_check = 1
            if x['Volume'].mean()<100000:                               # if volume not high enough, continue
                optimize_check = -1
                                                                        # if coef not high enough
            if x.iloc[-1:]['COEF'].values[0]<0.15 and x.iloc[-1:]['COEF'].values[0]>-0.15:
                optimize_check = -1

            days_before = x.iloc[-4:-1]['SQZ'].unique()                 # prior days must be same

            if len(days_before) != 1 or len(x.tail())==0:
                optimize_check = -1
        except Exception as e:
            print(e)
            optimize_check = -1
        return optimize_check


    def store_play(self, x, play):
        x = x.copy(deep=True)
        del x['Play']
        del x['FinViz Chart']
        del x['TradingView Chart']

        x['Buy Date'] = datetime.now().strftime('%m-%d-%Y')
        x['Sell Date'] = None
        x['Close Price'] = None
        x['Current Price'] = None

        if play == "Buy":
            # check if already bought
            x.to_sql('trades_v2', self.con, if_exists='append', index=False)
        elif play == "Sell":
            c = self.con.cursor()
            sql = """update trades_v2 set
                `Sell Date` = '%s',
                `Close Price` = %s where
                Symbol = '%s' and `Sell Date` is null""" % (datetime.now().strftime("%m-%d-%Y"), x['Open'].values[0], symbol)
            print(sql)
            try:
                c.execute(sql)
                self.con.commit()
            except:
                pass

    def get_play(self, x, symbol):
        day_before = x.iloc[-2:-1]['SQZ'].values[0]
        today = x.iloc[-1:]['SQZ'].values[0]

        play = None
        if today != day_before and today == 'maroon':
            play = "Buy"
        if today != day_before and today == "green" and symbol in self.current_trades:
            play = "Sell"
        return play

    def get_dividends(self, symbol):

        one_year_ago = (datetime.now()-timedelta(days=365)).strftime("%Y-%m-%d")


        url = "http://www.nasdaq.com/symbol/%s/dividend-history" % symbol
        html_text = r.get(url).text.encode('UTF-8')
        dividend_df = pd.read_html(html_text)[5]

        if 'Payment Date' not in dividend_df.keys():
            return "0/4"

        dividend_df = dividend_df[dividend_df['Payment Date'] != '--']
        dividend_df['Payment Date'] = pd.to_datetime(dividend_df['Payment Date'], format = '%m/%d/%Y')
        dividend_df = dividend_df[dividend_df['Payment Date'] > one_year_ago]

        if len(dividend_df)>5:
            dividend_ratio = str(len(dividend_df))+"/12"
        elif len(dividend_df)==5:                                     # hack for some stocks returning 5 dividends
            dividend_ratio = "4/4"
        else:
            dividend_ratio = str(len(dividend_df))+"/4"

        return dividend_ratio

    def format_output(self, x, symbol, list_type, play):
        x['Symbol'] = symbol
        x['Listing Type'] = list_type
        x['Play'] = play
        x = x.ix[:, ['Symbol', 'Play', 'Listing Type', 'Open', 'Volume']]



        # get other fundamentals info
        (exchange, fundamentals_df) = self.get_fundamentals(symbol)
        x['FinViz Chart'] = 'View Chart'
        x['TradingView Chart'] = exchange

        fundamentals_columns = ['Beta', 'P/E', 'EPS Q/Q', 'Quick Ratio', 'Short Ratio', 'Dividend %']
        for col in fundamentals_columns:
            x[col] = fundamentals_df[col]['value']

        # get dividend info
        dividend_ratio = self.get_dividends(symbol)

        x['Div. in Last YR.'] =  dividend_ratio
        x = x.tail(1)
        return x

    def get_current_trades(self):
        try:
            sql = "select * from trades_v2 where `Sell Date` is null";
            df = pd.read_sql(sql, self.con)
            return df['Symbol'].values
        except:
            return []

    def get_fundamentals(self, symbol):
        url = "http://finviz.com/quote.ashx?t=%s" % symbol
        html_text = r.get(url).text.encode('UTF-8')

        # get exchange
        exchange_key = re.findall(b"finance\?q=[A-Z:]*", html_text)
        exchange = exchange_key[0].decode("utf-8").replace("finance?q=","")

        # get fundamentals_df
        dfs = pd.read_html(html_text)
        df = dfs[7]
        df = pd.DataFrame(df.values.reshape(-1, 2), columns=['key', 'value'])
        df = df.set_index('key').T

        return (exchange, df)


def get_current_trades(ticker_list):
    con = sqlite3.connect("trades.sqlite")
    try:
        sql = "select Symbol,`Listing Type` from trades_v2 where `Sell Date` is null";
        df = pd.read_sql(sql, con)
    except Exception as e:
        print(e)
        return ticker_list

    for i in df.values:
        symbol = i[0]
        find_item = [item for item in ticker_list if symbol in item]

        if len(find_item)==0:
            ticker_list.append(i)

    return ticker_list

def get_sp500(ticker_list):
    df = pd.read_csv('sp500.csv').values

    for symbol in df:
        find_item = [item for item in ticker_list if symbol in item]
        if len(find_item)==0:
            ticker_list.append([symbol[0], 'sp500'])

    return ticker_list

def get_channel_symbols(ticker_list):
    list_types = ['channelup', 'channel']
    for list_type in list_types:
        url = "http://finviz.com/screener.ashx?v=210&s=ta_p_%s" % list_type
        html_text = r.get(url).text.encode('UTF-8')

        matchObj = re.search( b'Page 1\/[0-9]*', html_text, re.M|re.I)
        pages = str(matchObj.group()).split('/')[1].replace("'",'')

        for i in range(int(pages)):
            url = "http://finviz.com/screener.ashx?v=210&s=ta_p_%s&r=%s" % (list_type, 1+(20*i))
            html_text = r.get(url).text.encode('UTF-8')
            tickers = re.findall(b"quote\.ashx\?t=[A-Z]*\&", html_text)

            for ticker in tickers:
                ticker = str(ticker).replace('quote.ashx?t=','')[2:-2]
                ticker_list.append([ticker, list_type])

    return ticker_list

def get_html_table(messages):
    table = "<table>"
    for i in messages:
        print(i)

    for i in range(len(messages[0].columns)):
        table = table + "<col>"

    table = table + "<tr>"
    for column in messages[0].columns.values:
        table = table + "<th style = 'background-color: #0099CC; color: white; padding: 5px;'>" + column + "</th>"
    table = table + "</tr>"

    for message in messages:
        symbol = message['Symbol'].values[0]

        table = table + "<tr>"
        for item in message.values[0]:
            tr = ""
            if item == 'View Chart':
                tr = tr + "<td style='text-align: center; padding: 5px;border-bottom: 1px solid #ddd;'><a href='http://finviz.com/chart.ashx?t=%s&ta=1&p=d&s=l'>View Chart</a></td>" % (symbol)
            elif type(item) == float:
                tr = tr + "<td style='text-align: right; padding: 5px;border-bottom: 1px solid #ddd;'>{0:.2f}</td>".format(item)
            elif type(item) == int:
                tr = tr + "<td style='text-align: right; padding: 5px;border-bottom: 1px solid #ddd;'>{:,d}</td>".format(item)
            elif item == symbol:
                tr = tr + "<td style='text-align: center; padding: 5px;border-bottom: 1px solid #ddd;''><a href='https://finance.yahoo.com/quote/%s'>%s</a></td>" % (symbol, symbol)
            elif ":" in item and symbol in item:
                tr = tr + "<td style='text-align: center; padding: 5px;border-bottom: 1px solid #ddd;''><a href='https://www.tradingview.com/chart/?symbol=%s'>View Chart</a></td>" % (item)
            elif item == "Sell":
                tr = tr + "<td style='text-align: center; padding: 5px;border-bottom: 1px solid #ddd;''><b>"+str(item)+"</b></td>"
            else:
                tr = tr + "<td style='text-align: center; padding: 5px;border-bottom: 1px solid #ddd;''>"+str(item)+"</td>"
            table = table + tr


        table = table + "</tr>\n"

    table = table + "</table>"
    return table

def send_alert_email(messages):
    # generate table
    table = get_html_table(messages)

    with open('email_message.txt', 'r') as email_message:
        message_header=email_message.read()

    config = configparser.RawConfigParser()
    config.read("credentials.ini")

    addresses_config = configparser.RawConfigParser()
    addresses_config.read("email_members.ini")

    email_addresses = addresses_config['email_addresses']['addresses'].split(',')
    for to_address in email_addresses:
        print('sending email to: ', to_address)

        msg = MIMEMultipart('alternative')
        msg['From'] = "bot@aitrader.net"
        msg['To'] = to_address
        msg['Subject'] = "Trade Alerts for %s - AITrader.net (Beta)" % datetime.now().strftime('%m-%d-%Y')

        html = message_header + table

        msg.attach(MIMEText(html, 'html'))

        s = smtplib.SMTP("smtp-mail.outlook.com",587)
        s.ehlo() # Hostname to send for this command defaults to the fully qualified domain name of the local host.
        s.starttls() #Puts connection to SMTP server in TLS mode
        s.ehlo()
        s.login(config['smtp_login']['username'], config['smtp_login']['password'])

        s.sendmail("bot@aitrader.net", to_address, msg.as_string())

        s.quit()
        sleep(.1)
        if 'nicholas' in to_address:
            input()


if __name__ == '__main__':
    ticker_q = multiprocessing.Queue()      # input queue
    return_q = multiprocessing.Queue()      # output queue
    ticker_list = []
    ticker_list = get_channel_symbols(ticker_list)  # finviz pattern recognition
    ticker_list = get_sp500(ticker_list)            # get sp500 for testing purposes
    ticker_list = get_current_trades(ticker_list)

    for i in ticker_list:
        ticker_q.put(i)

    for i in range(10):
        thread = stock_analyzer(ticker_q, return_q)
        thread.start()

    while ticker_q.qsize()>0:
        sleep(1)
    print("Work queue complete")
    sleep(15)                                # wait for all workers to complete

    plays_list = []                        # concat output together for email
    while return_q.qsize()>0:
        plays_list.append(return_q.get())

    if len(plays_list)>0:
        send_alert_email(plays_list)          # send the mail
