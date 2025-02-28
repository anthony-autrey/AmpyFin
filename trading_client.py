from config_variables import FINANCIAL_PREP_API_KEY, API_KEY, API_SECRET, BASE_URL, MONGO_URL
import json
from urllib.request import urlopen
from zoneinfo import ZoneInfo
import time
from datetime import datetime, timedelta
from helper_files.client_helper import place_order, get_ndaq_tickers, market_status, strategies, get_latest_price, get_mongo_client
from control import enable_short_selling, max_short_ratio, short_liquidity_buffer
import os
from datetime import date
from alpaca.trading.client import TradingClient
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from strategies.archived_strategies.trading_strategies_v1 import get_historical_data
import yfinance as yf
import logging
from collections import Counter
from statistics import median, mode
import statistics
import heapq
import requests
from strategies.talib_indicators import *
import threading
import sys
import argparse


from control import trade_liquidity_limit, trade_asset_limit, suggestion_heap_limit

buy_heap = []
suggestion_heap = []
sold = False

# Set up logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler('system.log'),  # Log messages to a file
        logging.StreamHandler()             # Log messages to the console
    ]
)

# Custom logger setup for more controlled console output
console_logger = logging.getLogger('console')
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter('%(message)s')  # Simplified format for console
console_handler.setFormatter(console_formatter)
console_logger.addHandler(console_handler)
console_logger.propagate = False  # Prevent double logging

def log_portfolio_performance(trading_client, mongo_client):
    """
    Logs the daily performance of our portfolio compared to major indices.
    Compares with SPY, QQQ, VONG, SCHG, and IWY.
    
    Args:
        trading_client: Alpaca trading client
        mongo_client: MongoDB client
    """
    try:
        # Get current account info
        account = trading_client.get_account()
        portfolio_value = float(account.portfolio_value)
        
        # Get latest prices for benchmark ETFs
        indices = {
            "SPY": get_latest_price("SPY"),   # S&P 500
            "QQQ": get_latest_price("QQQ"),   # Nasdaq 100
            "VONG": get_latest_price("VONG"), # Russell 1000 Growth
            "SCHG": get_latest_price("SCHG"), # Schwab Large-Cap Growth
            "IWY": get_latest_price("IWY")    # iShares Russell Top 200 Growth
        }
        
        # Retrieve performance data from MongoDB
        db = mongo_client.trades
        performance_collection = db.performance_tracking
        
        # Get the most recent performance record
        today = date.today().isoformat()
        performance_record = performance_collection.find_one({"type": "daily_performance", "date": today})
        
        if not performance_record:
            # If no record exists for today, get the baseline from the last performance record
            last_record = performance_collection.find_one(
                {"type": "daily_performance"}, 
                sort=[("date", -1)]
            )
            
            if last_record:
                baseline = {
                    "portfolio": last_record.get("portfolio_value", 50000.00),
                    "indices": last_record.get("indices", {
                        "SPY": 591.95,    # Default values in case no history exists
                        "QQQ": 518.58,
                        "VONG": 380.00,
                        "SCHG": 92.00,
                        "IWY": 132.00
                    })
                }
            else:
                # Default baseline if no previous records - use environment variables
                baseline = {
                    "portfolio": float(os.getenv("BASELINE_PORTFOLIO_VALUE", 50000.00)),
                    "indices": {
                        "SPY": float(os.getenv("BASELINE_SPY", 591.95)),
                        "QQQ": float(os.getenv("BASELINE_QQQ", 518.58)),
                        "VONG": float(os.getenv("BASELINE_VONG", 380.00)),
                        "SCHG": float(os.getenv("BASELINE_SCHG", 92.00)),
                        "IWY": float(os.getenv("BASELINE_IWY", 132.00))
                    }
                }
                
            # Create new performance record
            performance_collection.insert_one({
                "type": "daily_performance",
                "date": today,
                "portfolio_value": portfolio_value,
                "indices": indices,
                "baseline": baseline
            })
        else:
            # Use today's existing record
            baseline = performance_record.get("baseline")
        
        # Calculate performance percentages
        portfolio_change = ((portfolio_value - baseline["portfolio"]) / baseline["portfolio"]) * 100
        
        index_changes = {}
        for index, price in indices.items():
            baseline_price = baseline["indices"].get(index, price)  # Fallback to current price if baseline missing
            change = ((price - baseline_price) / baseline_price) * 100
            index_changes[index] = change
        
        # Determine relative performance
        relative_performance = {}
        for index, change in index_changes.items():
            relative = portfolio_change - change
            relative_performance[index] = relative
        
        # Find best and worst relative performances
        best_index = max(relative_performance.items(), key=lambda x: x[1])
        worst_index = min(relative_performance.items(), key=lambda x: x[1])
        
        # Determine overall performance status
        if portfolio_change > 0:
            if all(portfolio_change > change for change in index_changes.values()):
                status = "🔥 OUTPERFORMING ALL INDICES"
            elif any(portfolio_change > change for change in index_changes.values()):
                status = "✅ MIXED PERFORMANCE"
            else:
                status = "⚠️ UNDERPERFORMING"
        else:
            if all(portfolio_change > change for change in index_changes.values()):
                status = "✅ OUTPERFORMING (SMALLER LOSSES)"
            else:
                status = "⚠️ UNDERPERFORMING"
                
        # Log the performance
        console_logger.info("\n" + "=" * 50)
        console_logger.info(f"📈 DAILY PERFORMANCE SUMMARY - {today}")
        console_logger.info("=" * 50)
        console_logger.info(f"Portfolio: ${portfolio_value:.2f} ({portfolio_change:+.2f}%)")
        
        # Log index comparisons
        console_logger.info("\nIndex Comparisons:")
        for index, change in index_changes.items():
            relative = relative_performance[index]
            marker = "🟢" if relative > 0 else "🔴"
            console_logger.info(f"{marker} {index}: {change:+.2f}% (Relative: {relative:+.2f}%)")
        
        # Log overall status
        console_logger.info("\nPerformance Status:")
        console_logger.info(f"{status}")
        
        # Best and Worst
        console_logger.info(f"\nBest vs: {best_index[0]} (+{best_index[1]:.2f}%)")
        console_logger.info(f"Worst vs: {worst_index[0]} ({worst_index[1]:+.2f}%)")
        
        # Add YTD performance if available
        try:
            # Calculate YTD performance
            ytd_collection = db.ytd_performance
            
            # Get first trading day record or create it if not found
            current_year = date.today().year
            first_day_record = ytd_collection.find_one({"year": current_year})
            
            if not first_day_record:
                # If this is the first execution of the year, create baseline
                ytd_collection.insert_one({
                    "year": current_year,
                    "portfolio_value": portfolio_value,
                    "indices": indices
                })
                ytd_change = 0.0
                ytd_indices = {index: 0.0 for index in indices}
            else:
                # Calculate YTD performance
                ytd_portfolio_start = first_day_record.get("portfolio_value")
                ytd_indices_start = first_day_record.get("indices")
                
                ytd_change = ((portfolio_value - ytd_portfolio_start) / ytd_portfolio_start) * 100
                ytd_indices = {}
                for index, price in indices.items():
                    start_price = ytd_indices_start.get(index, price)
                    ytd_indices[index] = ((price - start_price) / start_price) * 100
            
            # Display YTD performance
            console_logger.info("\n" + "-" * 30)
            console_logger.info(f"📆 YEAR-TO-DATE PERFORMANCE")
            console_logger.info(f"Portfolio YTD: {ytd_change:+.2f}%")
            
            for index, change in ytd_indices.items():
                relative = ytd_change - change
                marker = "🟢" if relative > 0 else "🔴"
                console_logger.info(f"{marker} {index} YTD: {change:+.2f}% (Rel: {relative:+.2f}%)")
            
        except Exception as ytd_error:
            logging.error(f"Error calculating YTD performance: {ytd_error}")
        
        console_logger.info("=" * 50)
        
        # Log to the regular log file as well
        logging.info(f"Daily performance: Portfolio: {portfolio_change:+.2f}%, " +
                    f"SPY: {index_changes['SPY']:+.2f}%, QQQ: {index_changes['QQQ']:+.2f}%, " +
                    f"VONG: {index_changes['VONG']:+.2f}%")
                    
    except Exception as e:
        console_logger.error(f"❌ Error logging performance data: {str(e)}")
        logging.error(f"Error in performance logging: {e}")

def weighted_majority_decision_and_median_quantity(decisions_and_quantities):  
    """  
    Determines the majority decision (buy, sell, hold, or short) and returns the weighted median quantity for the chosen action.  
    Groups 'strong buy' with 'buy' and distinguishes between 'sell' and 'short'.
    Applies weights to quantities based on strategy coefficients.  
    """  
    buy_decisions = ['buy', 'strong buy']  
    sell_decisions = ['sell']
    short_decisions = ['short']

    weighted_buy_quantities = []
    weighted_sell_quantities = []
    weighted_short_quantities = []
    buy_weight = 0
    sell_weight = 0
    short_weight = 0
    hold_weight = 0
    
    # Process decisions with weights
    for decision, quantity, weight in decisions_and_quantities:
        if decision in buy_decisions:
            weighted_buy_quantities.extend([quantity])
            buy_weight += weight
        elif decision in sell_decisions:
            weighted_sell_quantities.extend([quantity])
            sell_weight += weight
        elif decision in short_decisions:
            weighted_short_quantities.extend([quantity])
            short_weight += weight
        elif decision == 'hold':
            hold_weight += weight
    
    # Determine the majority decision based on the highest accumulated weight
    if buy_weight > sell_weight and buy_weight > short_weight and buy_weight > hold_weight:
        return 'buy', median(weighted_buy_quantities) if weighted_buy_quantities else 0, buy_weight, sell_weight, hold_weight, short_weight
    elif sell_weight > buy_weight and sell_weight > short_weight and sell_weight > hold_weight:
        return 'sell', median(weighted_sell_quantities) if weighted_sell_quantities else 0, buy_weight, sell_weight, hold_weight, short_weight
    elif short_weight > buy_weight and short_weight > sell_weight and short_weight > hold_weight and enable_short_selling:
        return 'short', median(weighted_short_quantities) if weighted_short_quantities else 0, buy_weight, sell_weight, hold_weight, short_weight
    else:
        return 'hold', 0, buy_weight, sell_weight, hold_weight, short_weight

def process_ticker(ticker, trading_client, data_client, mongo_client, strategy_to_coefficient):
    global buy_heap
    global suggestion_heap
    global sold
    if sold is True:
        logging.debug(f"Sold flag is True. Skipping {ticker}.")
    else:
        try:
            decisions_and_quantities = []
            current_price = None
            
            while current_price is None:
                try:
                    current_price = get_latest_price(ticker)
                except Exception as fetch_error:
                    logging.warning(f"Error fetching price for {ticker}. Retrying... {fetch_error}")
                    break
            if current_price is None:
                return
            logging.debug(f"Current price of {ticker}: {current_price}")

            asset_collection = mongo_client.trades.assets_quantities
            limits_collection = mongo_client.trades.assets_limit
            account = trading_client.get_account()
            buying_power = float(account.regt_buying_power)
            portfolio_value = float(account.portfolio_value)

            asset_info = asset_collection.find_one({'symbol': ticker})
            portfolio_qty = asset_info['quantity'] if asset_info else 0.0
            logging.debug(f"Portfolio quantity for {ticker}: {portfolio_qty}")

            # Check for long position stop-loss/take-profit
            limit_info = limits_collection.find_one({'symbol': ticker, 'is_short': False})
            if limit_info and portfolio_qty > 0:
                stop_loss_price = limit_info['stop_loss_price']
                take_profit_price = limit_info['take_profit_price']
                if current_price <= stop_loss_price or current_price >= take_profit_price:
                    sold = True
                    condition = "stop-loss" if current_price <= stop_loss_price else "take-profit"
                    console_logger.info(f"🔴 SELL {ticker}: {portfolio_qty} shares @ ${current_price:.2f} ({condition})")
                    quantity = portfolio_qty
                    order = place_order(trading_client, symbol=ticker, side=OrderSide.SELL, quantity=quantity, mongo_client=mongo_client)
                    if order:
                        console_logger.info(f"✅ Order executed: {ticker} SELL {quantity} @ ${current_price:.2f}")
                        logging.info(f"Executed SELL order for {ticker}: {order}")
                        return
                    else:
                        console_logger.error(f"❌ Order failed: {ticker} SELL {quantity}")
                        logging.error(f"Failed to execute SELL order for {ticker} due to {condition} condition")
                        sold = False  # Reset sold flag to allow other sells
            
            # Check for short position stop-loss/take-profit
            shorts_collection = mongo_client.trades.short_positions
            short_position = shorts_collection.find_one({'symbol': ticker})
            short_limit_info = limits_collection.find_one({'symbol': ticker, 'is_short': True})
            
            if short_position and short_limit_info and enable_short_selling:
                short_qty = short_position['quantity']
                stop_loss_price = short_limit_info['stop_loss_price'] 
                take_profit_price = short_limit_info['take_profit_price']
                
                # For short positions, stop loss is when price increases, take profit is when price decreases
                if current_price >= stop_loss_price or current_price <= take_profit_price:
                    condition = "stop-loss" if current_price >= stop_loss_price else "take-profit"
                    console_logger.info(f"🟢 COVER {ticker}: {short_qty} shares @ ${current_price:.2f} ({condition})")
                    order = place_order(trading_client, symbol=ticker, side=OrderSide.BUY, quantity=short_qty, mongo_client=mongo_client, is_short=True)
                    if order:
                        console_logger.info(f"✅ Order executed: {ticker} COVER {short_qty} @ ${current_price:.2f}")
                        logging.info(f"Executed BUY to cover short position for {ticker}: {order}")
                        return
                    else:
                        console_logger.error(f"❌ Order failed: {ticker} COVER {short_qty}")
                        logging.error(f"Failed to execute BUY to cover short position for {ticker} due to {condition} condition")
                        # No need to reset sold flag here as it's a buy operation

            indicator_tb = mongo_client.IndicatorsDatabase
            indicator_collection = indicator_tb.Indicators

            for strategy in strategies:
                historical_data = None
                while historical_data is None:
                    try:
                        period = indicator_collection.find_one({'indicator': strategy.__name__})
                        historical_data = get_data(ticker, mongo_client, period['ideal_period'])
                    except Exception as fetch_error:
                        logging.warning(f"Error fetching historical data for {ticker}. Retrying... {fetch_error}")
                        time.sleep(60)

                decision, quantity = simulate_strategy(strategy, ticker, current_price, historical_data, buying_power, portfolio_qty, portfolio_value)
                logging.debug(f"Strategy: {strategy.__name__}, Decision: {decision}, Quantity: {quantity} for {ticker}")
                weight = strategy_to_coefficient[strategy.__name__]
                decisions_and_quantities.append((decision, quantity, weight))

            decision, quantity, buy_weight, sell_weight, hold_weight, short_weight = weighted_majority_decision_and_median_quantity(decisions_and_quantities)
            console_logger.info(f"📊 {ticker}: {decision.upper()} {quantity} @ ${current_price:.2f} [B:{buy_weight:.1f} S:{sell_weight:.1f} SH:{short_weight:.1f} H:{hold_weight:.1f}]")

            # Get info about short positions
            shorts_collection = mongo_client.trades.short_positions
            short_position = shorts_collection.find_one({'symbol': ticker})
            short_qty = short_position['quantity'] if short_position else 0.0

            if decision == "buy" and float(account.regt_buying_power) > trade_liquidity_limit and (((quantity + portfolio_qty) * current_price) / portfolio_value) < trade_asset_limit:
                # Buy regular positions - same as before
                heapq.heappush(buy_heap, (-(buy_weight-(sell_weight + short_weight + (hold_weight * 0.5))), quantity, ticker))
                logging.debug(f"Added {ticker} to buy heap with priority {-(buy_weight-(sell_weight + short_weight + (hold_weight * 0.5))):.2f}")
            elif decision == "sell" and portfolio_qty > 0:
                # Sell long positions - same as before
                console_logger.info(f"🔴 SELL {ticker}: {quantity} shares @ ${current_price:.2f}")
                sold = True
                quantity = max(quantity, 1)
                order = place_order(trading_client, symbol=ticker, side=OrderSide.SELL, quantity=quantity, mongo_client=mongo_client)
                if order:
                    console_logger.info(f"✅ Order executed: {ticker} SELL {quantity} @ ${current_price:.2f}")
                    logging.info(f"Executed SELL order for {ticker}: {order}")
                else:
                    console_logger.error(f"❌ Order failed: {ticker} SELL {quantity}")
                    logging.error(f"Failed to execute SELL order for {ticker}")
                    sold = False  # Reset sold flag to allow other sells
            elif decision == "short" and enable_short_selling and short_qty == 0:
                # Short selling
                console_logger.info(f"🔵 SHORT {ticker}: {quantity} shares @ ${current_price:.2f}")
                sold = True
                quantity = max(quantity, 1)
                order = place_order(trading_client, symbol=ticker, side=OrderSide.SELL, quantity=quantity, mongo_client=mongo_client, is_short=True)
                if order:
                    console_logger.info(f"✅ Order executed: {ticker} SHORT {quantity} @ ${current_price:.2f}")
                    logging.info(f"Executed SHORT order for {ticker}: {order}")
                else:
                    console_logger.error(f"❌ Order failed: {ticker} SHORT {quantity}")
                    logging.error(f"Failed to execute SHORT order for {ticker}")
                    sold = False  # Reset sold flag to allow other sells
            elif decision == "buy" and short_qty > 0:
                # Buy to cover short positions
                console_logger.info(f"🟢 COVER {ticker}: {short_qty} shares @ ${current_price:.2f}")
                cover_qty = min(quantity, short_qty)
                order = place_order(trading_client, symbol=ticker, side=OrderSide.BUY, quantity=cover_qty, mongo_client=mongo_client, is_short=True)
                if order:
                    console_logger.info(f"✅ Order executed: {ticker} COVER {cover_qty} @ ${current_price:.2f}")
                    logging.info(f"Executed BUY to cover short position for {ticker}: {order}")
                else:
                    console_logger.error(f"❌ Order failed: {ticker} COVER {cover_qty}")
                    logging.error(f"Failed to execute BUY to cover short position for {ticker}")
            elif portfolio_qty == 0.0 and short_qty == 0.0 and buy_weight > (sell_weight + short_weight) and (((quantity + portfolio_qty) * current_price) / portfolio_value) < trade_asset_limit and float(account.regt_buying_power) > trade_liquidity_limit:
                # Suggestion heap for buying - same logic as before but with added short_weight consideration
                max_investment = portfolio_value * trade_asset_limit
                buy_quantity = min(int(max_investment // current_price), int(buying_power // current_price))
                if buy_weight > suggestion_heap_limit:
                    buy_quantity = max(buy_quantity, 2)
                    buy_quantity = buy_quantity // 2
                    logging.debug(f"Adding {ticker} to suggestion heap with weight {buy_weight:.2f} and quantity {buy_quantity}")
                    heapq.heappush(suggestion_heap, (-(buy_weight - (sell_weight + short_weight)), buy_quantity, ticker))
                else:
                    logging.debug(f"Holding for {ticker}, weight {buy_weight:.2f} below threshold {suggestion_heap_limit}")
            else:
                logging.debug(f"Holding for {ticker}, no action taken")
        
        except Exception as e:
            logging.error(f"Error processing {ticker}: {e}")

def main():
    """
    Main function to control the workflow based on the market's status.
    """
    
    console_logger.info("🚀 AmpyThropic Trading System Starting")
    logging.info("Trading mode is live.")
    global buy_heap
    global suggestion_heap
    global sold
    ndaq_tickers = []
    early_hour_first_iteration = True
    post_hour_first_iteration = True
    trading_client = TradingClient(API_KEY, API_SECRET)
    data_client = StockHistoricalDataClient(API_KEY, API_SECRET)
    mongo_client = get_mongo_client(MONGO_URL)
    db = mongo_client.trades
    asset_collection = db.assets_quantities
    limits_collection = db.assets_limit
    strategy_to_coefficient = {}
    sold = False
    
    # Print short selling status
    if enable_short_selling:
        console_logger.info(f"📢 Short selling is ENABLED (max ratio: {max_short_ratio:.2f}, buffer: {short_liquidity_buffer:.2f})")
    
    while True:
        trading_client = TradingClient(API_KEY, API_SECRET)
        data_client = StockHistoricalDataClient(API_KEY, API_SECRET)
        status = market_status(trading_client)  # Use the helper function for market status
        db = mongo_client.trades
        asset_collection = db.assets_quantities
        limits_collection = db.assets_limit
        market_db = mongo_client.market_data
        market_collection = market_db.market_status
        indicator_tb = mongo_client.IndicatorsDatabase
        indicator_collection = indicator_tb.Indicators
        
        market_collection.update_one({}, {"$set": {"market_status": status}})
        
        if status == "open":
            if not ndaq_tickers:
                console_logger.info("🟢 Market is OPEN - Starting trading operations")
                logging.info("Market is open")
                ndaq_tickers = get_ndaq_tickers(mongo_client, FINANCIAL_PREP_API_KEY)
                
                # Load strategy coefficients
                console_logger.info("📊 Loading strategy coefficients...")
                sim_db = mongo_client.trading_simulator
                rank_collection = sim_db.rank
                r_t_c_collection = sim_db.rank_to_coefficient
                strategy_count = 0
                
                for strategy in strategies:
                    strategy_count += 1
                    rank = rank_collection.find_one({'strategy': strategy.__name__})['rank']
                    coefficient = r_t_c_collection.find_one({'rank': rank})['coefficient']
                    strategy_to_coefficient[strategy.__name__] = coefficient
                
                console_logger.info(f"✅ Loaded {strategy_count} strategies with coefficients")
                early_hour_first_iteration = False
                post_hour_first_iteration = True
            trading_client = TradingClient(API_KEY, API_SECRET)
            account = trading_client.get_account()
            buying_power = float(account.regt_buying_power)
            portfolio_value = float(account.portfolio_value)
            qqq_latest = get_latest_price('QQQ')
            spy_latest = get_latest_price('SPY')
            buy_heap = []
            suggestion_heap = []

            trades_db = mongo_client.trades
            portfolio_collection = trades_db.portfolio_values

            # Update performance tracking metrics
            portfolio_collection.update_one({"name" : "portfolio_percentage"}, {"$set": {"portfolio_value": (portfolio_value-50491.13)/50491.13}})
            portfolio_collection.update_one({"name" : "ndaq_percentage"}, {"$set": {"portfolio_value": (qqq_latest-518.58)/518.58}})
            portfolio_collection.update_one({"name" : "spy_percentage"}, {"$set": {"portfolio_value": (spy_latest-591.95)/591.95}})

            console_logger.info(f"📊 Portfolio: ${portfolio_value:.2f} | Buying Power: ${float(account.regt_buying_power):.2f}")
            console_logger.info(f"🔍 Scanning {len(ndaq_tickers)} NASDAQ tickers...")
            
            threads = []

            for ticker in ndaq_tickers:
                thread = threading.Thread(target=process_ticker, args=(ticker, trading_client, data_client, mongo_client, strategy_to_coefficient))
                threads.append(thread)
                thread.start()

            # Wait for all threads to complete
            for thread in threads:
                thread.join()

            # Process buy orders from heaps
            trading_client = TradingClient(API_KEY, API_SECRET)
            account = trading_client.get_account()
            
            if buy_heap:
                console_logger.info(f"📋 Processing {len(buy_heap)} buy candidates...")
            elif suggestion_heap:
                console_logger.info(f"📋 Processing {len(suggestion_heap)} suggestion candidates...")
                
            while (buy_heap or suggestion_heap) and float(account.regt_buying_power) > trade_liquidity_limit and sold is False:
                try:
                    trading_client = TradingClient(API_KEY, API_SECRET)
                    account = trading_client.get_account()
                    buying_power = float(account.regt_buying_power)
                    logging.debug(f"Current buying power: ${buying_power:.2f}")
                    
                    if buy_heap and buying_power > trade_liquidity_limit:
                        _, quantity, ticker = heapq.heappop(buy_heap)
                        console_logger.info(f"🟢 BUY {ticker}: {quantity} shares @ ${get_latest_price(ticker):.2f}")
                        
                        order = place_order(trading_client, symbol=ticker, side=OrderSide.BUY, quantity=quantity, mongo_client=mongo_client)
                        if order:
                            console_logger.info(f"✅ Order executed: {ticker} BUY {quantity} @ ${get_latest_price(ticker):.2f}")
                            logging.info(f"Executed BUY order for {ticker}: {order}")
                        else:
                            console_logger.error(f"❌ Order failed: {ticker} BUY {quantity}")
                            logging.warning(f"Skipped BUY order for {ticker} due to margin safety checks")
                        
                    elif suggestion_heap and buying_power > trade_liquidity_limit:
                        _, quantity, ticker = heapq.heappop(suggestion_heap)
                        console_logger.info(f"🟡 SUGGEST BUY {ticker}: {quantity} shares @ ${get_latest_price(ticker):.2f}")
                        
                        order = place_order(trading_client, symbol=ticker, side=OrderSide.BUY, quantity=quantity, mongo_client=mongo_client)
                        if order:
                            console_logger.info(f"✅ Order executed: {ticker} BUY {quantity} @ ${get_latest_price(ticker):.2f}")
                            logging.info(f"Executed BUY order from suggestion heap for {ticker}: {order}")
                        else:
                            console_logger.error(f"❌ Order failed: {ticker} BUY {quantity}")
                            logging.warning(f"Skipped BUY order for {ticker} due to margin safety checks")
                        
                    time.sleep(5)
                    """
                    This is here so order will propage through and we will have an accurate cash balance recorded
                    """
                except Exception as e:
                    console_logger.error(f"❌ Error occurred while executing buy order: {str(e)}")
                    logging.error(f"Error executing buy order: {e}")
                    break
            
            # Reset state for next cycle
            buy_heap = []
            suggestion_heap = []
            sold = False
            console_logger.info("⏱️ Sleeping for 30 seconds before next scan...")
            time.sleep(30)

        elif status == "early_hours":
            if early_hour_first_iteration:
                console_logger.info("🟡 Market is in EARLY HOURS (pre-market)")
                
                # Load tickers and strategy coefficients
                ndaq_tickers = get_ndaq_tickers(mongo_client, FINANCIAL_PREP_API_KEY)
                console_logger.info("📊 Loading strategy coefficients...")
                
                sim_db = mongo_client.trading_simulator
                rank_collection = sim_db.rank
                r_t_c_collection = sim_db.rank_to_coefficient
                strategy_count = 0
                
                for strategy in strategies:
                    strategy_count += 1
                    rank = rank_collection.find_one({'strategy': strategy.__name__})['rank']
                    coefficient = r_t_c_collection.find_one({'rank': rank})['coefficient']
                    strategy_to_coefficient[strategy.__name__] = coefficient
                
                console_logger.info(f"✅ Loaded {strategy_count} strategies with coefficients")
                early_hour_first_iteration = False
                post_hour_first_iteration = True
                logging.info("Market is in early hours. Waiting for 30 seconds.")
            
            console_logger.info("⏱️ Waiting for market to open...")
            time.sleep(30)

        elif status == "closed":
            if post_hour_first_iteration:
                console_logger.info("🔴 Market is CLOSED")
                
                # Log daily performance summary at market close
                console_logger.info("📊 Generating daily performance report...")
                log_portfolio_performance(trading_client, mongo_client)
                
                early_hour_first_iteration = True
                post_hour_first_iteration = False
                logging.info("Market is closed. Performing post-market operations.")
            
            console_logger.info("⏱️ Waiting for next market session...")
            time.sleep(30)
        else:
            console_logger.error("❌ Error determining market status")
            logging.error("An error occurred while checking market status.")
            time.sleep(60)
    

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='AmpyThropic Trading System')
    parser.add_argument('--report', action='store_true', help='Generate performance report without running the trading system')
    args = parser.parse_args()
    
    if args.report:
        # Just generate performance report and exit
        console_logger.info("🚀 AmpyThropic Trading System - Performance Report Mode")
        trading_client = TradingClient(API_KEY, API_SECRET)
        mongo_client = get_mongo_client(MONGO_URL)
        log_portfolio_performance(trading_client, mongo_client)
    else:
        # Run the normal trading system
        main()

    