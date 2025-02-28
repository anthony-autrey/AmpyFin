from config import POLYGON_API_KEY, FINANCIAL_PREP_API_KEY, API_KEY, API_SECRET, BASE_URL, MONGO_URL
import os

# Import environment variables for Docker from .env file
# If environment variables are not present, config.py values will be used
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", POLYGON_API_KEY) 
FINANCIAL_PREP_API_KEY = os.getenv("FINANCIAL_PREP_API_KEY", FINANCIAL_PREP_API_KEY) 
API_KEY = os.getenv("API_KEY", API_KEY) 
API_SECRET = os.getenv("API_SECRET", API_SECRET)
BASE_URL = os.getenv("BASE_URL", BASE_URL)
MONGO_URL = os.getenv("MONGO_URL", MONGO_URL)

# Baseline values for portfolio and indices comparison
BASELINE_PORTFOLIO_VALUE = float(os.getenv("BASELINE_PORTFOLIO_VALUE", 50000.00))
BASELINE_SPY = float(os.getenv("BASELINE_SPY", 591.95))
BASELINE_QQQ = float(os.getenv("BASELINE_QQQ", 518.58))
BASELINE_VONG = float(os.getenv("BASELINE_VONG", 380.00))
BASELINE_SCHG = float(os.getenv("BASELINE_SCHG", 92.00))
BASELINE_IWY = float(os.getenv("BASELINE_IWY", 132.00))