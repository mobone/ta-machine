from indicators.sqz import stock
import pandas as pd

x = stock('svu')
print(x.df)
pd.set_option('display.max_rows', len(x.df))

trade = 'put'
for day in x.df.iterrows():
    print(day)

    if day[1]['SQZ'] == 'maroon' and trade == 'put':
        trade = 'call'


    if day[1]['SQZ'] == 'green' and trade == 'call':
        trade = 'put'

    x.df.ix[day[0], 'trade'] = trade
print(x.df)
