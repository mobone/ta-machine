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

def get_options_tickers():
    page = urllib.request.urlopen("ftp://ftp.nasdaqtrader.com/SymbolDirectory/options.txt")
    df = pd.read_csv(page,sep="|")

    dfs = df.groupby('Underlying Symbol')
    tickers = []
    for df in dfs:
        if len(df[1])>50:
            tickers.append(df[0])

    return tickers

class stock_analyzer(multiprocessing.Process):
    def __init__(self, ticker_q, return_q):
        multiprocessing.Process.__init__(self)
        self.q = ticker_q
        self.return_q = return_q

    def run(self):
        con = sqlite3.connect("trades.sqlite")

        while self.q.qsize()>0:
            (symbol, list_type, options) = self.q.get()

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
            x['listing_type'] = list_type
            x['Options'] = options

            if today != day_before and (today == 'maroon' or today =='green'):
                if today == 'maroon' and list_type != 'channeldown':
                    play = 'Call'
                elif today == 'green' and list_type != 'channelup':
                    play = 'Put'

                if play:    #sometimes play still gets through as none....
                    x = x.ix[:, ['listing_type', 'Options', 'Open', 'Volume', 'SQZ']]
                    x.columns = ['Listing Type', 'Options', 'Open', 'Y\'day Vol.', 'SQZ']
                    message = '\n----------\n' + symbol +"\t" + "Enter " + play + '\n' + str(x.tail(6)) + '\n----------'
                    print(message)
                    message = '\n<b>' + symbol +"\t\t\t" + "Enter " + play + '</b>\n' + x.tail(1).to_string(index=False)
                    self.return_q.put(str(message))

                    x['Sell Date'] = None
                    x['Close Price'] = None
                    x['Current Price'] = None
                    x['Symbol'] = symbol
                    x['Play'] = play
                    x = x.tail(1)
                    x.to_sql('trades', con, if_exists='append')

def get_sp500(ticker_q, options_tickers):
    df = pd.read_csv('sp500.csv').values
    for symbol in df:
        if symbol[0] in options_tickers:
            ticker_q.put((symbol[0], 'sp500', 'Yes'))
        else:
            ticker_q.put((symbol[0], 'sp500', 'No'))

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
                    options = 'Yes'
                else:
                    options = 'No'

                ticker_q.put((ticker, list_type, options))

def send_alert_email(messages):
    with open('email_message.txt', 'r') as email_message:
        message_header=email_message.read().replace('\n', '<br>')

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
        html = message_header + "<p style='font-family:courier;'>" + messages.replace("\n", "<br>")

        html = html.replace("  ", "&nbsp;&nbsp;")
        html = html.replace("\t", "&nbsp;&nbsp;&nbsp;&nbsp;")

        msg.attach(MIMEText(text, 'text'))
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

    options_tickers = get_options_tickers()         # get stocks that have options
    get_channel_symbols(ticker_q, options_tickers)  # finviz pattern recognition
    get_sp500(ticker_q, options_tickers)            # get sp500 for testing purposes

    for i in range(20):
        thread = stock_analyzer(ticker_q, return_q)
        thread.start()

    while ticker_q.qsize()>0:
        sleep(1)
    sleep(25)                               # wait for all workers to complete

    messages = ""                           # concat output together for email
    while return_q.qsize()>0:
        messages = messages + return_q.get()

    if messages!="":
        send_alert_email(messages)          # send the mail
