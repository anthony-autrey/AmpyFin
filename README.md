
# 🌟 AmpyFin Trading System

## 🚀 Introduction

Welcome to **AmpyFin**, an advanced AI-powered trading system designed for the NASDAQ-100. Imagine having expert traders working for you 24/7—AmpyFin makes this a reality.

## 📊 AmpyFin’s Data Collection Power

### 🔍 Data Sources

- **Financial Modeling Prep API**: Retrieves NASDAQ-100 tickers to gain crucial market insights.

### 💾 Data Storage

All data and trading logs are securely stored in **MongoDB**, allowing fast access to historical trading information and supporting in-depth analysis.

### 🤖 Machine Learning at Work

At the core of AmpyFin are diverse algorithms optimized for different market conditions. Rather than relying on a single strategy or multiple strategies, AmpyFin relies on a ranked ensemble learning system that dynamically ranks each strategy and gives more influence in the final decision to strategies with better performance.

### 📈 Trading Strategies

Some of the strategies AmpyFin employs include:

- **📊 Mean Reversion**: Predicts asset prices will return to their historical average.
- **📈 Momentum**: Capitalizes on prevailing market trends.
- **💱 Arbitrage**: Identifies and exploits price discrepancies between related assets.
- **🧠 AI-Driven Custom Strategies**: Continuously refined through machine learning for enhanced performance.

These strategies work collaboratively, ensuring AmpyFin is always prepared for changing market dynamics.

### 🔗 How Dynamic Ranking Works

Managing multiple algorithms is simplified with AmpyFin’s dynamic ranking system, which ranks each algorithm based on performance.

#### 🏆 Ranking System

Each strategy starts with a base score of 0 and a mock balance of $50,000. The system evaluates their performance and assigns a weight based on the following function:

$$
\left( \frac{e^e}{e^2} - 1 \right)^{2i}
$$

Where \(i\) is the strategy's rank. Please keep in mind that the strategy's rank is inverse of its performance. So a strategy ranked 132 is actually performing the best while strategy ranked 1 is performing the worst currently.

#### ⏳ Time Delta Coefficient

This ensures that strategies with better recent performance have a greater influence on decision-making while maintaining balance by also accounting for old performance as well.

### 💡 Benefits of Dynamic Ranking

- **📉 Quickly adapts to changing market conditions.**
- **📊 Prioritizes high-performing algorithms.**
- **⚖️ Balances risk while maximizing potential returns.**

## 📂 File Structure and Objectives

### 🕹️ control.py

**Objective**: Designed to allow users to change parameters based on how they would like their version of Ampyfin to trade. Testing and training will also be supported options for both trading and ranking modes.

### 🤝 trading_client.py

**Objective**: Executes trades based on algorithmic decisions.

**Features**:

- Executes trades every 60 seconds by default (adjustable based on user).
- Ensures a minimum spending balance of $15,000 (adjustable based on user) and maintains 30% liquidity (adjustable based on user).
- Logs trades with details like timestamp, stock, and reasoning.
- Margin trading support with safety checks to prevent margin calls.
- Configurable margin safety ratio (default: 30%) to maintain a buffer above Alpaca's maintenance margin requirements.
- Short selling capabilities with additional risk controls:
  - Configurable maximum short portfolio ratio (default: 25%)
  - Higher margin safety requirements for short positions (default: 40%)
  - Position size limits specific to short trades
  - Customizable stop-loss and take-profit settings for shorts
  - Option to use regular sell signals for shorting (SHORT_ON_SELL_SIGNALS)

### 🏆 ranking_client.py

**Objective**: Runs the ranking system to evaluate trading strategies.

**Features**:

- Downloads NASDAQ-100 tickers and stores them in MongoDB.
- Updates algorithm scores and rankings every 120 seconds (adjustable based on user).

### 🏋️ training_client.py

**Objective**: Allows users to train a simulator from scratch, test the simulator, and update their simulator from local to database.

**Features**:

- Training using parameters given by control.py
- Testing using parameters given by control.py
- Option to push trained rank model into MongoDB

### 📜 strategies/*

**Objective**: Defines various trading strategies. Houses strategies like mean reversion, momentum, and arbitrage.

**Features**:

- **trading_strategies_v1.py**: Archived first iteration of AmpyFin used 5 strategies. This file is not supported anymore but is a great reference material
- **trading_strategies_v2.py**:  Archived second gen older strategies being used in the ranking system. Contains 50 strategies with a lot leaning towards momentum.
- **trading_strategies_v2_1.py**: Archived second gen older strategies that complements the older strategies in trading_strategies_v2.py. Houses 10 more strategies. This is where newer strategies will be implemented until it caps at 50 strategies as well.
- **talib_indicators.py**: Contains all the technical indicators used in the strategies. To visit the documentation for each technical indicator, please visit the following link: [Link to TA](https://ta-lib.org/). These indicators were not developed by me, but I have modified their use to fit the needs of AmpyFin. Each indicator is fine tuned with a specific period and historical data is either retrieved from MongoDB cache system or from yfinance.

### 🔧 helper_files/*

**Objective**: Helper Files to help with both trading client and ranking client. Houses functions for retrieving a Mongo Client, getting latest prices, current strategies implemented etc.

**Features**:

- **client_helper.py**: Contains common functions for client operations in both ranking and trading.
- **train_client_helper.py**: Contains utility functions for training and testing.

### 💡 utils/*

**Objective**: Contains utility functions for data processing and analysis as well as other miscellaneous functions. These functions are not necessarily being used currently in trading or ranking but stored for development purposes.

**Features**:

- **check_strategy_scores.py**: Checks the scores of the strategies and prints them out.
- **sell_all.py**: Sells all the stocks in the portfolio.
- **sync_alpaca.py**: Syncs the Alpaca account with the MongoDB account.

## ⚙️ Installation

### 1️⃣ Clone the Repository

```bash
git clone https://github.com/yeonholee50/AmpyFin.git
cd AmpyFin
```

### 2️⃣ Install Dependencies

- Run the following command to install the required Python packages:
```bash
pip install -r requirements.txt
```

- We have recently migrated to using Ta-Lib for trading. Please follow the installation instructions here: 

👉 [Ta-Lib Python Original](https://github.com/TA-Lib/ta-lib-python)

👉 [Ta-Lib Python Easy Installation](https://github.com/cgohlke/talib-build/releases)

### 3️⃣ Configuration

1. **Option 1: Create `config.py`**:
   - Copy `templates/config_template.py` to `config.py` and enter your API keys and MongoDB connection string.
    ```python
    FINANCIAL_PREP_API_KEY = "your_fmp_api_key"
    API_KEY = "your_alpaca_api_key"
    API_SECRET = "your_alpaca_secret_key"
    BASE_URL = "https://paper-api.alpaca.markets"
    MONGO_URL = "your mongo connection string"
    ```

2. **Option 2: Use Environment Variables (Recommended)**:
   - Copy `.env_template` to `.env` and customize your settings.
   - All system parameters are configurable through environment variables.
   - Key parameters include:
     - API keys and connection strings
     - Trading parameters (stop loss, take profit)
     - Liquidity and asset limits
     - Margin safety parameters
     - Time delta settings for backtesting
     - Training parameters and date ranges

### 4️⃣ API Setup

- Financial Modeling Prep API
1. Sign up at [Financial Modeling Prep](https://financialmodelingprep.com/) and get an API key.
2. Add it to `config.py` as `FINANCIAL_PREP_API_KEY`.

- Alpaca API
1. Sign up at [Alpaca](https://alpaca.markets/) and get API keys.
2. Add them to `config.py` as `API_KEY` and `API_SECRET`.

### 5️⃣ Set Up MongoDB

- Sign up for a MongoDB cluster (e.g., via MongoDB Atlas).
- Create a database for stock data storage and replace the `MONGO_URL` in 'config.py' with your connection string. Make sure to give yourself Network Access.
- Run the setup script `setup.py`:
- After running the mongo setup script, the MongoDB setup for the rest will be completed on the first minute in trading for both ranking and trading.

## ⚡ Usage

### Running the Trading and Ranking System

- To run the trading and ranking system, execute on two separate terminals:

```bash
python ranking_client.py
python trading_client.py
```

### Command Line Flags for the Trading Client

The trading client supports several command line flags for different operations:

```bash
# Start the trading system in normal mode
python trading_client.py

# Generate a performance report without starting the trading system
python trading_client.py --report

# Run a system health check
python trading_client.py --health

# Start the system in recovery mode (more conservative trading settings)
python trading_client.py --recovery
```

#### Flag Details:

- `--report`: Generates a comprehensive performance report comparing your portfolio to major indices (SPY, QQQ, VONG, SCHG, IWY) with both daily and year-to-date statistics.

- `--health`: Runs a comprehensive system health check that evaluates:
  - Alpaca API connectivity
  - MongoDB connectivity
  - System resources (CPU, memory, disk)
  - Error statistics
  
- `--recovery`: Starts the system with more conservative trading parameters:
  - Reduces position sizes by 50%
  - Increases margin safety buffer by 50%
  - Raises the threshold for suggested trades
  - This mode is useful after system failures or during volatile market conditions

### Using the Training Client

- To train using training_client.py:

1. First change the mode in control.py:
```bash
mode = 'train'
```

2. Adjust parameters according to your specifications in control.py

3. Execute on terminal:

```bash
python training_client.py
```

- To test using training_client.py:

1. First change the mode in control.py:
```bash
mode = 'test'
```

2. Adjust parameters according to your specifications in control.py. Advice is to not overlap your training dates and testing dates.

3. Execute on terminal:

```bash
python training_client.py
```

- To push your model into MongoDB:

1. First change the mode in control.py:
```bash
mode = 'push'
```

2. Make sure you have tested your model and confirm you would like to replace your existing model in MongoDB with your new one.

3. Execute on terminal:

```bash
python training_client.py
```


## 🐋 Using Docker (Optional)

AmpyFin includes a Dockerfile to automate the installation process and package the application as a Docker image. Using Docker offers several benefits:

- **Easy Deployment:** Deploy the same image across different environments.
- **Automated Restarts:** Containers can be configured to restart automatically on failure.
- **Environment Configuration:** Set up via environment variables or a dedicated `.env` file.

### Prerequisites
Before you begin, ensure that [Docker is installed](https://docs.docker.com/get-docker/) on your system.

### 1️⃣ Create the `.env` File
1. Copy `.env_template` to `.env` and enter your API keys and MongoDB connection string.
    ```
    # API Keys
    POLYGON_API_KEY=your_polygon_api_key
    FINANCIAL_PREP_API_KEY=your_fmp_api_key
    API_KEY=your_alpaca_api_key
    API_SECRET=your_alpaca_secret_key
    BASE_URL=https://paper-api.alpaca.markets
    MONGO_URL=mongodb://mongo:27017/db  # Leave this value if running MongoDB in the local Docker service (see below).
    ```

2. Customize Trading Parameters (all parameters are configurable):
    ```
    # Trading Parameters
    STOP_LOSS=0.03
    TAKE_PROFIT=0.05
    
    # Trading Client Parameters
    TRADE_LIQUIDITY_LIMIT=15000
    TRADE_ASSET_LIMIT=0.1
    SUGGESTION_HEAP_LIMIT=600000
    
    # Margin Safety Parameters
    MIN_MARGIN_RATIO=0.30
    ```

3. Configure Training and Backtest Settings:
    ```
    # Training Client Parameters
    # Modes: 'train', 'test', 'live', 'push'
    TRAIN_MODE=test
    TRAIN_START=2024-01-01
    TRAIN_END=2025-01-01
    
    # Training Cash Parameters
    TRAIN_START_CASH=50000.00
    TRAIN_TRADE_LIQUIDITY_LIMIT=15000.00
    ```
    
The system will automatically load these environment variables when starting up. For a complete list of all configurable parameters, see the `.env_template` file.

### 2️⃣ Build Ampyfin Docker Image and Initialize Database

Build the Docker image using the provided Dockerfile. Run this command in the root directory of your project:
```bash
docker build -t ampyfin .
COMPOSE_PROFILES=setup,mongo docker compose up # exclude ",mongo" if not running the local MongoDB service
```
The first command tells Docker to build an image named ampyfin based on the instructions in your Dockerfile. The second command runs the image and tells it to run the setup.py script, which initializes the MongoDB database.

### 3️⃣ Run the Ranking and Trading Containers

AmpyFin is designed to run its ranking and trading services in separate containers. To start the services, use Docker Compose:
```bash
docker compose up
```
What this does:
- Starts Multiple Containers: Each service (ranking and trading) runs in its own container.
- Automatic Restart: Containers are configured to restart automatically if they crash.
- Unified Environment: Docker Compose sets up networking between containers for seamless communication.

*Tip*: To run the containers in the background (detached mode), use:
```bash
docker compose up -d
```

## ⚠️ IMPORTANT

For people looking to do live trading, I suggest training via running ranking_client.py for at least two weeks before running the trading system altogether. Or train using training_client.py before executing live trades. This way, you're running with a client that has been trained to a certain extent (with strategies ranked) and is ready to go. Otherwise, you will most likely be buying random stocks.

## 🛡️ Fault Tolerance Features

AmpyThropic includes robust fault tolerance features to ensure reliable operation:

### Exception Handling and Recovery
- **Automatic Retry Logic**: Critical operations like API calls and database queries automatically retry with exponential backoff
- **Error Pattern Detection**: System monitors error patterns to identify recurring issues
- **Self-Healing**: Trading system can recover automatically from many types of failures
- **Recovery Mode**: Start with `--recovery` flag for more conservative operation after system issues

### System Health Monitoring
- **Periodic Health Checks**: System automatically runs diagnostics at regular intervals
- **Resource Monitoring**: Tracks CPU, memory, and disk usage (requires psutil)
- **API Connectivity**: Monitors connections to Alpaca and MongoDB
- **Error Tracking**: Records exception patterns and frequencies

### Resilient Data Operations
- **Connection Pooling**: Efficient database connection management
- **Idempotent Operations**: Prevents duplicate orders during retries
- **Caching Strategies**: Reduces API calls for frequently accessed data
- **Data Validation**: Validates all external data before processing

### Defensive Trading
- **Margin Safety**: Prevents trades that would violate margin requirements
- **Transaction Guards**: Ensures database consistency during trading operations
- **Rate Limit Protection**: Handles API rate limits gracefully
- **Critical Error Prevention**: Additional safeguards around high-risk operations

## 📑 Logging and Diagnostics

- **system.log**: Tracks major events like API errors and MongoDB operations.
- **rank_system.log**: Logs all ranking-related events and updates.
- **MongoDB Diagnostics**: Health data and error statistics stored in MongoDB
- **Console Output**: Color-coded real-time status with emojis for better readability
- **Performance Reports**: Comprehensive daily and YTD performance tracking
- **Email Alerts**: Sends notifications for critical events and performance anomalies

### 📧 Email Alert System

AmpyThropic includes an email alerting system that notifies you of:

1. **System Errors**: Repeated or critical errors that may require attention
2. **Health Issues**: Degraded system health including connectivity problems
3. **Performance Anomalies**: Significant underperformance or market declines
4. **Resource Warnings**: High memory/CPU usage or low disk space

#### Setting Up Gmail SMTP Alerts

1. **Create an App Password** in your Google Account:
   - Go to your Google Account → Security → App passwords
   - Select "Mail" and "Other" (custom name: "AmpyThropic")
   - Copy the generated 16-character password

2. **Configure Your .env File**:
   ```
   # Email Alert Configuration
   ENABLE_EMAIL_ALERTS=True
   EMAIL_FROM=your.email@gmail.com
   EMAIL_TO=your.email@gmail.com
   EMAIL_APP_PASSWORD=your_16_char_app_password
   SMTP_SERVER=smtp.gmail.com
   SMTP_PORT=587
   ALERT_RATE_LIMIT_MINUTES=15
   ```

3. **Understanding Alert Levels**:
   - **CRITICAL** 🔴: Immediate attention required (system failure, critical errors)
   - **ERROR** 🟠: Errors that affect system operation
   - **WARNING** 🟡: Issues that may lead to problems but aren't critical yet
   - **INFO** 🔵: Important information (significant outperformance)

## 🛠️ Contributing

Contributions are welcome! 🎉 Feel free to submit pull requests or report issues. All contributions should be made on the **test branch**. Please avoid committing directly to the **main branch**.

## 📜 License

This project is licensed under the MIT License. See the LICENSE file for details.
