# User Configuration

# List of stocks to scan
STOCKS = [
    'NVDA',
    'AAPL',
    'TSLA',
    'AMD',
    'MSFT'
]

# Expiration filters
# We will look for expirations that are approximately these many days away
# This is a soft target; we'll find the closest monthly or weekly expirations
TARGET_DAYS_TO_EXPIRATION = [30, 45, 60, 90]

# Strike Price Selection
# Percentage OTM (Out of The Money)
# 0.0 means At The Money (ATM)
# 0.20 means 20% below current price
MIN_OTM_PCT = 0.05
MAX_OTM_PCT = 0.20

# IBKR Connection Details
IB_HOST = '127.0.0.1'
IB_PORT = 7497  # Default TWS paper trading port. Use 4001 for Gateway.
IB_CLIENT_ID = 1

# Other settings
RISK_FREE_RATE = 0.04  # Used for Sharpe etc (future use), mainly placeholder now
