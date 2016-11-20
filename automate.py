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

requests_cache.install_cache('request_cache')

warnings.filterwarnings('ignore')
pd.set_option('max_colwidth',120)

class stock_analyzer(multiprocessing.Process):
    def __init__(self, ticker_q, return_q):
        multiprocessing.Process.__init__(self)
        self.q = ticker_q
        self.return_q = return_q

    def run(self):
        con = sqlite3.connect("trades.sqlite")
        pd.set_option('max_colwidth',120)
        pd.set_option('precision',2)

        while self.q.qsize()>0:
            (symbol, list_type) = self.q.get()

            x = stock(symbol, caller='automate').df

            try:
                if x['Volume'].mean()<100000:  # if volume not high enough, continue
                    continue
                days_before = x.iloc[-4:-1]['SQZ'].unique() # prior days must be same
                if len(days_before) != 1 or len(x.tail())==0:
                    continue
            except:
                continue

            day_before = x.iloc[-2:-1]['SQZ'].values[0]
            today = x.iloc[-1:]['SQZ'].values[0]

            play = None
            x['Listing Type'] = list_type

            if today != day_before and today == 'maroon':
                if today == 'maroon':
                    play = 'Buy'

                if play:    #sometimes play still gets through as none....
                    x = x.ix[:, ['Listing Type', 'Open', 'Volume', 'SQZ']]

                    x['Symbol'] = symbol
                    x['Play'] = play

                    x['FinViz Chart'] = 'View Chart'
                    x = x.ix[:, ['Symbol', 'Play', 'Listing Type', 'FinViz Chart', 'Open', 'Volume']]
                    x['Open'] = x['Open'].round(2)

                    fundamentals_df = self.get_fundamentals(symbol)
                    fundamentals_columns = ['Beta', 'P/E', 'EPS Q/Q', 'Quick Ratio', 'Short Ratio']
                    for col in fundamentals_columns:
                        x[col] = fundamentals_df[col]['value']

                    print(x.tail(1))
                    self.return_q.put(x.tail(1))
                    del x['FinViz Chart']

                    x['Buy Date'] = datetime.now().strftime('%m-%d-%Y')
                    x['Sell Date'] = None
                    x['Close Price'] = None
                    x['Current Price'] = None



                    x = x.tail(1)
                    x.to_sql('trades_v2', con, if_exists='append')

    def get_fundamentals(self, symbol):
        url = "http://finviz.com/quote.ashx?t=%s" % symbol
        html_text = r.get(url).text.encode('UTF-8')
        dfs = pd.read_html(html_text)
        df = dfs[7]
        df = pd.DataFrame(df.values.reshape(-1, 2), columns=['key', 'value'])
        df = df.set_index('key').T

        return df



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
        table = table + "<col width='90'>"

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

        input()


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
