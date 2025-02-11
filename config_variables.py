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