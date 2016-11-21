import pandas as pd
import re
import requests as r
import sqlite3


def get_current_price(symbol):
    url = "http://finviz.com/quote.ashx?t=%s" % symbol
    html_text = r.get(url).text.encode('UTF-8')
    dfs = pd.read_html(html_text)
    df = dfs[7]
    d1 = pd.DataFrame(df.values.reshape(-1, 2), columns=['key', 'value'])
    d1 = d1.set_index('key').T
    print(d1)
    input()
    cur_price = d1['Price']['value']


    return cur_price

def send_to_db(symbol, trade_date, price):
    sql = "update trades set `Current Price` = %s where Symbol = '%s' and `Buy Date` = '%s'" % (price, symbol, trade_date)
    print(sql)


    c.execute(sql)
    con.commit()

con = sqlite3.connect("trades.sqlite")
c = con.cursor()
trades_df = pd.read_sql("select Symbol,`Buy Date` from trades_v2 where `Close Price` is null and `Play` = 'Enter Call';", con)

for i in trades_df.iterrows():
    print(i[1])
    cur_price = get_current_price(i[1]['Symbol'])
    send_to_db(i[1]['Symbol'], i[1]['Buy Date'], cur_price)
