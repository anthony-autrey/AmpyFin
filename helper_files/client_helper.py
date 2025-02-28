import os
import functools
import time
import random
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
    enable_short_selling, max_short_ratio, short_liquidity_buffer,
    short_min_margin_ratio, short_max_position_size, 
    short_stop_loss, short_take_profit
)

# Retry decorator for handling transient errors
def retry_with_backoff(max_retries=3, initial_backoff=1, max_backoff=30, backoff_factor=2, 
                      exceptions=(Exception,), on_backoff=None):
    """
    Retry decorator with exponential backoff
    
    Args:
        max_retries: Maximum number of retries before giving up
        initial_backoff: Initial backoff time in seconds
        max_backoff: Maximum backoff time in seconds
        backoff_factor: Factor to increase backoff with each retry
        exceptions: Tuple of exceptions to catch and retry on
        on_backoff: Optional callback function to call when backing off (fn(exception, retry_count, backoff_time))
    
    Returns:
        Decorated function
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            retry_count = 0
            backoff_time = initial_backoff
            
            while True:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    retry_count += 1
                    
                    # If we've reached max retries, re-raise the exception
                    if retry_count > max_retries:
                        logging.error(f"Max retries ({max_retries}) exceeded for {func.__name__}. Last error: {str(e)}")
                        raise
                    
                    # Add some randomness to avoid thundering herd
                    jitter = random.uniform(0, 0.1 * backoff_time)
                    sleep_time = min(backoff_time + jitter, max_backoff)
                    
                    # Log the retry attempt
                    logging.warning(f"Retry {retry_count}/{max_retries} for {func.__name__} after {sleep_time:.2f}s. Error: {str(e)}")
                    
                    # Call the backoff callback if provided
                    if on_backoff:
                        on_backoff(e, retry_count, sleep_time)
                    
                    # Sleep before retrying
                    time.sleep(sleep_time)
                    
                    # Increase backoff for next retry
                    backoff_time = min(backoff_time * backoff_factor, max_backoff)
        
        return wrapper
    return decorator

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

# MongoDB connection helper with retry mechanism
@retry_with_backoff(max_retries=5, initial_backoff=2, max_backoff=60, 
                   exceptions=(ConnectionError, TimeoutError, Exception),
                   on_backoff=lambda e, retry, backoff: logging.warning(f"MongoDB connection attempt {retry} failed: {str(e)}"))
def get_mongo_client(mongo_url):
    """
    Connect to MongoDB with fault tolerance and return the client.
    Includes retry logic in case of connection errors.
    
    Args:
        mongo_url: MongoDB connection URL
        
    Returns:
        MongoDB client instance
        
    Raises:
        ConnectionError: If unable to connect after retries
    """
    try:
        running_locally = os.getenv("MONGO_URL") == "mongodb://mongo:27017/db"
        
        # Set client options with proper timeouts and retryable writes
        client_options = {
            'connectTimeoutMS': 30000,      # 30 seconds connection timeout
            'socketTimeoutMS': 60000,       # 60 seconds socket timeout
            'serverSelectionTimeoutMS': 30000,  # 30 seconds server selection timeout
            'retryWrites': True,            # Enable retryable writes
            'w': 'majority',                # Write concern
            'maxPoolSize': 50,              # Connection pool size
            'minPoolSize': 10,              # Minimum pool size
            'maxIdleTimeMS': 60000,         # Max idle time for connections
        }
        
        if running_locally:
            # TLS not required on the Docker mongo service
            client = MongoClient(mongo_url, **client_options)
        else:
            # Add TLS for non-local connections
            client = MongoClient(mongo_url, tlsCAFile=ca, **client_options)
        
        # Verify connection by making a simple command call
        client.admin.command('ping')
        
        logging.info("Successfully connected to MongoDB")
        return client
    
    except Exception as e:
        logging.error(f"Error connecting to MongoDB: {str(e)}")
        if "Authentication failed" in str(e):
            logging.critical("MongoDB authentication failed. Check credentials.")
            raise ConnectionError("MongoDB authentication failed") from e
        elif "timed out" in str(e).lower():
            logging.error("MongoDB connection timed out")
            raise TimeoutError("MongoDB connection timed out") from e
        else:
            raise ConnectionError(f"Failed to connect to MongoDB: {str(e)}") from e

# Helper to place an order with fault tolerance
@retry_with_backoff(max_retries=3, initial_backoff=1, max_backoff=10, 
                   exceptions=(TimeoutError, ConnectionError),
                   on_backoff=lambda e, retry, backoff: logging.warning(f"Retrying order placement after error: {str(e)}"))
def place_order(trading_client, symbol, side, quantity, mongo_client, is_short=False):
    """
    Place a market order and log the order to MongoDB with fault tolerance.
    Includes margin safety checks to prevent margin calls and retry logic for transient errors.
    Supports both regular buying/selling and short selling.

    :param trading_client: The Alpaca trading client instance
    :param symbol: The stock symbol to trade
    :param side: Order side (OrderSide.BUY or OrderSide.SELL)
    :param qty: Quantity to trade
    :param mongo_client: MongoDB client instance
    :param is_short: Boolean indicating if this is a short sell or buy to cover
    :return: Order result from Alpaca API or None if margin safety check fails
    """
    # Use a unique trade ID to track this order through retries
    trade_id = f"{symbol}_{side.name}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    
    # Check if short selling is enabled
    if is_short and not enable_short_selling:
        logging.warning(f"Attempted short selling for {symbol} but short selling is disabled. "
                      f"Enable it by setting ENABLE_SHORT_SELLING=True in your environment.")
        return None
    
    try:
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
            time_in_force=TimeInForce.DAY,
            client_order_id=trade_id  # Use trade_id for idempotency
        )
        
        # Submit the order with exception handling
        try:
            order = trading_client.submit_order(market_order_data)
        except Exception as order_error:
            # Check if this is a transient error that should be retried
            error_str = str(order_error).lower()
            if any(phrase in error_str for phrase in ['timeout', 'connection', 'network', 'temporarily unavailable']):
                logging.warning(f"Transient error placing order for {symbol}: {order_error}")
                raise TimeoutError(f"Order placement timeout: {order_error}") from order_error
            elif 'rate limit' in error_str or 'too many requests' in error_str:
                logging.warning(f"Rate limit hit when placing order for {symbol}")
                raise ConnectionError(f"API rate limit exceeded: {order_error}") from order_error
            else:
                # Non-transient error, don't retry
                logging.error(f"Error placing order for {symbol}: {order_error}")
                return None
        
        # Order successfully placed
        qty = round(quantity, 3)
        
        # Calculate stop loss and take profit differently for short vs long positions
        if is_short and side == OrderSide.SELL:
            # For short positions, stop loss is price going up, take profit is price going down
            # Use short-specific thresholds
            stop_loss_price = round(current_price * (1 + short_stop_loss), 2)  # e.g. 3% increase
            take_profit_price = round(current_price * (1 - short_take_profit), 2)  # e.g. 5% decrease
        else:
            # For long positions, or when covering shorts
            stop_loss_price = round(current_price * (1 - stop_loss), 2)  # e.g. 3% decrease
            take_profit_price = round(current_price * (1 + take_profit), 2)  # e.g. 5% increase

        # Log trade details to MongoDB with exception handling
        try:
            db = mongo_client.trades
            
            # Check if we already logged this trade (in case of retry)
            existing_trade = db.paper.find_one({'trade_id': trade_id})
            if not existing_trade:
                # Only insert if this is not a duplicate
                db.paper.insert_one({
                    'trade_id': trade_id,
                    'symbol': symbol,
                    'qty': qty,
                    'side': side.name,
                    'is_short': is_short,
                    'time_in_force': TimeInForce.DAY.name,
                    'time': datetime.now(tz=timezone.utc),
                    'price': current_price,
                    'order_id': order.id
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
        except Exception as db_error:
            # Database error shouldn't invalidate the order
            logging.error(f"Error updating database for order {trade_id}: {db_error}")
            # Continue since the order was placed successfully

        return order
    
    except (TimeoutError, ConnectionError) as e:
        # These will be caught by the retry decorator
        raise
    except Exception as e:
        # Unexpected error
        logging.error(f"Unexpected error in place_order for {symbol}: {e}")
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

# Market status checker helper with retry logic
@retry_with_backoff(max_retries=5, initial_backoff=1, max_backoff=15, 
                   exceptions=(TimeoutError, ConnectionError, Exception),
                   on_backoff=lambda e, retry, backoff: logging.warning(f"Retrying market status check after error: {str(e)}"))
def market_status(trading_client):
    """
    Check market status using the Alpaca Trading API with fault tolerance.
    Includes retry logic for transient errors.

    :param trading_client: The Alpaca trading client instance
    :return: Current market status ('open', 'early_hours', 'closed', 'error')
    """
    try:
        # Cache to prevent excessive API calls if we encounter partial failures
        cache_file = "/tmp/market_status_cache.json"
        cache_expiry = 60  # cache validity in seconds
        
        # Check if we have a recent cache
        try:
            if os.path.exists(cache_file):
                cache_time = os.path.getmtime(cache_file)
                if time.time() - cache_time < cache_expiry:
                    with open(cache_file, 'r') as f:
                        import json
                        cached_data = json.load(f)
                        logging.debug("Using cached market status")
                        return cached_data.get("status", "error")
        except Exception as cache_error:
            logging.debug(f"Error reading cache: {cache_error}")
        
        # Make the API call
        try:
            # Determine premarket hours by substracting 5.5 hours from next open, resulting in 4am on the next open trading day
            # See: https://docs.alpaca.markets/docs/orders-at-alpaca#extended-hours-trading
            status = trading_client.get_clock() 
            early_hours_start = status.next_open - timedelta(hours=5, minutes=30)
            current_time = status.timestamp

            # Determine market status
            if status.is_open:
                result = "open"
            elif current_time > early_hours_start:
                result = "early_hours"
            else:
                result = "closed"
                
            # Cache the result
            try:
                with open(cache_file, 'w') as f:
                    import json
                    json.dump({"status": result, "timestamp": time.time()}, f)
            except Exception as write_error:
                logging.debug(f"Error writing cache: {write_error}")
                
            return result
            
        except Exception as api_error:
            error_str = str(api_error).lower()
            if any(phrase in error_str for phrase in ['timeout', 'connection', 'network', 'temporarily unavailable']):
                logging.warning(f"Transient error checking market status: {api_error}")
                raise TimeoutError(f"Market status check timeout: {api_error}") from api_error
            elif 'rate limit' in error_str or 'too many requests' in error_str:
                logging.warning(f"Rate limit hit when checking market status")
                raise ConnectionError(f"API rate limit exceeded: {api_error}") from api_error
            else:
                raise
    
    except (TimeoutError, ConnectionError) as e:
        # Will be caught by retry decorator
        raise
        
    except Exception as e:
        logging.error(f"Error retrieving market status: {e}")
        
        # Check if we have any cached data as fallback
        try:
            if os.path.exists(cache_file):
                with open(cache_file, 'r') as f:
                    import json
                    cached_data = json.load(f)
                    cache_age = time.time() - cached_data.get("timestamp", 0)
                    # Use cached status if it's not too old (10 minutes max)
                    if cache_age < 600:
                        logging.warning(f"Using cached market status ({cache_age:.0f}s old) due to error")
                        return cached_data.get("status", "error")
        except Exception:
            pass
            
        return "error"

# Helper to get latest price
@retry_with_backoff(max_retries=3, initial_backoff=1, 
                  exceptions=(Exception,), 
                  on_backoff=lambda e, retry, backoff: logging.warning(f"Retrying price fetch for ticker after error: {str(e)}"))
def get_latest_price(ticker):  
    """  
    Fetch the latest price for a given stock ticker using yfinance with retry logic.
    Will retry up to 3 times with exponential backoff if the request fails.
    
    :param ticker: The stock ticker symbol  
    :return: The latest price of the stock  
    """  
    try:
        ticker_yahoo = yf.Ticker(ticker)  
        data = ticker_yahoo.history()
        
        if data.empty:
            raise ValueError(f"No data returned for ticker {ticker}")
            
        if 'Close' not in data.columns:
            raise KeyError(f"Close column not found in data for ticker {ticker}")
            
        price = data['Close'].iloc[-1]
        if not (isinstance(price, (int, float)) and price > 0):
            raise ValueError(f"Invalid price value for {ticker}: {price}")
            
        return round(price, 2)
    except IndexError as e:
        logging.error(f"IndexError getting price for {ticker}: {e}")
        raise ValueError(f"Could not get price data for {ticker}") from e
    except Exception as e:
        logging.error(f"Unexpected error getting price for {ticker}: {e}")
        raise


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

        # Calculate trade value
        trade_value = quantity * current_price
        
        # For short positions, check if we'd exceed max short ratio and position size
        if is_short and order_side == OrderSide.SELL:
            # Check position size limit
            if trade_value > short_max_position_size:
                logging.warning(f"Short position for {ticker} would exceed max position size "
                              f"(${trade_value:.2f} > ${short_max_position_size:.2f}). Order cancelled.")
                return False, 0.0
            
            # Check portfolio ratio limit
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
        
        # Handle different order types to calculate new margin ratio
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
        
        # Use different margin thresholds for short vs long positions
        required_margin_ratio = short_min_margin_ratio if is_short else min_margin_ratio
        
        # Check if the new margin ratio is above our minimum threshold
        is_safe = new_margin_ratio >= required_margin_ratio
        
        short_info = "SHORT " if is_short else ""
        # Only log at INFO level if it's potentially unsafe, otherwise log at DEBUG level to reduce noise
        if new_margin_ratio < required_margin_ratio * 1.2:  # Within 20% of the minimum threshold
            logging.info(f"Margin check for {ticker} {short_info}{order_side.name} {quantity} @ ${current_price:.2f}: " 
                       f"Current ratio: {current_margin_ratio:.4f}, New ratio: {new_margin_ratio:.4f}, "
                       f"Threshold: {required_margin_ratio:.4f}, Safe: {is_safe}")
        else:
            logging.debug(f"Margin check for {ticker} {short_info}{order_side.name} {quantity} @ ${current_price:.2f}: " 
                        f"Current ratio: {current_margin_ratio:.4f}, New ratio: {new_margin_ratio:.4f}, "
                        f"Threshold: {required_margin_ratio:.4f}, Safe: {is_safe}")
        
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


