# CSP Scanner (Cash Secured Put Scanner)

A Python-based tool that scans for Cash Secured Put (CSP) opportunities using the Interactive Brokers (IBKR) API. This tool automates the process of finding option contracts that meet your specific risk and return criteria.

## Disclaimer

> [!WARNING]
> **This software is for educational purposes only.** Do not engage in live trading with this tool/algorithm unless you completely understand the risks involved. Options trading involves significant risk and is not suitable for all investors. The authors/contributors are not financial advisors.

## Features

- **Automated Scanning**: Iterates through a user-defined list of stock symbols.
- **Smart Expiration Filtering**: Automatically finds option chains closest to your target "Days to Expiration" (DTE) (e.g., 30 days, 45 days).
- **Strike Selection**: Filters strikes based on percentage Out-of-the-Money (OTM) calculation.
- **Return metrics**: Calculates:
  - **ROI**: Return on collateral (Strike Price × 100).
  - **Annualized ROI**: ROI normalized to a yearly rate for better comparison.
- **Data Robustness**:
  - Handles "Smart" routing and falls back to standard exchanges.
  - Retrieves historical data if live market data is unavailable (outside market hours).
- **Output**:
  - Displays a sorted table of filtered opportunities in the console.
  - Exports full results to a CSV file (`scan_results_YYYYMMDD_HHMMSS.csv`).

## Prerequisites

1. **Interactive Brokers Account**: You need an account with [Interactive Brokers](https://www.interactivebrokers.com/).
2. **Trader Workstation (TWS) or IB Gateway**:
   - Download and install TWS or IB Gateway.
   - **Configuration**:
     - Go to `File > Global Configuration > API > Settings`.
     - Check **"Enable ActiveX and Socket Clients"**.
     - Note the **Socket Port** (usually `7496` for TWS Live, `7497` for TWS Paper, `4001` or `4002` for Gateway).
     - Ensure `127.0.0.1` is in the "Trusted IPs" list (usually there by default).
3. **Python 3.9+**

## Installation

This project uses [Poetry](https://python-poetry.org/) for dependency management.

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd csp_scanner
   ```

2. **Install dependencies**:
   ```bash
   poetry install
   ```

## Configuration

All settings are managed in `config.py`.

### 1. Stock Selection
Modify the `STOCKS` list to include the symbols you want to scan.
```python
STOCKS = ['AAPL', 'MSFT', 'GOOG', 'NVDA']
```

### 2. Expiration Targets
Set the `TARGET_DAYS_TO_EXPIRATION` list. The scanner will find the closest available expiration date for each target.
```python
# Look for options expiring in approx 30 and 45 days
TARGET_DAYS_TO_EXPIRATION = [30, 45]
```

### 3. Strike Filtration (OTM)
Configure the Out-of-the-Money (OTM) range.
- `0.0` = At The Money (ATM)
- `0.1` = 10% below current price (for Puts)
- `-0.02` = 2% In The Money (ITM) - *Be careful with ITM puts!*

```python
# Look for strikes between -2% ITM and 5% OTM (below price)
# Note: For Puts, a lower strike is "more OTM".
# Logic: target_strike <= current_price * (1 - MIN_OTM)
MIN_OTM_PCT = 0.05  # e.g., Strike must be at least 5% below price
MAX_OTM_PCT = 0.20  # e.g., Strike must be no more than 20% below price
```
*Note: Check `main.py` logic to confirm how these specific flags are applied if behavior needs tuning.*

### 4. Connection Settings
Ensure these match your TWS/Gateway settings.
```python
IB_HOST = '127.0.0.1'
IB_PORT = 7496      # 7497 for Paper Trading
IB_CLIENT_ID = 1    # Unique ID for this client
```

## Usage

1. **Start TWS or IB Gateway** and ensure you are logged in.
2. **Run the scanner**:

   Using Poetry:
   ```bash
   poetry run python main.py
   ```

   Or activate the shell first:
   ```bash
   poetry shell
   python main.py
   ```

## Output

The script will print progress as it scans each stock. Once finished, it displays a summary table:

```text
+-------+---------+------------+-------+----------+---------+------------+---------+--------------+
| Stock |   Price | Expiration |   DTE |   Strike | OTM %   |    Premium |   ROI % |   Ann. ROI % |
|-------+---------+------------+-------+----------+---------+------------+---------+--------------|
| NVDA  |  120.50 | 20240315   |    30 |   110.00 | 8.7     |       2.50 |    2.27 |        27.65 |
| AAPL  |  180.25 | 20240315   |    30 |   170.00 | 5.7     |       1.85 |    1.09 |        13.24 |
+-------+---------+------------+-------+----------+---------+------------+---------+--------------+
```

It also saves a CSV file: `scan_results_20240214_103000.csv`.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

[MIT License](LICENSE) (or whichever you choose)
