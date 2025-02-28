from config_variables import FINANCIAL_PREP_API_KEY, API_KEY, API_SECRET, BASE_URL, MONGO_URL, BASELINE_PORTFOLIO_VALUE, BASELINE_SPY, BASELINE_QQQ, BASELINE_VONG, BASELINE_SCHG, BASELINE_IWY
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
from utils.alerting import send_critical_alert, send_error_alert, send_warning_alert, send_info_alert


from control import trade_liquidity_limit, trade_asset_limit, pragmatic_buying_power_factor, pragmatic_over_hold_factor

buy_heap = []
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

# Setup exception tracking
class ExceptionStats:
    """Class to track exception frequency and patterns"""
    def __init__(self):
        self.exceptions = {}  # Maps exception types to counts
        self.consecutive_errors = {}  # Maps exception types to consecutive occurrence counts
        self.error_timestamps = {}  # Maps exception types to most recent timestamp
        self.total_errors = 0
        self.critical_error_threshold = 5  # Number of consecutive errors before taking action
        self.error_window = 300  # Time window in seconds to track error frequency
        
    def record_exception(self, exception_type, error_message, context=None):
        """Record an exception occurrence"""
        now = time.time()
        type_name = exception_type.__name__
        
        # Update counts
        if type_name not in self.exceptions:
            self.exceptions[type_name] = 1
            self.consecutive_errors[type_name] = 1
            self.error_timestamps[type_name] = [now]
        else:
            self.exceptions[type_name] += 1
            self.consecutive_errors[type_name] += 1
            self.error_timestamps[type_name].append(now)
            
            # Clean up old timestamps
            self.error_timestamps[type_name] = [ts for ts in self.error_timestamps[type_name] 
                                              if now - ts <= self.error_window]
        
        self.total_errors += 1
        
        # Log the exception
        logging.error(f"Exception {type_name}: {error_message} | Context: {context}")
        
        # Send email alert based on severity
        if self.consecutive_errors[type_name] >= self.critical_error_threshold:
            error_detail = f"Error type: {type_name}\nMessage: {error_message}\nContext: {context}\nOccurred: {self.consecutive_errors[type_name]} times consecutively"
            logging.critical(f"CRITICAL: {type_name} errors occurring frequently ({self.consecutive_errors[type_name]} times).")
            console_logger.error(f"❌ CRITICAL ERROR: {type_name} occurring repeatedly. System may need attention.")
            
            # Send critical alert for repeated errors
            send_critical_alert(
                f"Critical Error: {type_name} (Repeated)",
                error_detail
            )
        elif self.consecutive_errors[type_name] > 1:
            # Send warning alert for consecutive errors
            error_detail = f"Error type: {type_name}\nMessage: {error_message}\nContext: {context}\nOccurred: {self.consecutive_errors[type_name]} times consecutively"
            send_warning_alert(
                f"Repeated Error: {type_name}",
                error_detail
            )
        else:
            # For first occurrence, just send an error alert
            error_detail = f"Error type: {type_name}\nMessage: {error_message}\nContext: {context}"
            send_error_alert(
                f"System Error: {type_name}",
                error_detail
            )
        
        # Return if this is a critical error situation
        return self.consecutive_errors[type_name] >= self.critical_error_threshold
        
    def reset_consecutive(self, exception_type):
        """Reset consecutive error counter for a specific exception type"""
        type_name = exception_type.__name__
        if type_name in self.consecutive_errors:
            self.consecutive_errors[type_name] = 0
            
    def get_error_frequency(self, exception_type):
        """Get frequency of errors of a specific type in the error window"""
        type_name = exception_type.__name__
        if type_name not in self.error_timestamps:
            return 0
        
        # Count errors in the time window
        now = time.time()
        recent_errors = [ts for ts in self.error_timestamps[type_name] if now - ts <= self.error_window]
        return len(recent_errors)
    
    def get_summary(self):
        """Get a summary of all recorded exceptions"""
        return {
            'total_errors': self.total_errors,
            'exception_counts': self.exceptions.copy(),
            'consecutive_errors': self.consecutive_errors.copy()
        }

# Instantiate the exception tracker
exception_tracker = ExceptionStats()

def check_system_health(trading_client, mongo_client):
    """
    Checks overall system health by verifying connectivity to critical services
    and monitoring system resources.
    
    Args:
        trading_client: Alpaca trading client
        mongo_client: MongoDB client
    
    Returns:
        dict: Health status information
    """
    health_status = {
        "timestamp": datetime.now().isoformat(),
        "status": "healthy",  # Default to healthy
        "components": {},
        "error_count": exception_tracker.total_errors,
        "warnings": []
    }
    
    # Check Alpaca API connection
    try:
        # Light API call to check connectivity
        account = trading_client.get_account()
        health_status["components"]["alpaca_api"] = {
            "status": "connected",
            "account_status": account.status,
            "last_equity": float(account.equity)
        }
    except Exception as e:
        health_status["components"]["alpaca_api"] = {
            "status": "error",
            "error": str(e)
        }
        health_status["status"] = "degraded"
        health_status["warnings"].append(f"Alpaca API connection issue: {str(e)}")
    
    # Check MongoDB connection
    try:
        # Light query to check connectivity
        mongo_client.admin.command('ping')
        dbs = mongo_client.list_database_names()
        health_status["components"]["mongodb"] = {
            "status": "connected",
            "databases": len(dbs)
        }
    except Exception as e:
        health_status["components"]["mongodb"] = {
            "status": "error",
            "error": str(e)
        }
        health_status["status"] = "degraded"
        health_status["warnings"].append(f"MongoDB connection issue: {str(e)}")
    
    # Check system resources
    try:
        import psutil
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        # Check for low resources
        if memory.percent > 90:
            health_status["status"] = "degraded"
            health_status["warnings"].append(f"High memory usage: {memory.percent}%")
        
        if disk.percent > 90:
            health_status["status"] = "degraded"
            health_status["warnings"].append(f"Low disk space: {disk.percent}% used")
        
        health_status["components"]["system"] = {
            "memory_used_percent": memory.percent,
            "disk_used_percent": disk.percent,
            "cpu_used_percent": psutil.cpu_percent(interval=0.1)
        }
    except ImportError:
        health_status["components"]["system"] = {
            "status": "unknown",
            "message": "psutil not installed"
        }
    except Exception as e:
        health_status["components"]["system"] = {
            "status": "error",
            "error": str(e)
        }
    
    # Check for recent errors
    error_summary = exception_tracker.get_summary()
    if error_summary["total_errors"] > 10:
        health_status["status"] = "degraded"
        health_status["warnings"].append(f"High error count: {error_summary['total_errors']} errors")
    
    # Log system health
    if health_status["status"] != "healthy":
        logging.warning(f"System health check: {health_status['status']}")
        for warning in health_status["warnings"]:
            logging.warning(f"Health warning: {warning}")
            
        console_logger.warning(f"⚠️ System health: {health_status['status'].upper()}")
        for warning in health_status["warnings"]:
            console_logger.warning(f"  - {warning}")
        
        # Send alert for degraded system health
        warnings_text = "\n".join([f"- {w}" for w in health_status["warnings"]])
        component_status = "\n".join([
            f"{name}: {details.get('status', 'unknown')}" 
            for name, details in health_status["components"].items()
        ])
        
        alert_message = f"""
System health status: {health_status['status'].upper()}

WARNINGS:
{warnings_text}

COMPONENT STATUS:
{component_status}

Total Error Count: {error_summary["total_errors"]}
        """
        
        # Send warning or critical alert based on severity
        if health_status["status"] == "degraded":
            send_warning_alert("System Health Degraded", alert_message)
        else:
            send_critical_alert("System Health Critical", alert_message)
    else:
        logging.info("System health check: Healthy")
    
    # Save health status to MongoDB for historical tracking
    try:
        mongo_client.system_health.status.insert_one(health_status)
    except Exception as e:
        logging.error(f"Failed to save health status: {e}")
    
    return health_status

def log_portfolio_performance(trading_client, mongo_client, send_alerts=True):
    """
    Logs the daily performance of our portfolio compared to major indices.
    Compares with SPY, QQQ, VONG, SCHG, and IWY.
    
    Args:
        trading_client: Alpaca trading client
        mongo_client: MongoDB client
        send_alerts: Whether to send alerts for significant performance changes
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
                    "portfolio": last_record.get("portfolio_value", BASELINE_PORTFOLIO_VALUE),
                    "indices": last_record.get("indices", {
                        "SPY": BASELINE_SPY,
                        "QQQ": BASELINE_QQQ,
                        "VONG": BASELINE_VONG,
                        "SCHG": BASELINE_SCHG,
                        "IWY": BASELINE_IWY
                    })
                }
            else:
                # Default baseline if no previous records - use imported variables
                baseline = {
                    "portfolio": BASELINE_PORTFOLIO_VALUE,
                    "indices": {
                        "SPY": BASELINE_SPY,
                        "QQQ": BASELINE_QQQ,
                        "VONG": BASELINE_VONG,
                        "SCHG": BASELINE_SCHG,
                        "IWY": BASELINE_IWY
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
        
        # Send performance alerts if enabled
        if send_alerts:
            # Significant underperformance alert
            if portfolio_change < -5.0 or (portfolio_change < 0 and all(portfolio_change < change for change in index_changes.values())):
                alert_message = f"""
Portfolio is significantly underperforming:
Portfolio: {portfolio_change:+.2f}%

Index Comparisons:
{', '.join([f"{idx}: {chg:+.2f}%" for idx, chg in index_changes.items()])}

Best performing index vs portfolio: {best_index[0]} ({best_index[1]:+.2f}%)
Worst performing index vs portfolio: {worst_index[0]} ({worst_index[1]:+.2f}%)
                """
                send_warning_alert("Portfolio Underperforming", alert_message)
            
            # Significant market decline alert
            elif portfolio_change < -3.0 and all(change < -2.0 for change in index_changes.values()):
                alert_message = f"""
Significant market decline detected:
Portfolio: {portfolio_change:+.2f}%

Index Declines:
{', '.join([f"{idx}: {chg:+.2f}%" for idx, chg in index_changes.items()])}
                """
                send_warning_alert("Market Decline Alert", alert_message)
            
            # Exceptional performance alert (positive)
            elif portfolio_change > 3.0 and all(portfolio_change > change for change in index_changes.values()):
                alert_message = f"""
Portfolio is significantly outperforming all indices:
Portfolio: {portfolio_change:+.2f}%

Index Comparisons:
{', '.join([f"{idx}: {chg:+.2f}%" for idx, chg in index_changes.items()])}

Best performing index vs portfolio: {best_index[0]} ({best_index[1]:+.2f}%)
                """
                send_info_alert("Portfolio Outperforming", alert_message)
        
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
    Applies weights to quantities based on strategy coefficients.  
    """  
    buy_decisions = ['buy']  
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

            # Extract buy and sell quantities from decisions for pragmatic trades
            buy_quantities = [quantity for decision, quantity, _ in decisions_and_quantities if decision == 'buy']
            short_quantities = [quantity for decision, quantity, _ in decisions_and_quantities if decision == 'short']
            
            decision, quantity, buy_weight, sell_weight, hold_weight, short_weight = weighted_majority_decision_and_median_quantity(decisions_and_quantities)
            console_logger.info(f"📊 {ticker}:\t\t{decision.upper()} {quantity} @ ${current_price:.2f}\t[B:{buy_weight:.1f} S:{sell_weight:.1f} SH:{short_weight:.1f} H:{hold_weight:.1f}]")

            # Get info about short positions
            shorts_collection = mongo_client.trades.short_positions
            short_position = shorts_collection.find_one({'symbol': ticker})
            short_qty = short_position['quantity'] if short_position else 0.0

            # Calculate quantities that might be needed for pragmatic decisions
            pragmatic_buy_quantity = median(buy_quantities) if buy_quantities else 0
            pragmatic_short_quantity = median(short_quantities) if short_quantities else 0
            
            buy_condition = decision == "buy" and float(account.regt_buying_power) > trade_liquidity_limit and (((quantity + portfolio_qty) * current_price) / portfolio_value) < trade_asset_limit
            # Check for buy condition with less restrictive requirements
            pragmatic_buy_condition = (float(account.regt_buying_power) > (trade_liquidity_limit * pragmatic_buying_power_factor) and
                buy_weight > (hold_weight * pragmatic_over_hold_factor) and
                buy_weight > sell_weight and 
                buy_weight > short_weight and
                pragmatic_buy_quantity > 0)  # Ensure we have a valid quantity

            short_condition = decision == "short" and enable_short_selling and short_qty == 0
            # Check for short condition with new less restrictive requirements
            pragmatic_short_condition = (enable_short_selling and 
                short_qty == 0 and
                float(account.regt_buying_power) > (trade_liquidity_limit * pragmatic_buying_power_factor) and
                short_weight > (hold_weight * pragmatic_over_hold_factor) and
                short_weight > buy_weight and 
                short_weight > sell_weight and
                pragmatic_short_quantity > 0)  # Ensure we have a valid quantity

            # Check if we need to cover a short position first
            if decision == "buy" and short_qty > 0:
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
            elif buy_condition or pragmatic_buy_condition:
                buy_type = "standard" if buy_condition else "pragmatic"
                # Use appropriate quantity based on condition type
                actual_quantity = quantity if buy_condition else pragmatic_buy_quantity
                heapq.heappush(buy_heap, (-(buy_weight-(sell_weight + short_weight + (hold_weight * 0.5))), actual_quantity, ticker, buy_type))
                logging.debug(f"Added {ticker} to buy heap with priority {-(buy_weight-(sell_weight + short_weight + (hold_weight * 0.5))):.2f} ({buy_type} buy)")        
            elif short_condition or pragmatic_short_condition:
                short_type = "standard" if short_condition else "pragmatic"
                # Use appropriate quantity based on condition type
                actual_quantity = quantity if short_condition else pragmatic_short_quantity
                # Short selling with asset limit check
                # Calculate portfolio impact as a percentage of total portfolio value
                short_position_value = actual_quantity * current_price
                short_position_ratio = short_position_value / portfolio_value
                
                # Check if this short would exceed our per-ticker asset limit
                if short_position_ratio > trade_asset_limit:
                    # Adjust quantity to stay within limits
                    adjusted_quantity = int((trade_asset_limit * portfolio_value) / current_price)
                    if adjusted_quantity < 1:
                        logging.info(f"Cannot short {ticker}: position would exceed asset limit {trade_asset_limit:.2f} of portfolio")
                        return
                    actual_quantity = adjusted_quantity
                    logging.info(f"Adjusted short quantity for {ticker} to {actual_quantity} to stay within asset limit")
                
                console_logger.info(f"🔵 SHORT {ticker}: {actual_quantity} shares @ ${current_price:.2f} ({short_type} short)")
                sold = True
                actual_quantity = max(actual_quantity, 1)
                order = place_order(trading_client, symbol=ticker, side=OrderSide.SELL, quantity=actual_quantity, mongo_client=mongo_client, is_short=True)
                if order:
                    console_logger.info(f"✅ Order executed: {ticker} SHORT {actual_quantity} @ ${current_price:.2f}")
                    logging.info(f"Executed SHORT order for {ticker}: {order}")
                else:
                    console_logger.error(f"❌ Order failed: {ticker} SHORT {actual_quantity}")
                    logging.error(f"Failed to execute SHORT order for {ticker}")
                    sold = False  # Reset sold flag to allow other sells
            elif decision == "sell" and portfolio_qty > 0:
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
            else:
                logging.debug(f"Holding for {ticker}, no action taken")
        
        except Exception as e:
            # Track exception to detect patterns
            is_critical = exception_tracker.record_exception(type(e), str(e), f"process_ticker({ticker})")
            logging.error(f"Error processing {ticker}: {e}")
            
            # If this is a critical/repeated error, log more details
            if is_critical:
                logging.critical(f"CRITICAL: Repeated errors processing {ticker}. Check system stability.")
                # Send summary to console
                error_summary = exception_tracker.get_summary()
                console_logger.error(f"⚠️ System stability warning: Multiple errors detected")
                console_logger.error(f"  Total errors: {error_summary['total_errors']}")
                top_errors = sorted(error_summary['exception_counts'].items(), key=lambda x: x[1], reverse=True)[:3]
                for err_type, count in top_errors:
                    console_logger.error(f"  {err_type}: {count} occurrences")

def main():
    """
    Main function to control the workflow based on the market's status.
    """
    
    console_logger.info("🚀 AmpyThropic Trading System Starting")
    logging.info("Trading mode is live.")
    global buy_heap
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
    
    # Track when we last did a health check
    last_health_check = time.time()
    health_check_interval = 3600  # 1 hour interval
    
    # Print short selling status
    if enable_short_selling:
        console_logger.info(f"📢 Short selling is ENABLED (max ratio: {max_short_ratio:.2f}, buffer: {short_liquidity_buffer:.2f})")
    
    # Run initial health check
    try:
        console_logger.info("🔍 Running initial system health check...")
        health_status = check_system_health(trading_client, mongo_client)
        if health_status["status"] != "healthy":
            console_logger.warning(f"⚠️ Initial health check: System health is {health_status['status'].upper()}")
            for warning in health_status["warnings"]:
                console_logger.warning(f"  - {warning}")
        else:
            console_logger.info("✅ Initial health check passed")
    except Exception as e:
        logging.error(f"Error in initial health check: {e}")
        console_logger.error(f"⚠️ Error in initial health check: {str(e)}")
    
    while True:
        # Check if it's time for a health check
        current_time = time.time()
        if current_time - last_health_check > health_check_interval:
            try:
                health_status = check_system_health(trading_client, mongo_client)
                last_health_check = current_time
            except Exception as e:
                logging.error(f"Error in periodic health check: {e}")
                
        # Reset error counters for successful operations
        if exception_tracker.total_errors > 0:
            for ex_type in list(exception_tracker.consecutive_errors.keys()):
                exception_tracker.consecutive_errors[ex_type] = 0
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

            trades_db = mongo_client.trades
            portfolio_collection = trades_db.portfolio_values

            # Update performance tracking metrics using baseline values
            portfolio_collection.update_one({"name" : "portfolio_percentage"}, {"$set": {"portfolio_value": (portfolio_value-BASELINE_PORTFOLIO_VALUE)/BASELINE_PORTFOLIO_VALUE}})
            portfolio_collection.update_one({"name" : "ndaq_percentage"}, {"$set": {"portfolio_value": (qqq_latest-BASELINE_QQQ)/BASELINE_QQQ}})
            portfolio_collection.update_one({"name" : "spy_percentage"}, {"$set": {"portfolio_value": (spy_latest-BASELINE_SPY)/BASELINE_SPY}})

            console_logger.info(f"📊 Portfolio: ${portfolio_value:.2f} | Buying Power: ${float(account.regt_buying_power):.2f}")
            console_logger.info(f"🔍 Processing {len(ndaq_tickers)} NASDAQ tickers...")
            
            threads = []

            for ticker in ndaq_tickers:
                thread = threading.Thread(target=process_ticker, args=(ticker, trading_client, data_client, mongo_client, strategy_to_coefficient))
                threads.append(thread)
                thread.start()

            # Wait for all threads to complete
            for thread in threads:
                thread.join()

            # Process buy orders from heap
            trading_client = TradingClient(API_KEY, API_SECRET)
            account = trading_client.get_account()
            
            if buy_heap:
                console_logger.info(f"📋 Processing {len(buy_heap)} buy candidates...")
                
            # We'll check the buying power threshold dynamically based on the buy_type in the loop
            while buy_heap and sold is False:
                try:
                    trading_client = TradingClient(API_KEY, API_SECRET)
                    account = trading_client.get_account()
                    buying_power = float(account.regt_buying_power)
                    logging.debug(f"Current buying power: ${buying_power:.2f}")
                    
                    # Make sure the heap isn't empty
                    if not buy_heap:
                        break
                        
                    # Peek at the top item first to check if we have enough buying power
                    heap_item = buy_heap[0]
                    if len(heap_item) == 4:  # New format with buy_type
                        _, _, _, buy_type = heap_item
                    else:
                        buy_type = "standard"
                    
                    # Determine the appropriate buying power threshold based on the buy_type
                    required_buying_power = (trade_liquidity_limit * pragmatic_buying_power_factor 
                                           if buy_type == "pragmatic" else trade_liquidity_limit)
                    
                    # Check if we have enough buying power
                    if buying_power <= required_buying_power:
                        logging.info(f"Insufficient buying power (${buying_power:.2f}) for {buy_type} buy threshold (${required_buying_power:.2f}). Stopping buy processing.")
                        break
                    
                    # If we have enough buying power, pop the item and proceed
                    heap_item = heapq.heappop(buy_heap)
                    if len(heap_item) == 4:  # New format with buy_type
                        _, quantity, ticker, buy_type = heap_item
                        console_logger.info(f"🟢 BUY {ticker}: {quantity} shares @ ${get_latest_price(ticker):.2f} ({buy_type} buy)")
                    else:  # Old format without buy_type (for backward compatibility)
                        _, quantity, ticker = heap_item
                        buy_type = "standard"
                        console_logger.info(f"🟢 BUY {ticker}: {quantity} shares @ ${get_latest_price(ticker):.2f}")
                    
                    order = place_order(trading_client, symbol=ticker, side=OrderSide.BUY, quantity=quantity, mongo_client=mongo_client)
                    if order:
                        console_logger.info(f"✅ Order executed: {ticker} BUY {quantity} @ ${get_latest_price(ticker):.2f}")
                        logging.info(f"Executed BUY order for {ticker} ({buy_type}): {order}")
                    else:
                        console_logger.error(f"❌ Order failed: {ticker} BUY {quantity}")
                        
                    time.sleep(5)
                    """
                    This is here so order will propage through and we will have an accurate cash balance recorded
                    """
                except Exception as e:
                    # Track exception to detect patterns
                    is_critical = exception_tracker.record_exception(type(e), str(e), "buy_order_execution")
                    console_logger.error(f"❌ Error occurred while executing buy order: {str(e)}")
                    
                    if is_critical:
                        console_logger.error(f"⚠️ Multiple order execution failures detected! System may need attention.")
                        logging.critical(f"Multiple consecutive order execution failures. Pausing buy operations.")
                        # Take a longer break to let transient issues resolve
                        time.sleep(30)
                    
                    # Continue to next order instead of breaking out completely, unless it's a critical system error
                    if isinstance(e, (SystemExit, KeyboardInterrupt)):
                        raise
                    if any(fatal_err in str(e).lower() for fatal_err in [
                        "authentication", "insufficient funds", "account blocked", "account restricted"
                    ]):
                        logging.critical(f"Fatal error detected: {e}")
                        console_logger.error(f"🛑 CRITICAL ERROR: {str(e)}")
                        break
            
            # Reset state for next cycle
            buy_heap = []
            sold = False
            console_logger.info("⏱️ Sleeping for 30 seconds...\n")
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
                logging.info("⏱️ Market is in early hours. Waiting for market to open...")
            
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
    

def main_with_fault_tolerance():
    """
    Wrapper around main() with fault tolerance to handle critical errors
    and ensure the system keeps running.
    """
    # Track consecutive failures
    failure_count = 0
    max_failures = 5
    
    while True:
        try:
            # Reset exception counter before each run
            exception_tracker.total_errors = 0
            
            # Run the main function, which has its own infinite loop
            main()
            
            # If we get here, main() exited (which shouldn't happen normally)
            logging.critical("Main loop exited unexpectedly. Restarting...")
            console_logger.error("❌ Trading system exited unexpectedly. Restarting...")
            
            # Reset failure count since we've run successfully for some time
            failure_count = 0
            
        except KeyboardInterrupt:
            logging.info("Keyboard interrupt received. Shutting down...")
            console_logger.info("👋 Shutting down AmpyThropic Trading System")
            break
            
        except Exception as e:
            # Track the critical error
            failure_count += 1
            is_critical = exception_tracker.record_exception(type(e), str(e), "main_loop")
            
            # Log the error
            logging.critical(f"Critical error in main loop: {e}")
            console_logger.error(f"🚨 CRITICAL ERROR: {str(e)}")
            
            if failure_count >= max_failures:
                logging.critical(f"Too many consecutive failures ({failure_count}). Exiting.")
                console_logger.error(f"🛑 System halted after {failure_count} consecutive failures.")
                break
                
            # Wait before restarting
            backoff_time = min(30 * failure_count, 300)  # Max 5 minutes
            logging.warning(f"Restarting main loop in {backoff_time} seconds...")
            console_logger.warning(f"⏱️ Restarting in {backoff_time} seconds...")
            time.sleep(backoff_time)

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='AmpyThropic Trading System')
    parser.add_argument('--report', action='store_true', help='Generate performance report without running the trading system')
    parser.add_argument('--health', action='store_true', help='Run a system health check')
    args = parser.parse_args()
    
    # Add psutil to requirements
    try:
        import psutil
    except ImportError:
        logging.warning("psutil not installed. System health monitoring will be limited.")
        console_logger.warning("⚠️ psutil not installed. Run 'pip install psutil' for better health monitoring.")
    
    # Initialize clients for all modes
    trading_client = TradingClient(API_KEY, API_SECRET)
    mongo_client = get_mongo_client(MONGO_URL)
    
    if args.report:
        # Generate performance report and exit
        console_logger.info("🚀 AmpyThropic Trading System - Performance Report Mode")
        log_portfolio_performance(trading_client, mongo_client)
    elif args.health:
        # Run system health check and exit
        console_logger.info("🚀 AmpyThropic Trading System - Health Check Mode")
        health_status = check_system_health(trading_client, mongo_client)
        console_logger.info(f"System Status: {health_status['status'].upper()}")
        for component, status in health_status['components'].items():
            status_str = status['status'] if isinstance(status, dict) and 'status' in status else 'unknown'
            console_logger.info(f"{component}: {status_str}")
    else:
        # Run the normal trading system with fault tolerance
        console_logger.info("🚀 AmpyThropic Trading System - Starting with fault tolerance")        
        main_with_fault_tolerance()