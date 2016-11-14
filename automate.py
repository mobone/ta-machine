from indicators.sqz import stock
import pandas as pd
from datetime import datetime, timedelta, time
import calendar
import multiprocessing
import requests
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

def get_tickers():


    """
    page = urllib.request.urlopen("ftp://ftp.nasdaqtrader.com/SymbolDirectory/options.txt")
    df = pd.read_csv(page,sep="|")

    dfs = df.groupby('Underlying Symbol')
    tickers = []
    for df in dfs:
        if len(df[1])>10:
            tickers.append(df[0])
    """
    tickers = pd.read_csv('options_tickers.csv')['Symbol'].tolist()

    return tickers


class myThread (multiprocessing.Process):
    def __init__(self, ticker_q, return_q):
        multiprocessing.Process.__init__(self)
        self.q = ticker_q
        self.return_q = return_q

    def run(self):
        con = sqlite3.connect("trades.sqlite")

        while self.q.qsize()>0:
            (symbol, list_type) = self.q.get()
            x = stock(symbol).df

            x['listing_type'] = list_type

            day_before = x.iloc[-2:-1]['SQZ'].values[0]
            today = x.iloc[-1:]['SQZ'].values[0]

            if today != day_before and (today == 'maroon' or today =='green'):
                if today == 'maroon':
                    play = 'Call'
                elif today == 'green':
                    play = 'Put'
                x = x.ix[:, ['Date', 'listing_type', 'Open', 'SQZ']]
                x.columns = ['Date', 'Listing Type', 'Open', 'SQZ']
                message = '\n----------\n' + symbol +"\t" + "Enter " + play + '\n' + str(x.tail(2)) + '\n----------\n'
                self.return_q.put(str(message))
                print(message)
                x['Sell Date'] = None
                x['Close Price'] = None
                x['Symbol'] = symbol
                x['Play'] = play
                x = x.tail(1)
                x.to_sql('trades', con, if_exists='append')


def get_channel_symbols(ticker_q, options_tickers):
    list_types = ['channelup', 'channel' , 'channeldown']
    for list_type in list_types:
        url = "http://finviz.com/screener.ashx?v=210&s=ta_p_%s" % list_type
        html_text = requests.get(url).text.encode('UTF-8')

        matchObj = re.search( b'Page 1\/[0-9]*', html_text, re.M|re.I)
        pages = str(matchObj.group()).split('/')[1].replace("'",'')

        for i in range(int(pages)):
            url = "http://finviz.com/screener.ashx?v=210&s=ta_p_%s&r=%s" % (list_type, 1+(20*i))
            html_text = requests.get(url).text.encode('UTF-8')
            tickers = re.findall(b"quote\.ashx\?t=[A-Z]*\&", html_text)

            for ticker in tickers:
                ticker = str(ticker).replace('quote.ashx?t=','')[2:-2]
                if ticker in options_tickers:

                    ticker_q.put((ticker, list_type))


def send_alert_email(messages):

    message_header = """
    <p style='font-family: verdana'>
      This is a beta release of an automated trading system based on a popular momentum indicator. The indicator
      works by combining two common technical analysis tools and adding linear regression. Alert signals are
      produced when the indicator switches from lime green to green, or red to maroon.
      <br>
      An example of the indicator can be viewed <a href='http://aitrader.net/static/example.png'>here</a>.

    <p style='font-family: verdana'>
      You do not have to play options to succeed. Back testing revealed a median ROI of 19% and
      average ROI of 31% for the stock alone. If you only want to play the stock then submit a
      buy order install of a call; ignore puts.

    <p style='font-family: verdana'>
      This system is conbined with finviz.com's pattern recognition system to identify stocks that
      are moving within a certain channel.  If you are playing the options, it is highly recommended
      to only do calls in channel up stocks and puts in channel down stocks - this will work to your advantage.
      <br>
      Listed below are the recommended plays.<br>
      """


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
        text = message_header + messages
        messages = message_header + messages.replace("\n----------\n", "<p style='font-family:courier;'>----------\n")
        html = messages.replace("\n", "<br>")


        html = html.replace("  ", "&nbsp;&nbsp;")

        msg.attach(MIMEText(text, 'text'))
        msg.attach(MIMEText(html, 'html'))

        s = smtplib.SMTP("smtp-mail.outlook.com",587)
        s.ehlo() # Hostname to send for this command defaults to the fully qualified domain name of the local host.
        s.starttls() #Puts connection to SMTP server in TLS mode
        s.ehlo()
        s.login(config['smtp_login']['username'], config['smtp_login']['password'])

        s.sendmail("bot@aitrader.net", to_address, msg.as_string())

        s.quit()
        sleep(1)
        



if __name__ == '__main__':




    ticker_q = multiprocessing.Queue()
    return_q = multiprocessing.Queue()

    options_tickers = get_tickers()


    get_channel_symbols(ticker_q, options_tickers)


    for i in range(13):
        thread = myThread(ticker_q, return_q)
        thread.start()

    while ticker_q.qsize()>0:
        sleep(1)
    sleep(5)
    messages = ""
    while return_q.qsize()>0:
        messages = messages + return_q.get()

    if messages!="":
        send_alert_email(messages)
