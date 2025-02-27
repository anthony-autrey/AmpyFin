import yfinance as yf
import datetime

ticker_yahoo = yf.Ticker('AAPL')  
data = ticker_yahoo.history()
# return round(data['Close'].iloc[-1], 2)

marketTime = ticker_yahoo.info['regularMarketTime']
marketPrice = ticker_yahoo.info['regularMarketPrice']
dt_object = datetime.datetime.fromtimestamp(marketTime)
print(data)
print(dt_object)
print(marketPrice)