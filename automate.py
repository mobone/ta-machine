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
            play = None

            try:
                if x['Volume'].mean()<100000:               # if volume not high enough, continue
                    continue

                days_before = x.iloc[-4:-1]['SQZ'].unique() # prior days must be same

                if len(days_before) != 1 or len(x.tail())==0:
                    continue
            except:
                continue

            day_before = x.iloc[-2:-1]['SQZ'].values[0]
            today = x.iloc[-1:]['SQZ'].values[0]

            play = None                                     # check for buy and sell signals
            if today != day_before and today == 'maroon':
                play = "Buy"
            if today != day_before and today == "green" and symbol in self.current_trades:
                play = "Sell"


            if play is not None:
                x = x.ix[:, ['Open', 'Volume', 'SQZ']]

                x['Symbol'] = symbol
                x['Play'] = play
                x['Listing Type'] = list_type

                x = x.ix[:, ['Symbol', 'Play', 'Listing Type', 'Open', 'Volume']]

                (exchange, fundamentals_df) = self.get_fundamentals(symbol)
                x['FinViz Chart'] = 'View Chart'
                x['TradingView Chart'] = exchange

                fundamentals_columns = ['Beta', 'P/E', 'EPS Q/Q', 'Quick Ratio', 'Short Ratio']
                for col in fundamentals_columns:
                    x[col] = fundamentals_df[col]['value']

                x = x.tail(1)
                print(x)
                self.return_q.put(x)

                del x['FinViz Chart']
                del x['TradingView Chart']
                del x['Play']

                x['Buy Date'] = datetime.now().strftime('%m-%d-%Y')
                x['Sell Date'] = None
                x['Close Price'] = None
                x['Current Price'] = None

                # store buys and sells
                if play == "Buy":    
                    x.to_sql('trades_v2', self.con, if_exists='append')
                elif play == "Sell":
                    c = self.con.cursor()
                    sql = """update trades_v2 set
                        `Sell Date` = '%s',
                        `Close Price` = %s where
                        Symbol = '%s' and `Sell Date` is null""" % (datetime.now().strftime("%m-%d-%Y"), x['Open'].values[0], symbol)
                    print(sql)
                    c.execute(sql)
                    self.con.commit()

    def get_current_trades(self):
        sql = "select * from trades_v2 where `Sell Date` is null";
        df = pd.read_sql(sql, self.con)

        return df['Symbol'].values


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

def get_sp500(ticker_q, ):
    df = pd.read_csv('sp500.csv').values
    for symbol in df:
        ticker_q.put((symbol[0], 'sp500'))

def get_channel_symbols(ticker_q):
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
                ticker_q.put((ticker, list_type))

def get_html_table(messages):
    table = "<table>"
    for i in messages:
        print(i)

    for i in range(len(messages[0].columns)):
        table = table + "<col width='85'>"

    table = table + "<tr>"
    for column in messages[0].columns.values:
        table = table + "<th>" + column + "</th>"
    table = table + "</tr>"

    for message in messages:
        symbol = message['Symbol'].values[0]

        table = table + "<tr>"
        for item in message.values[0]:
            tr = ""
            if item == 'View Chart':
                tr = tr + "<td style='text-align: center'><a href='http://finviz.com/chart.ashx?t=%s&ta=1&p=d&s=l'>View Chart</a></td>" % (symbol)
            elif type(item) == float:
                tr = tr + "<td style='text-align: right'>{0:.2f}</td>".format(item)
            elif type(item) == int:
                tr = tr + "<td style='text-align: right'>{:,d}</td>".format(item)
            elif item == symbol:
                tr = tr + "<td style='text-align: center'><a href='https://finance.yahoo.com/quote/%s'>%s</a></td>" % (symbol, symbol)
            elif ":" in item and symbol in item:
                tr = tr + "<td style='text-align: center'><a href='https://www.tradingview.com/chart/?symbol=%s'>View Chart</a></td>" % (item)
            elif item == "Sell":
                tr = tr + "<td style='text-align: center'><b>"+str(item)+"</b></td>"
            else:
                tr = tr + "<td style='text-align: center'>"+str(item)+"</td>"
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


if __name__ == '__main__':
    ticker_q = multiprocessing.Queue()      # input queue
    return_q = multiprocessing.Queue()      # output queue

    get_channel_symbols(ticker_q)  # finviz pattern recognition
    get_sp500(ticker_q)            # get sp500 for testing purposes

    for i in range(15):
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
