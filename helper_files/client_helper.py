import os
from pymongo import MongoClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from datetime import datetime, timedelta, timezone
import logging
import yfinance as yf
import sys
from pathlib import Path
sys.path.append("..")
from control import (
    stop_loss, take_profit, min_margin_ratio,
    enable_short_selling, max_short_ratio, short_liquidity_buffer
)

parent_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(parent_dir))
from strategies.talib_indicators import (get_data, BBANDS_indicator, DEMA_indicator, EMA_indicator, HT_TRENDLINE_indicator, KAMA_indicator, MA_indicator, MAMA_indicator, MAVP_indicator, MIDPOINT_indicator, MIDPRICE_indicator, SAR_indicator, SAREXT_indicator, SMA_indicator, T3_indicator, TEMA_indicator, TRIMA_indicator, WMA_indicator, ADX_indicator, ADXR_indicator, APO_indicator, AROON_indicator, AROONOSC_indicator, BOP_indicator, CCI_indicator, CMO_indicator, DX_indicator, MACD_indicator, MACDEXT_indicator, MACDFIX_indicator, MFI_indicator, MINUS_DI_indicator, MINUS_DM_indicator, MOM_indicator, PLUS_DI_indicator, PLUS_DM_indicator, PPO_indicator, ROC_indicator, ROCP_indicator, ROCR_indicator, ROCR100_indicator, RSI_indicator, STOCH_indicator, STOCHF_indicator, STOCHRSI_indicator, TRIX_indicator, ULTOSC_indicator, WILLR_indicator, AD_indicator, ADOSC_indicator, OBV_indicator, HT_DCPERIOD_indicator, HT_DCPHASE_indicator, HT_PHASOR_indicator, HT_SINE_indicator, HT_TRENDMODE_indicator, AVGPRICE_indicator, MEDPRICE_indicator, TYPPRICE_indicator, WCLPRICE_indicator, ATR_indicator, NATR_indicator, TRANGE_indicator, CDL2CROWS_indicator, CDL3BLACKCROWS_indicator, CDL3INSIDE_indicator, CDL3LINESTRIKE_indicator, CDL3OUTSIDE_indicator, CDL3STARSINSOUTH_indicator, CDL3WHITESOLDIERS_indicator, CDLABANDONEDBABY_indicator, CDLADVANCEBLOCK_indicator, CDLBELTHOLD_indicator, CDLBREAKAWAY_indicator, CDLCLOSINGMARUBOZU_indicator, CDLCONCEALBABYSWALL_indicator, CDLCOUNTERATTACK_indicator, CDLDARKCLOUDCOVER_indicator, CDLDOJI_indicator, CDLDOJISTAR_indicator, CDLDRAGONFLYDOJI_indicator, CDLENGULFING_indicator, CDLEVENINGDOJISTAR_indicator, CDLEVENINGSTAR_indicator, CDLGAPSIDESIDEWHITE_indicator, CDLGRAVESTONEDOJI_indicator, CDLHAMMER_indicator, CDLHANGINGMAN_indicator, CDLHARAMI_indicator, CDLHARAMICROSS_indicator, CDLHIGHWAVE_indicator, CDLHIKKAKE_indicator, CDLHIKKAKEMOD_indicator, CDLHOMINGPIGEON_indicator, CDLIDENTICAL3CROWS_indicator, CDLINNECK_indicator, CDLINVERTEDHAMMER_indicator, CDLKICKING_indicator, CDLKICKINGBYLENGTH_indicator, CDLLADDERBOTTOM_indicator, CDLLONGLEGGEDDOJI_indicator, CDLLONGLINE_indicator, CDLMARUBOZU_indicator, CDLMATCHINGLOW_indicator, CDLMATHOLD_indicator, CDLMORNINGDOJISTAR_indicator, CDLMORNINGSTAR_indicator, CDLONNECK_indicator, CDLPIERCING_indicator, CDLRICKSHAWMAN_indicator, CDLRISEFALL3METHODS_indicator, CDLSEPARATINGLINES_indicator, CDLSHOOTINGSTAR_indicator, CDLSHORTLINE_indicator, CDLSPINNINGTOP_indicator, CDLSTALLEDPATTERN_indicator, CDLSTICKSANDWICH_indicator, CDLTAKURI_indicator, CDLTASUKIGAP_indicator, CDLTHRUSTING_indicator, CDLTRISTAR_indicator, CDLUNIQUE3RIVER_indicator, CDLUPSIDEGAP2CROWS_indicator, CDLXSIDEGAP3METHODS_indicator, BETA_indicator, CORREL_indicator, LINEARREG_indicator, LINEARREG_ANGLE_indicator, LINEARREG_INTERCEPT_indicator, LINEARREG_SLOPE_indicator, STDDEV_indicator, TSF_indicator, VAR_indicator)
   
from urllib.request import urlopen
import json
import certifi
from zoneinfo import ZoneInfo
import time

ca = certifi.where()

overlap_studies = [BBANDS_indicator, DEMA_indicator, EMA_indicator, HT_TRENDLINE_indicator, KAMA_indicator, MA_indicator, MAMA_indicator, MAVP_indicator, MIDPOINT_indicator, MIDPRICE_indicator, SAR_indicator, SAREXT_indicator, SMA_indicator, T3_indicator, TEMA_indicator, TRIMA_indicator, WMA_indicator]
momentum_indicators = [ADX_indicator, ADXR_indicator, APO_indicator, AROON_indicator, AROONOSC_indicator, BOP_indicator, CCI_indicator, CMO_indicator, DX_indicator, MACD_indicator, MACDEXT_indicator, MACDFIX_indicator, MFI_indicator, MINUS_DI_indicator, MINUS_DM_indicator, MOM_indicator, PLUS_DI_indicator, PLUS_DM_indicator, PPO_indicator, ROC_indicator, ROCP_indicator, ROCR_indicator, ROCR100_indicator, RSI_indicator, STOCH_indicator, STOCHF_indicator, STOCHRSI_indicator, TRIX_indicator, ULTOSC_indicator, WILLR_indicator]
volume_indicators = [AD_indicator, ADOSC_indicator, OBV_indicator]
cycle_indicators = [HT_DCPERIOD_indicator, HT_DCPHASE_indicator, HT_PHASOR_indicator, HT_SINE_indicator, HT_TRENDMODE_indicator]
price_transforms = [AVGPRICE_indicator, MEDPRICE_indicator, TYPPRICE_indicator, WCLPRICE_indicator]
volatility_indicators = [ATR_indicator, NATR_indicator, TRANGE_indicator]
pattern_recognition = [CDL2CROWS_indicator, CDL3BLACKCROWS_indicator, CDL3INSIDE_indicator, CDL3LINESTRIKE_indicator, CDL3OUTSIDE_indicator, CDL3STARSINSOUTH_indicator, CDL3WHITESOLDIERS_indicator, CDLABANDONEDBABY_indicator, CDLADVANCEBLOCK_indicator, CDLBELTHOLD_indicator, CDLBREAKAWAY_indicator, CDLCLOSINGMARUBOZU_indicator, CDLCONCEALBABYSWALL_indicator, CDLCOUNTERATTACK_indicator, CDLDARKCLOUDCOVER_indicator, CDLDOJI_indicator, CDLDOJISTAR_indicator, CDLDRAGONFLYDOJI_indicator, CDLENGULFING_indicator, CDLEVENINGDOJISTAR_indicator, CDLEVENINGSTAR_indicator, CDLGAPSIDESIDEWHITE_indicator, CDLGRAVESTONEDOJI_indicator, CDLHAMMER_indicator, CDLHANGINGMAN_indicator, CDLHARAMI_indicator, CDLHARAMICROSS_indicator, CDLHIGHWAVE_indicator, CDLHIKKAKE_indicator, CDLHIKKAKEMOD_indicator, CDLHOMINGPIGEON_indicator, CDLIDENTICAL3CROWS_indicator, CDLINNECK_indicator, CDLINVERTEDHAMMER_indicator, CDLKICKING_indicator, CDLKICKINGBYLENGTH_indicator, CDLLADDERBOTTOM_indicator, CDLLONGLEGGEDDOJI_indicator, CDLLONGLINE_indicator, CDLMARUBOZU_indicator, CDLMATCHINGLOW_indicator, CDLMATHOLD_indicator, CDLMORNINGDOJISTAR_indicator, CDLMORNINGSTAR_indicator, CDLONNECK_indicator, CDLPIERCING_indicator, CDLRICKSHAWMAN_indicator, CDLRISEFALL3METHODS_indicator, CDLSEPARATINGLINES_indicator, CDLSHOOTINGSTAR_indicator, CDLSHORTLINE_indicator, CDLSPINNINGTOP_indicator, CDLSTALLEDPATTERN_indicator, CDLSTICKSANDWICH_indicator, CDLTAKURI_indicator, CDLTASUKIGAP_indicator, CDLTHRUSTING_indicator, CDLTRISTAR_indicator, CDLUNIQUE3RIVER_indicator, CDLUPSIDEGAP2CROWS_indicator, CDLXSIDEGAP3METHODS_indicator]
statistical_functions = [BETA_indicator, CORREL_indicator, LINEARREG_indicator, LINEARREG_ANGLE_indicator, LINEARREG_INTERCEPT_indicator, LINEARREG_SLOPE_indicator, STDDEV_indicator, TSF_indicator, VAR_indicator]

strategies = overlap_studies + momentum_indicators + volume_indicators + cycle_indicators + price_transforms + volatility_indicators + pattern_recognition + statistical_functions

# MongoDB connection helper
def get_mongo_client(mongo_url):
    """Connect to MongoDB and return the client."""

    running_locally = os.getenv("MONGO_URL") == "mongodb://mongo:27017/db"
    if running_locally:
        return MongoClient(mongo_url) # TLS not required on the Docker mongo service because it blocks all external requests
    
    return MongoClient(mongo_url, tlsCAFile=ca)

# Helper to place an order
def place_order(trading_client, symbol, side, quantity, mongo_client, is_short=False):
    """
    Place a market order and log the order to MongoDB.
    Includes margin safety checks to prevent margin calls.
    Supports both regular buying/selling and short selling.

    :param trading_client: The Alpaca trading client instance
    :param symbol: The stock symbol to trade
    :param side: Order side (OrderSide.BUY or OrderSide.SELL)
    :param qty: Quantity to trade
    :param mongo_client: MongoDB client instance
    :param is_short: Boolean indicating if this is a short sell or buy to cover
    :return: Order result from Alpaca API or None if margin safety check fails
    """
    # Check if short selling is enabled
    if is_short and not enable_short_selling:
        logging.warning(f"Attempted short selling for {symbol} but short selling is disabled. "
                      f"Enable it by setting ENABLE_SHORT_SELLING=True in your environment.")
        return None
    
    current_price = get_latest_price(symbol)
    
    # Check margin safety for all orders
    is_safe, margin_ratio = check_margin_safety(trading_client, symbol, quantity, current_price, side, is_short)
    if not is_safe:
        order_type = "SHORT" if is_short else "regular"
        logging.warning(f"Margin safety check failed for {symbol} {order_type} {side.name} order. "
                      f"Margin ratio {margin_ratio:.4f} would be below minimum {min_margin_ratio:.4f}. "
                      f"Order cancelled for safety.")
        return None
    
    # Proceed with order
    market_order_data = MarketOrderRequest(
        symbol=symbol,
        qty=quantity,
        side=side,
        time_in_force=TimeInForce.DAY
    )
    
    try:
        order = trading_client.submit_order(market_order_data)
        qty = round(quantity, 3)
        
        # Calculate stop loss and take profit differently for short vs long positions
        if is_short and side == OrderSide.SELL:
            # For short positions, stop loss is price going up, take profit is price going down
            stop_loss_price = round(current_price * (1 + stop_loss), 2)  # e.g. 3% increase
            take_profit_price = round(current_price * (1 - take_profit), 2)  # e.g. 5% decrease
        else:
            # For long positions, or when covering shorts
            stop_loss_price = round(current_price * (1 - stop_loss), 2)  # e.g. 3% decrease
            take_profit_price = round(current_price * (1 + take_profit), 2)  # e.g. 5% increase

        # Log trade details to MongoDB
        db = mongo_client.trades
        db.paper.insert_one({
            'symbol': symbol,
            'qty': qty,
            'side': side.name,
            'is_short': is_short,
            'time_in_force': TimeInForce.DAY.name,
            'time': datetime.now(tz=timezone.utc)
        })

        # Track assets as well
        assets = db.assets_quantities
        limits = db.assets_limit
        shorts = db.short_positions  # New collection for short positions

        if side == OrderSide.BUY:
            if is_short:
                # Covering a short position
                shorts.update_one({'symbol': symbol}, {'$inc': {'quantity': -qty}}, upsert=True)
                # If covered completely, remove from shorts
                short_position = shorts.find_one({'symbol': symbol})
                if short_position and short_position['quantity'] <= 0:
                    shorts.delete_one({'symbol': symbol})
                    limits.delete_one({'symbol': symbol, 'is_short': True})
            else:
                # Regular buy
                assets.update_one({'symbol': symbol}, {'$inc': {'quantity': qty}}, upsert=True)
                limits.update_one(
                    {'symbol': symbol, 'is_short': False},
                    {'$set': {'stop_loss_price': stop_loss_price, 'take_profit_price': take_profit_price}},
                    upsert=True
                )
        elif side == OrderSide.SELL:
            if is_short:
                # Short selling
                shorts.update_one({'symbol': symbol}, {'$inc': {'quantity': qty}}, upsert=True)
                limits.update_one(
                    {'symbol': symbol, 'is_short': True},
                    {'$set': {'stop_loss_price': stop_loss_price, 'take_profit_price': take_profit_price}},
                    upsert=True
                )
            else:
                # Regular sell
                assets.update_one({'symbol': symbol}, {'$inc': {'quantity': -qty}}, upsert=True)
                # If sold completely, remove from assets
                asset = assets.find_one({'symbol': symbol})
                if asset and asset['quantity'] <= 0:
                    assets.delete_one({'symbol': symbol})
                    limits.delete_one({'symbol': symbol, 'is_short': False})

        return order
    
    except Exception as e:
        logging.error(f"Error placing order for {symbol}: {e}")
        return None

# Helper to retrieve NASDAQ-100 tickers from MongoDB
def get_ndaq_tickers(mongo_client, FINANCIAL_PREP_API_KEY):
    """
    Connects to MongoDB and retrieves NASDAQ-100 tickers.

    :param mongo_url: MongoDB connection URL
    :return: List of NASDAQ-100 ticker symbols.
    """
    def call_ndaq_100():
        """
        Fetches the list of NASDAQ 100 tickers using the Financial Modeling Prep API and stores it in a MongoDB collection.
        The MongoDB collection is cleared before inserting the updated list of tickers.
        """
        logging.info("Calling NASDAQ 100 to retrieve tickers.")

        def get_jsonparsed_data(url):
            """
            Parses the JSON response from the provided URL.
            
            :param url: The API endpoint to retrieve data from.
            :return: Parsed JSON data as a dictionary.
            """
            response = urlopen(url)
            data = response.read().decode("utf-8")
            return json.loads(data)
        try:
            # API URL for fetching NASDAQ 100 tickers
            ndaq_url = f"https://financialmodelingprep.com/api/v3/nasdaq_constituent?apikey={FINANCIAL_PREP_API_KEY}"
            ndaq_stocks = get_jsonparsed_data(ndaq_url)
            logging.info("Successfully retrieved NASDAQ 100 tickers.")
        except Exception as e:
            logging.error(f"Error fetching NASDAQ 100 tickers: {e}")
            return
        try:
            # MongoDB connection details
            
            db = mongo_client.stock_list
            ndaq100_tickers = db.ndaq100_tickers

            ndaq100_tickers.delete_many({})  # Clear existing data
            ndaq100_tickers.insert_many(ndaq_stocks)  # Insert new data
            logging.info("Successfully inserted NASDAQ 100 tickers into MongoDB.")
        except Exception as e:
            logging.error(f"Error inserting tickers into MongoDB: {e}")
        

    call_ndaq_100()
    
    tickers = [stock['symbol'] for stock in mongo_client.stock_list.ndaq100_tickers.find()]
    
    return tickers

# Market status checker helper
def market_status(trading_client):
    """
    Check market status using the Alpaca Trading API.

    :param trading_client: The Alpaca trading client instance
    :return: Current market status ('open', 'early_hours', 'closed')
    """
    try:
        # Determine premarket hours by substracting 5.5 hours from next open, resulting in 4am on the next open trading day
        # See: https://docs.alpaca.markets/docs/orders-at-alpaca#extended-hours-trading
        status = trading_client.get_clock() 
        early_hours_start = status.next_open - timedelta(hours=5, minutes=30)
        current_time = status.timestamp

        if status.is_open:
            return "open"
        elif current_time > early_hours_start:
            return "early_hours"
        else:
            return "closed"
    except Exception as e:
        logging.error(f"Error retrieving market status: {e}")
        return "error"

# Helper to get latest price
def get_latest_price(ticker):  
    """  
    Fetch the latest price for a given stock ticker using yfinance.  
    
    :param ticker: The stock ticker symbol  
    :return: The latest price of the stock  
    """  
    ticker_yahoo = yf.Ticker(ticker)  
    data = ticker_yahoo.history()
    return round(data['Close'].iloc[-1], 2)


def check_margin_safety(trading_client, ticker, quantity, current_price, order_side, is_short=False):
    """
    Checks if a proposed trade is safe from a margin perspective.
    
    Args:
    - trading_client (TradingClient): Alpaca trading client instance
    - ticker (str): Stock ticker symbol
    - quantity (float): Quantity to trade
    - current_price (float): Current price of the asset
    - order_side (OrderSide): Buy or sell order
    - is_short (bool): Whether this is a short sell order
    
    Returns:
    - bool: True if the trade is safe, False otherwise
    - float: Current margin ratio after the hypothetical trade
    """
    try:
        # Get account info
        account = trading_client.get_account()
        
        # Extract key account values
        equity = float(account.equity)
        buying_power = float(account.regt_buying_power)
        portfolio_value = float(account.portfolio_value)
        long_market_value = float(account.long_market_value)
        short_market_value = float(account.short_market_value)

        # For short positions, check if we'd exceed max short ratio
        if is_short and order_side == OrderSide.SELL:
            trade_value = quantity * current_price
            new_short_value = short_market_value + trade_value
            short_ratio = new_short_value / portfolio_value
            
            # Check if this would exceed our maximum short allocation
            if short_ratio > max_short_ratio:
                logging.warning(f"Short position for {ticker} would exceed max short ratio "
                               f"({short_ratio:.2f} > {max_short_ratio:.2f}). Order cancelled.")
                return False, 0.0
            
            # Check if we have enough liquidity buffer for the short
            required_buffer = trade_value * short_liquidity_buffer
            available_cash = float(account.cash) - trade_liquidity_limit
            
            if available_cash < required_buffer:
                logging.warning(f"Insufficient liquidity buffer for short position on {ticker}. "
                               f"Required: ${required_buffer:.2f}, Available: ${available_cash:.2f}")
                return False, 0.0
        
        # Calculate current margin cushion
        if hasattr(account, 'margin_ratio'):
            current_margin_ratio = float(account.margin_ratio)
        else:
            # If margin_ratio is not available, estimate it
            total_positions_value = long_market_value + short_market_value
            
            # Avoid division by zero
            if total_positions_value == 0:
                current_margin_ratio = 1.0  # No positions, full equity
            else:
                current_margin_ratio = equity / total_positions_value
        
        # Calculate margin impact of the proposed trade
        trade_value = quantity * current_price
        
        # Handle different order types
        if order_side == OrderSide.BUY:
            if is_short:  # Covering a short position
                new_short_value = max(0, short_market_value - trade_value)
                new_margin_ratio = equity / (long_market_value + new_short_value) if (long_market_value + new_short_value) > 0 else 1.0
            else:  # Regular buy
                new_long_value = long_market_value + trade_value
                new_margin_ratio = equity / (new_long_value + short_market_value) if (new_long_value + short_market_value) > 0 else 1.0
        else:  # OrderSide.SELL
            if is_short:  # Short selling
                new_short_value = short_market_value + trade_value
                new_margin_ratio = equity / (long_market_value + new_short_value) if (long_market_value + new_short_value) > 0 else 1.0
            else:  # Regular sell
                new_long_value = max(0, long_market_value - trade_value)
                new_margin_ratio = equity / (new_long_value + short_market_value) if (new_long_value + short_market_value) > 0 else 1.0
        
        # Check if the new margin ratio is above our minimum threshold
        is_safe = new_margin_ratio >= min_margin_ratio
        
        short_info = "SHORT " if is_short else ""
        logging.info(f"Margin check for {ticker} {short_info}{order_side.name} {quantity} @ ${current_price:.2f}: " 
                    f"Current ratio: {current_margin_ratio:.4f}, New ratio: {new_margin_ratio:.4f}, Safe: {is_safe}")
        
        return is_safe, new_margin_ratio
        
    except Exception as e:
        logging.error(f"Error checking margin safety: {e}")
        # Default to conservative approach - assume not safe if we can't calculate
        return False, 0.0


def dynamic_period_selector(ticker):
    """
    Determines the best period to use for fetching historical data.
    
    Args:
    - ticker (str): Stock ticker symbol.
    
    Returns:
    - str: Optimal period for historical data retrieval.
    """
    periods = ['5d', '1mo', '3mo', '6mo', '1y', '2y', '5y', 'ytd', 'max']
    volatility_scores = []

    for period in periods:
        try:
            data = yf.Ticker(ticker).history(period=period)
            if data.empty:
                continue
            
            # Calculate metrics for decision-making
            daily_changes = data['Close'].pct_change().dropna()
            volatility = daily_changes.std()
            trend_strength = abs(data['Close'].iloc[-1] - data['Close'].iloc[0]) / data['Close'].iloc[0]
            
            # Combine metrics into a single score (weight them as desired)
            score = volatility * 0.7 + trend_strength * 0.3
            volatility_scores.append((period, score))
        except Exception as e:
            print(f"Error fetching data for period {period}: {e}")
            continue

    # Select the period with the highest score
    
    optimal_period = min(volatility_scores, key=lambda x: x[1])[0] if volatility_scores else '1y'
    return optimal_period


