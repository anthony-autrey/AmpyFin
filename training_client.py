from statistics import median
from config_variables import FINANCIAL_PREP_API_KEY, API_KEY, API_SECRET, BASE_URL, MONGO_URL
from datetime import datetime, timedelta
from strategies.talib_indicators import *
import yfinance as yf
import logging
from collections import Counter
from trading_client import market_status, weighted_majority_decision_and_median_quantity, ExceptionStats
from helper_files.client_helper import strategies, get_latest_price, get_ndaq_tickers, dynamic_period_selector, get_mongo_client, calculate_safe_quantity
from datetime import datetime 
import heapq 
import certifi
import pandas as pd
ca = certifi.where()

# Set up logging configuration similar to trading_client.py
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler('training_system.log'),  # Log messages to a file
        logging.StreamHandler()             # Log messages to the console
    ]
)

# Custom logger setup for more controlled console output
console_logger = logging.getLogger('console')

if not console_logger.handlers:
    console_logger.setLevel(logging.INFO)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter('%(message)s')  # Simplified format for console
    console_handler.setFormatter(console_formatter)
    console_logger.addHandler(console_handler)
    console_logger.propagate = False  # Prevent double logging

# Setup exception tracking
exception_tracker = ExceptionStats()

from control import mode, train_time_delta_mode, train_time_delta_increment, train_time_delta_multiplicative, train_time_delta_balanced, train_rank_liquidity_limit, train_rank_asset_limit
from control import train_profit_price_change_ratio_d1, train_profit_profit_time_d1, train_profit_price_change_ratio_d2, train_profit_profit_time_d2, train_profit_profit_time_else
from control import train_loss_price_change_ratio_d1, train_loss_price_change_ratio_d2, train_loss_profit_time_d1, train_loss_profit_time_d2, train_loss_profit_time_else
from control import period_start, period_end, train_tickers, train_stop_loss, train_take_profit, train_start_cash, train_trade_liquidity_limit, train_trade_asset_limit
from control import train_data_path, pragmatic_buying_power_factor, pragmatic_over_hold_factor, enable_short_selling
import json
from ranking_client import update_ranks
from helper_files.train_client_helper import *

def train():
    """
    initialize
    """
    ticker_price_history = {}
    trading_simulator = {}
    points = {}
    global train_tickers
    """
    need it for time_delta component and we need to adapt time delta for multiple modes - multiplicative, balanced or additive
    """
    for strategy in strategies:
        points[strategy.__name__] = 0
        trading_simulator[strategy.__name__] = {
            "holdings": {},
            "amount_cash": train_start_cash,
            "total_trades": 0,
            "successful_trades": 0,
            "neutral_trades": 0,
            "failed_trades": 0,
            "portfolio_value": train_start_cash
        }
    ideal_period = {}
    time_delta = 0.01
    mongo_client = get_mongo_client(MONGO_URL)
    db = mongo_client.IndicatorsDatabase
    indicator_collection = db.Indicators
    for strategy in strategies:
        period = indicator_collection.find_one({'indicator': strategy.__name__})
        ideal_period[strategy.__name__] = period['ideal_period']
    
    start_date = datetime.strptime(period_start, "%Y-%m-%d")
    data_start_date = (start_date - timedelta(days=730)).strftime("%Y-%m-%d")
    print(f"Will be using {train_tickers} for training")
    if len(train_tickers) == 0:
        train_tickers = get_ndaq_tickers(mongo_client, FINANCIAL_PREP_API_KEY)

    for ticker in train_tickers:
        try:
            data = yf.Ticker(ticker).history(start=data_start_date, end=period_end, interval="1d")
            logging.info(f'Got data: {ticker}  \t {data.iloc[0].name.date()} to {data.iloc[-1].name.date()}')
            ticker_price_history[ticker] = data
        except:
            data = yf.Ticker(ticker).history(period="max", interval="1d")
            logging.info(f'Got data: {ticker}  \t {data.iloc[0].name.date()} to {data.iloc[-1].name.date()}')
            ticker_price_history[ticker] = data
    
    
    """
    now we have the data loaded, we need to simulate strategy for each day from start day to end day. create a loop that goes from start to end date
    """
    # Now simulate strategy for each day from start date to end date
    start_date = datetime.strptime(period_start, "%Y-%m-%d")
    end_date = datetime.strptime(period_end, "%Y-%m-%d")
    current_date = start_date
    mongo_client = get_mongo_client(MONGO_URL)


    print(f"Training on tickers: {train_tickers}")
    
    while current_date <= end_date:
        print(f"Simulating strategies for date: {current_date.strftime('%Y-%m-%d')}")
        if current_date.weekday() >= 5:
            current_date += timedelta(days=1)
            continue
        if current_date.strftime('%Y-%m-%d') not in ticker_price_history[train_tickers[0]].index:
            current_date += timedelta(days=1)
            continue
        for ticker in train_tickers:
            """
            what we need to simulate:
            1. strategy - completed
            2. historical data - must give historical data that is ideal period days/months/years before the current date to current date
            3. current_price - get from trading simulator
            4. account_cash - get from trading_simulator
            5. holdings - get from trading_simulator
            6. total_portfolio_value
            """
            if current_date.strftime('%Y-%m-%d') in ticker_price_history[ticker].index:
                daily_data = ticker_price_history[ticker].loc[current_date.strftime('%Y-%m-%d')]
                current_price = daily_data['Close']
                for strategy in strategies:
                    historical_data = get_historical_data(ticker, current_date, ideal_period[strategy.__name__], ticker_price_history)
                    account_cash = trading_simulator[strategy.__name__]["amount_cash"]
                    portfolio_qty = trading_simulator[strategy.__name__]["holdings"].get(ticker, {}).get("quantity", 0)
                    total_portfolio_value = trading_simulator[strategy.__name__]["portfolio_value"]
                    decision, qty = simulate_strategy(
                        strategy, ticker, current_price, historical_data, account_cash, portfolio_qty, total_portfolio_value
                    )
                    # print(f"{strategy.__name__} - {decision} - {qty} - {ticker}")
                    """
                    now simulate the trade
                    """
                    if decision == "buy" and trading_simulator[strategy.__name__]["amount_cash"] > train_rank_liquidity_limit and qty > 0 and ((portfolio_qty + qty) * current_price) / total_portfolio_value < train_rank_asset_limit:
                        trading_simulator[strategy.__name__]["amount_cash"] -= qty * current_price
                    
                        if ticker in trading_simulator[strategy.__name__]["holdings"]:
                            trading_simulator[strategy.__name__]["holdings"][ticker]["quantity"] += qty
                        else:
                            trading_simulator[strategy.__name__]["holdings"][ticker] = {"quantity": qty}
                    
                        trading_simulator[strategy.__name__]["holdings"][ticker]["price"] = current_price
                        trading_simulator[strategy.__name__]["total_trades"] += 1
                        
                    elif decision == "sell" and trading_simulator[strategy.__name__]["holdings"].get(ticker, {}).get("quantity", 0) >= qty:
                        trading_simulator[strategy.__name__]["amount_cash"] += qty * current_price
                        ratio = current_price / trading_simulator[strategy.__name__]["holdings"][ticker]["price"]
                        if current_price > trading_simulator[strategy.__name__]["holdings"][ticker]["price"]:
                            trading_simulator[strategy.__name__]["successful_trades"] += 1
                            if ratio < train_profit_price_change_ratio_d1:
                                points[strategy.__name__] = points.get(strategy.__name__, 0) + time_delta * train_profit_profit_time_d1
                            elif ratio < train_profit_price_change_ratio_d2:
                                points[strategy.__name__] = points.get(strategy.__name__, 0) + time_delta * train_profit_profit_time_d2
                            else:
                                points[strategy.__name__] = points.get(strategy.__name__, 0) + time_delta * train_profit_profit_time_else
                            """
                            points[strategy.__name__] = points.get(strategy.__name__, 0) + time_delta * train_profit_profit_time_d1
                            """
                        elif current_price == trading_simulator[strategy.__name__]["holdings"][ticker]["price"]:
                            trading_simulator[strategy.__name__]["neutral_trades"] += 1
                        else:
                            trading_simulator[strategy.__name__]["failed_trades"] += 1
                            if ratio > train_loss_price_change_ratio_d1:
                                points[strategy.__name__] = points.get(strategy.__name__, 0) + -time_delta * train_loss_profit_time_d1
                            elif ratio > train_loss_price_change_ratio_d2:
                                points[strategy.__name__] = points.get(strategy.__name__, 0) + -time_delta * train_loss_profit_time_d2
                            else:
                                points[strategy.__name__] = points.get(strategy.__name__, 0) + -time_delta * train_loss_profit_time_else

                        trading_simulator[strategy.__name__]["holdings"][ticker]["quantity"] -= qty
                        if trading_simulator[strategy.__name__]["holdings"][ticker]["quantity"] == 0:
                            del trading_simulator[strategy.__name__]["holdings"][ticker]
                        elif trading_simulator[strategy.__name__]["holdings"][ticker]["quantity"] < 0:
                            Exception("Quantity cannot be negative")
                        trading_simulator[strategy.__name__]["total_trades"] += 1
        active_count, trading_simulator = local_update_portfolio_values(current_date, strategies, trading_simulator, ticker_price_history) 
        """
        log history of trading_simulator and points
        """

        logging.info("-------------------------------------------------")
        for strategy in strategies:
            logging.info(f"\t\t{strategy.__name__}: ${trading_simulator[strategy.__name__]['portfolio_value']}")
        logging.info(f"Date: {current_date.strftime('%Y-%m-%d')}")
        logging.info(f"time_delta: {time_delta}")
        logging.info(f"Active count: {active_count}")
        logging.info("-------------------------------------------------")
        
        """
        Update time_delta based on the mode
        """
        if train_time_delta_mode == 'additive':
            time_delta += train_time_delta_increment
        elif train_time_delta_mode == 'multiplicative':
            time_delta *= train_time_delta_multiplicative
        elif train_time_delta_mode == 'balanced':
            time_delta += train_time_delta_balanced * time_delta


        current_date += timedelta(days=1)
        
    results = {
        "trading_simulator": trading_simulator,
        "points": points,
        "date": current_date.strftime('%Y-%m-%d'),
        "time_delta": time_delta
        }
        
    with open(train_data_path, 'w') as json_file:
        json.dump(results, json_file, indent=4)

    """
    output onto console top 10 strategies with highest portfolio values and top 10 strategies with highest points
    """
    top_portfolio_values = heapq.nlargest(10, trading_simulator.items(), key=lambda x: x[1]["portfolio_value"])
    top_points = heapq.nlargest(10, points.items(), key=lambda x: x[1])
    print("Top 10 strategies with highest portfolio values")
    for strategy, value in top_portfolio_values:
        print(f"{strategy} - {value['portfolio_value']}")
    print("Top 10 strategies with highest points")
    for strategy, value in top_points:
        print(f"{strategy} - {value}")
    print("Training completed.")
   
def push():
    with open(train_data_path, 'r') as json_file:
         results = json.load(json_file)
         trading_simulator = results['trading_simulator']
         points = results['points']
         date = results['date']
         time_delta = results['time_delta']

    # Push the trading simulator and points to the database
    mongo_client = get_mongo_client(MONGO_URL)
    db = mongo_client.trading_simulator
    holdings_collection = db.algorithm_holdings
    points_collection = db.points_tally
    for strategy, value in trading_simulator.items():
        holdings_collection.update_one(
            {"strategy": strategy},
            {
                "$set": {
                    "holdings": value["holdings"],
                    "amount_cash": value["amount_cash"],
                    "total_trades": value["total_trades"],
                    "successful_trades": value["successful_trades"],
                    "neutral_trades": value["neutral_trades"],
                    "failed_trades": value["failed_trades"],
                    "portfolio_value": value["portfolio_value"],
                    "last_updated": datetime.now(),
                    "initialized_date": datetime.now()
                }
            },
            upsert=True
        )
    for strategy, value in points.items():
        points_collection.update_one(
            {"strategy": strategy},
            {
                "$set": {
                    "total_points": value,
                    "last_updated": datetime.now(),
                    "initialized_date": datetime.now()
                }
            },
            upsert=True
        )
    db.time_delta.update_one({}, {"$set": {"time_delta": time_delta}}, upsert=True)
    update_ranks(mongo_client)

def test():
    with open(train_data_path, 'r') as json_file:
         results = json.load(json_file)
         trading_simulator = results['trading_simulator']
         points = results['points']
         date = results['date']
         time_delta = results['time_delta']
    print(trading_simulator)
    print(points)
    print(date)
    print(time_delta)
    ticker_price_history = {}
    ideal_period = {}
    
    mongo_client = get_mongo_client(MONGO_URL)
    db = mongo_client.trading_simulator
    r_t_c = db.rank_to_coefficient

    rank_to_coefficient = {}
    for doc in r_t_c.find({}):
        rank_to_coefficient[doc['rank']] = doc['coefficient']
    print("Rank Coefficient Retrieved")

    db = mongo_client.IndicatorsDatabase
    indicator_collection = db.Indicators
    for strategy in strategies:
        period = indicator_collection.find_one({'indicator': strategy.__name__})
        ideal_period[strategy.__name__] = period['ideal_period']
    global train_tickers
    if not train_tickers:
        train_tickers = get_ndaq_tickers(mongo_client, FINANCIAL_PREP_API_KEY)
    start_date = datetime.strptime(period_start, "%Y-%m-%d")
    data_start_date = (start_date - timedelta(days=730)).strftime("%Y-%m-%d")
    print(f"Will be using {train_tickers} for training")
    
    for ticker in train_tickers:
        try:
            data = yf.Ticker(ticker).history(start=data_start_date, end=period_end, interval="1d")
            logging.info(f'Got data: {ticker}  \t {data.iloc[0].name.date()} to {data.iloc[-1].name.date()}')
            ticker_price_history[ticker] = data
        except:
            data = yf.Ticker(ticker).history(period="max", interval="1d")
            logging.info(f'Got data: {ticker}  \t {data.iloc[0].name.date()} to {data.iloc[-1].name.date()}')
            ticker_price_history[ticker] = data
    start_date = datetime.strptime(period_start, "%Y-%m-%d")
    end_date = datetime.strptime(period_end, "%Y-%m-%d")
    current_date = start_date
    rank = {}
    """
    we assign strategy a rank
    """
    def update_ranks():
        q = []
        for strategy in strategies:
            if points[strategy.__name__] > 0:
                heapq.heappush(q, (points[strategy.__name__] * 2 + trading_simulator[strategy.__name__]["portfolio_value"], trading_simulator[strategy.__name__]["successful_trades"] - trading_simulator[strategy.__name__]["failed_trades"], trading_simulator[strategy.__name__]["amount_cash"], strategy.__name__))
            else:
                heapq.heappush(q, (trading_simulator[strategy.__name__]["portfolio_value"], trading_simulator[strategy.__name__]["successful_trades"] - trading_simulator[strategy.__name__]["failed_trades"], trading_simulator[strategy.__name__]["amount_cash"], strategy.__name__))
        coeff_rank = 1
        while q:
            _, _, _, strategy_name = heapq.heappop(q)
            rank[strategy_name] = coeff_rank
            coeff_rank+=1
            
        console_logger.info(f"🏆 Updated strategy rankings")
        return rank

    strategy_to_coefficient = {}
    account = {
        "holdings": {},
        "short_positions": {},
        "cash": train_start_cash,
        "trades" : [],
        "total_portfolio_value": train_start_cash
    }
    rank = update_ranks()
    print(rank)
    account_values = pd.Series(index=pd.date_range(start=start_date, end=end_date))
    
    while current_date <= end_date:
        print(f"Simulating strategies for date: {current_date.strftime('%Y-%m-%d')}")
        if current_date.weekday() >= 5:
            current_date += timedelta(days=1)
            continue
        if current_date.strftime('%Y-%m-%d') not in ticker_price_history[train_tickers[0]].index:
            current_date += timedelta(days=1)
            continue
        
        """
        simulate early hour operations
        - retrieve rank and assign to new coefficient
        """
        # print(f"rank_to_coefficient: {rank_to_coefficient}")
        
        for strategy in strategies:
            strategy_to_coefficient[strategy.__name__] = rank_to_coefficient[rank[strategy.__name__]]
        # print(f"strategy_to_coefficient: {strategy_to_coefficient}")
        """
        simulate trading
        check stop loss + take profit and buy & sell in accordance to ranking
        """
        buy_heap = []
        for ticker in train_tickers:
            if current_date.strftime('%Y-%m-%d') in ticker_price_history[ticker].index:
                daily_data = ticker_price_history[ticker].loc[current_date.strftime('%Y-%m-%d')]
                current_price = daily_data['Close']
                """
                check stop loss + take profit for both long and short positions
                """
                # Check stop loss/take profit for long positions
                if ticker in account["holdings"]:
                    if account["holdings"][ticker]["quantity"] > 0:
                        if current_price < account["holdings"][ticker]["stop_loss"] or current_price > account["holdings"][ticker]["take_profit"]:
                            quantity = account["holdings"][ticker]["quantity"]
                            console_logger.info(f"🔴 SELL {ticker}: {quantity} shares @ ${current_price:.2f} (stop-loss/take-profit)")
                            account["trades"].append({"symbol": ticker, "quantity": quantity, "price": current_price, "action": "sell", "date": current_date.strftime('%Y-%m-%d')})
                            account["cash"] += quantity * current_price
                            del account["holdings"][ticker]
                
                # Check stop loss/take profit for short positions
                if "short_positions" in account and ticker in account["short_positions"]:
                    if account["short_positions"][ticker]["quantity"] > 0:
                        # For short positions, stop loss is price going up, take profit is price going down
                        if current_price >= account["short_positions"][ticker]["stop_loss"] or current_price <= account["short_positions"][ticker]["take_profit"]:
                            quantity = account["short_positions"][ticker]["quantity"]
                            condition = "stop-loss" if current_price >= account["short_positions"][ticker]["stop_loss"] else "take-profit"
                            console_logger.info(f"🟢 COVER {ticker}: {quantity} shares @ ${current_price:.2f} ({condition})")
                            account["trades"].append({"symbol": ticker, "quantity": quantity, "price": current_price, "action": "cover", "date": current_date.strftime('%Y-%m-%d')})
                            del account["short_positions"][ticker]
                """
                now simulate strategies and store 
                """
                
                decisions_and_quantities = []
                portfolio_qty = 0.0
                short_qty = 0.0
                
                # Check if ticker is in short positions
                if "short_positions" in account and ticker in account["short_positions"]:
                    short_qty = account["short_positions"][ticker]["quantity"]
                
                for strategy in strategies:
                    historical_data = get_historical_data(ticker, current_date, ideal_period[strategy.__name__], ticker_price_history)
                    account_cash = account["cash"]
                    portfolio_qty = account["holdings"][ticker]["quantity"] if ticker in account["holdings"] else 0
                    total_portfolio_value = account["total_portfolio_value"]
                    decision, qty = simulate_strategy(strategy, ticker, current_price, historical_data, account_cash, portfolio_qty, total_portfolio_value)
                    weight = strategy_to_coefficient[strategy.__name__]
                    decisions_and_quantities.append((decision, qty, weight))
                # Extract buy and sell quantities from decisions for pragmatic trades
                buy_quantities = [quantity for decision, quantity, _ in decisions_and_quantities if decision == 'buy']
                short_quantities = [quantity for decision, quantity, _ in decisions_and_quantities if decision == 'short']
                
                decision, quantity, buy_weight, sell_weight, hold_weight, short_weight = weighted_majority_decision_and_median_quantity(decisions_and_quantities)
                pragmatic_buy_quantity = median(buy_quantities) if buy_quantities else 0
                pragmatic_short_quantity = median(short_quantities) if short_quantities else 0
                
                # Check for short positions
                short_position = account.get("short_positions", {}).get(ticker, {"quantity": 0})
                short_qty = short_position.get("quantity", 0)
                
                # Mirror trading_client.py's pragmatic condition logic
                buy_condition = decision == "buy" and float(account["cash"]) > train_trade_liquidity_limit and (((quantity + portfolio_qty) * current_price) / account["total_portfolio_value"]) < train_trade_asset_limit
                
                # Check for buy condition with less restrictive requirements
                pragmatic_buy_condition = (float(account["cash"]) > (train_trade_liquidity_limit * pragmatic_buying_power_factor) and
                    buy_weight > (hold_weight * pragmatic_over_hold_factor) and
                    buy_weight > sell_weight and 
                    buy_weight > short_weight and
                    pragmatic_buy_quantity > 0)
                    
                # Mirror trading_client.py's short condition logic
                short_condition = decision == "short" and enable_short_selling and short_qty == 0
                
                # Mirror trading_client.py's pragmatic short condition logic
                pragmatic_short_condition = (enable_short_selling and 
                    short_qty == 0 and
                    float(account["cash"]) > (train_trade_liquidity_limit * pragmatic_buying_power_factor) and
                    short_weight > (hold_weight * pragmatic_over_hold_factor) and
                    short_weight > buy_weight and 
                    short_weight > sell_weight and
                    pragmatic_short_quantity > 0)
                
                # Check if we need to cover a short position first
                if decision == "buy" and short_qty > 0:
                    # Buy to cover short positions
                    console_logger.info(f"🟢 COVER {ticker}: {short_qty} shares @ ${current_price:.2f}")
                    cover_qty = min(quantity, short_qty)
                    safe_cover_qty = cover_qty  # In simulation we don't need actual margin check
                    
                    account["trades"].append({"symbol": ticker, "quantity": safe_cover_qty, "price": current_price, "action": "cover", "date": current_date.strftime('%Y-%m-%d')})
                    
                    # Update short positions
                    account["short_positions"][ticker]["quantity"] -= safe_cover_qty
                    if account["short_positions"][ticker]["quantity"] <= 0:
                        del account["short_positions"][ticker]
                
                # Implement same buy heap logic as trading_client
                elif buy_condition or pragmatic_buy_condition:
                    buy_type = "standard" if buy_condition else "pragmatic"
                    # Use appropriate quantity based on condition type
                    actual_quantity = quantity if buy_condition else pragmatic_buy_quantity
                    console_logger.info(f"Adding {ticker} to buy heap: {actual_quantity} shares ({buy_type} buy)")
                    heapq.heappush(buy_heap, (-(buy_weight-(sell_weight + short_weight + (hold_weight * 0.5))), actual_quantity, ticker, buy_type))
                
                # Implement short selling like trading_client
                elif short_condition or pragmatic_short_condition:
                    short_type = "standard" if short_condition else "pragmatic"
                    # Use appropriate quantity based on condition type
                    actual_quantity = quantity if short_condition else pragmatic_short_quantity
                    
                    # Short selling with asset limit check
                    short_position_value = (actual_quantity + short_qty) * current_price
                    short_position_ratio = short_position_value / account["total_portfolio_value"]
                    
                    # Check if this short would exceed our per-ticker asset limit
                    if short_position_ratio > train_trade_asset_limit:
                        # Adjust quantity to stay within limits
                        adjusted_quantity = int((train_trade_asset_limit * account["total_portfolio_value"]) / current_price)
                        if adjusted_quantity < 1:
                            logging.info(f"Cannot short {ticker}: position would exceed asset limit {train_trade_asset_limit:.2f} of portfolio")
                            continue
                        actual_quantity = adjusted_quantity
                    
                    console_logger.info(f"🔵 SHORT {ticker}: {actual_quantity} shares @ ${current_price:.2f} ({short_type} short)")
                    actual_quantity = max(actual_quantity, 1)
                    safe_quantity = actual_quantity  # In simulation we don't need actual margin check
                    
                    account["trades"].append({"symbol": ticker, "quantity": safe_quantity, "price": current_price, "action": "short", "date": current_date.strftime('%Y-%m-%d')})
                    
                    # Setup short positions tracking
                    if ticker not in account["short_positions"]:
                        account["short_positions"][ticker] = {"quantity": 0, "price": current_price}
                    account["short_positions"][ticker]["quantity"] += safe_quantity
                    account["short_positions"][ticker]["price"] = current_price
                    account["short_positions"][ticker]["stop_loss"] = current_price * (1 + train_take_profit)
                    account["short_positions"][ticker]["take_profit"] = current_price * (1 - train_stop_loss)
                
                elif decision == 'sell' and ticker in account["holdings"]:
                    console_logger.info(f"🔴 SELL {ticker}: {quantity} shares @ ${current_price:.2f}")
                    quantity = max(quantity, 1)
                    # Calculate safe quantity for simulation
                    safe_quantity = quantity  # No actual margin check in simulator but keeps flow consistent
                    
                    """
                    execute sell on spot
                    """
                    account["trades"].append({"symbol": ticker, "quantity": safe_quantity, "price": current_price, "action": "sell", "date": current_date.strftime('%Y-%m-%d')})
                    quantity = account["holdings"][ticker]["quantity"]
                    account["cash"] += quantity * current_price
                    del account["holdings"][ticker]

        # Process buy heap only - suggestion heap is removed to match trading_client
        while buy_heap and float(account["cash"]) > train_trade_liquidity_limit:
            heap_item = heapq.heappop(buy_heap)
            # Handle both old and new format with buy_type
            if len(heap_item) == 4:  # New format with buy_type
                _, quantity, ticker, buy_type = heap_item
                console_logger.info(f"🟢 BUY {ticker}: {quantity} shares @ ${ticker_price_history[ticker].loc[current_date.strftime('%Y-%m-%d')]['Close']:.2f} ({buy_type} buy)")
            else:  # Old format without buy_type
                _, quantity, ticker = heap_item
                buy_type = "standard"
                console_logger.info(f"🟢 BUY {ticker}: {quantity} shares @ ${ticker_price_history[ticker].loc[current_date.strftime('%Y-%m-%d')]['Close']:.2f}")
            
            current_price = ticker_price_history[ticker].loc[current_date.strftime('%Y-%m-%d')]['Close']
            safe_quantity = quantity  # In simulation we don't need actual margin check
            
            account["trades"].append({"symbol": ticker, "quantity": safe_quantity, "price": current_price, "action": "buy", "date": current_date.strftime('%Y-%m-%d')})
            account["cash"] -= safe_quantity * current_price
            account["holdings"][ticker] = {"quantity": safe_quantity, "price": current_price, "stop_loss": current_price * (1 - train_stop_loss), "take_profit": current_price * (1 + train_take_profit)}
                
        buy_heap = []
        # logging.info("-------------------------------------------------")
        # logging.info(f"Account Cash: ${account['cash']:,.2f}")
        # logging.info(f"Trades: {account['trades']}")
        # logging.info(f"Holdings: {account['holdings']}")
        # logging.info(f"Total Portfolio Value: ${account['total_portfolio_value']:,.2f}")
        
        # logging.info("-------------------------------------------------")
        # time.sleep(5)
        """
        simulate ranking
        """
        for ticker in train_tickers:
            """
            what we need to simulate:
            1. strategy - completed
            2. historical data - must give historical data that is ideal period days/months/years before the current date to current date
            3. current_price - get from trading simulator
            4. account_cash - get from trading_simulator
            5. holdings - get from trading_simulator
            6. total_portfolio_value
            """
            if current_date.strftime('%Y-%m-%d') in ticker_price_history[ticker].index:
                daily_data = ticker_price_history[ticker].loc[current_date.strftime('%Y-%m-%d')]
                current_price = daily_data['Close']
                for strategy in strategies:
                    historical_data = get_historical_data(ticker, current_date, ideal_period[strategy.__name__], ticker_price_history)
                    account_cash = trading_simulator[strategy.__name__]["amount_cash"]
                    portfolio_qty = trading_simulator[strategy.__name__]["holdings"].get(ticker, {}).get("quantity", 0)
                    total_portfolio_value = trading_simulator[strategy.__name__]["portfolio_value"]
                    decision, qty = simulate_strategy(
                        strategy, ticker, current_price, historical_data, account_cash, portfolio_qty, total_portfolio_value
                    )
                    # print(f"{strategy.__name__} - {decision} - {qty} - {ticker}")
                    """
                    now simulate the trade
                    """
                    if decision == "buy" and trading_simulator[strategy.__name__]["amount_cash"] > train_rank_liquidity_limit and qty > 0 and ((portfolio_qty + qty) * current_price) / total_portfolio_value < train_rank_asset_limit:
                        trading_simulator[strategy.__name__]["amount_cash"] -= qty * current_price
                    
                        if ticker in trading_simulator[strategy.__name__]["holdings"]:
                            trading_simulator[strategy.__name__]["holdings"][ticker]["quantity"] += qty
                        else:
                            trading_simulator[strategy.__name__]["holdings"][ticker] = {"quantity": qty}
                    
                        trading_simulator[strategy.__name__]["holdings"][ticker]["price"] = current_price
                        trading_simulator[strategy.__name__]["total_trades"] += 1
                        
                    elif decision == "sell" and trading_simulator[strategy.__name__]["holdings"].get(ticker, {}).get("quantity", 0) >= qty:
                        trading_simulator[strategy.__name__]["amount_cash"] += qty * current_price
                        ratio = current_price / trading_simulator[strategy.__name__]["holdings"][ticker]["price"]
                        if current_price > trading_simulator[strategy.__name__]["holdings"][ticker]["price"]:
                            trading_simulator[strategy.__name__]["successful_trades"] += 1
                            if ratio < train_profit_price_change_ratio_d1:
                                points[strategy.__name__] = points.get(strategy.__name__, 0) + time_delta * train_profit_profit_time_d1
                            elif ratio < train_profit_price_change_ratio_d2:
                                points[strategy.__name__] = points.get(strategy.__name__, 0) + time_delta * train_profit_profit_time_d2
                            else:
                                points[strategy.__name__] = points.get(strategy.__name__, 0) + time_delta * train_profit_profit_time_else
                            """
                            points[strategy.__name__] = points.get(strategy.__name__, 0) + time_delta * train_profit_profit_time_d1
                            """
                        elif current_price == trading_simulator[strategy.__name__]["holdings"][ticker]["price"]:
                            trading_simulator[strategy.__name__]["neutral_trades"] += 1
                        else:
                            trading_simulator[strategy.__name__]["failed_trades"] += 1
                            if ratio > train_loss_price_change_ratio_d1:
                                points[strategy.__name__] = points.get(strategy.__name__, 0) + -time_delta * train_loss_profit_time_d1
                            elif ratio > train_loss_price_change_ratio_d2:
                                points[strategy.__name__] = points.get(strategy.__name__, 0) + -time_delta * train_loss_profit_time_d2
                            else:
                                points[strategy.__name__] = points.get(strategy.__name__, 0) + -time_delta * train_loss_profit_time_else

                        trading_simulator[strategy.__name__]["holdings"][ticker]["quantity"] -= qty
                        if trading_simulator[strategy.__name__]["holdings"][ticker]["quantity"] == 0:
                            del trading_simulator[strategy.__name__]["holdings"][ticker]
                        elif trading_simulator[strategy.__name__]["holdings"][ticker]["quantity"] < 0:
                            Exception("Quantity cannot be negative")
                        trading_simulator[strategy.__name__]["total_trades"] += 1
        active_count = local_update_portfolio_values(current_date, strategies, trading_simulator, ticker_price_history) 
        # """
        # log history of trading_simulator and points
        # """
        # logging.info(f"Trading simulator: {trading_simulator}")
        # logging.info(f"Points: {points}")
        # logging.info(f"Date: {current_date.strftime('%Y-%m-%d')}")
        # logging.info(f"time_delta: {time_delta}")
        # logging.info(f"Active count: {active_count}")
        # logging.info("-------------------------------------------------")
        
        """
        Update time_delta based on the mode
        """
        if train_time_delta_mode == 'additive':
            time_delta += train_time_delta_increment
        elif train_time_delta_mode == 'multiplicative':
            time_delta *= train_time_delta_multiplicative
        elif train_time_delta_mode == 'balanced':
            time_delta += train_time_delta_balanced * time_delta
        """
        simulate closing actions for both 
        - updating total portfolio value of account
        - update portfolio_value of each strategies
        - update ranks
        """
        # Calculate total portfolio value including cash, long and short positions
        total_value = account["cash"]
        
        # Add value of long positions
        for ticker in account["holdings"]:
            daily_data = ticker_price_history[ticker].loc[current_date.strftime('%Y-%m-%d')]
            current_price = daily_data['Close']
            total_value += account["holdings"][ticker]["quantity"] * current_price
        
        # For short positions, unrealized profit/loss affects total value
        for ticker in account.get("short_positions", {}):
            if current_date.strftime('%Y-%m-%d') in ticker_price_history[ticker].index:
                daily_data = ticker_price_history[ticker].loc[current_date.strftime('%Y-%m-%d')]
                current_price = daily_data['Close']
                entry_price = account["short_positions"][ticker]["price"]
                quantity = account["short_positions"][ticker]["quantity"]
                
                # For shorts, profit is made when price decreases
                unrealized_pnl = (entry_price - current_price) * quantity
                total_value += unrealized_pnl
        
        account["total_portfolio_value"] = total_value

        active_count, trading_simulator = local_update_portfolio_values(current_date, strategies, trading_simulator, ticker_price_history)
        
        rank = update_ranks()

        try:
            total_value = sum([holding["quantity"] * ticker_price_history[ticker].loc[current_date.strftime('%Y-%m-%d')]['Close'] for ticker, holding in trading_simulator[strategy.__name__]["holdings"].items()]) + trading_simulator[strategy.__name__]["amount_cash"]
            account_values[current_date] = total_value 
        except KeyError:
            # Get the last available account value (if any exists)
            previous_dates = [date for date in account_values.keys() if date < current_date]
            if previous_dates:
                last_available_date = max(previous_dates)
                account_values[current_date] = account_values[last_available_date]  # Carry forward
            else:
                # Default to cash if no prior data exists (e.g., first day)
                account_values[current_date] = trading_simulator[strategy.__name__]["amount_cash"]

        logging.info(f"Date: {current_date.strftime('%Y-%m-%d')}")
        logging.info(f"Total portfolio value: {account['total_portfolio_value']}")
        logging.info("-------------------------------------------------")

        current_date += timedelta(days=1)
    
    """
    Calculate metrics and generate tear sheet
    """
    metrics = calculate_metrics(account_values)
    print(metrics)
    generate_tear_sheet(account_values, metrics)

    """
    print some stats
    """
    console_logger.info("🏁 Testing Completed")
    console_logger.info("=" * 50)
    console_logger.info(f"💰 Account Cash: ${account['cash']:,.2f}")
    console_logger.info(f"🔢 Total Trades: {len(account['trades'])}")
    
    # Count trade types
    buy_count = sum(1 for trade in account['trades'] if trade['action'] == 'buy')
    sell_count = sum(1 for trade in account['trades'] if trade['action'] == 'sell')
    short_count = sum(1 for trade in account['trades'] if trade['action'] == 'short')
    cover_count = sum(1 for trade in account['trades'] if trade['action'] == 'cover')
    console_logger.info(f"📊 Trade Summary: {buy_count} buys, {sell_count} sells, {short_count} shorts, {cover_count} covers")
    
    console_logger.info(f"📈 Current Long Positions: {len(account['holdings'])} holdings")
    console_logger.info(f"📉 Current Short Positions: {len(account.get('short_positions', {}))} shorts")
    console_logger.info(f"💵 Total Portfolio Value: ${account['total_portfolio_value']:,.2f}")
    
    # Calculate performance vs starting cash
    perf_pct = ((account['total_portfolio_value'] - train_start_cash) / train_start_cash) * 100
    console_logger.info(f"📈 Performance: {perf_pct:+.2f}%")
    
    console_logger.info("=" * 50)


if __name__ == "__main__":
    if mode == 'train':
        train()
    elif mode == 'push':
        push()
    elif mode == 'test':
        test()

