import asyncio
import sys
from ib_insync import *
import pandas as pd
from tabulate import tabulate
import config

async def main():
    # 1. Connect to IBKR
    util.startLoop()  # Needed if running in notebook, but harmless here
    ib = IB()
    try:
        print(f"Connecting to IBKR at {config.IB_HOST}:{config.IB_PORT} with Client ID {config.IB_CLIENT_ID}...")
        await ib.connectAsync(config.IB_HOST, config.IB_PORT, clientId=config.IB_CLIENT_ID)
        print("Connected to IBKR!")
    except Exception as e:
        print(f"Failed to connect to IBKR: {e}")
        print("Please ensure TWS or IB Gateway is running and API ports are configured.")
        return

    # 2. Main Scan Loop
    results = []
    
    for ticker in config.STOCKS:
        print(f"\nScanning {ticker}...")
        stock = Stock(ticker, 'SMART', 'USD')
        
        # Qualify contract to get conId
        try:
            qualified_contracts = await ib.qualifyContractsAsync(stock)
            if not qualified_contracts:
                print(f"Could not qualify contract for {ticker}")
                continue
            stock = qualified_contracts[0]
        except Exception as e:
            print(f"Error qualifying {ticker}: {e}")
            continue

        # Get Market Data (Price)
        # Snapshot=True to get a single point of data
        ticker_data = ib.reqMktData(stock, '', False, False)
        # Wait a bit for data to populate
        # In a real app we might use events, but waiting is simple for a script
        c = 0
        while ticker_data.last != ticker_data.last and c < 50: # Wait until we have a last price or timeout
            await asyncio.sleep(0.1)
            c += 1
            
        # Fallback to close if last is NaN (e.g. after hours, though last usually persists)
        current_price = ticker_data.last if not pd.isna(ticker_data.last) else ticker_data.close
        
        if pd.isna(current_price):
             # Try requesting historical data for latest close if live data fails (e.g. weekend)
            bars = await ib.reqHistoricalDataAsync(
                stock, endDateTime='', durationStr='1 D',
                barSizeSetting='1 day', whatToShow='TRADES', useRTH=1
            )
            if bars:
                current_price = bars[-1].close
            else:
                print(f"Could not get price for {ticker}")
                continue

        print(f"{ticker} Price: {current_price}")

        # 3. Get Option Chains
        chains = await ib.reqSecDefOptParamsAsync(stock.symbol, '', stock.secType, stock.conId)
        
        # Flatten smart exchanges
        smart_chains = [c for c in chains if c.exchange == 'SMART']
        if not smart_chains:
            # Fallback if no SMART
            smart_chains = chains
        
        # For simplicity, take the first valid chain set (usually contains all expirations/strikes)
        if not smart_chains:
             print(f"No option chains found for {ticker}")
             continue
             
        chain = smart_chains[0]
        
        # Filter Expirations
        expirations = sorted(list(chain.expirations))
        import datetime
        today = datetime.date.today()
        
        target_dates = []
        for target_days in config.TARGET_DAYS_TO_EXPIRATION:
            target_date_approx = today + datetime.timedelta(days=target_days)
            # Find closest expiration
            # We look for something within +/- 7 days of target
            # Or just take the closest one if we want to be robust
            
            # Simple approach: closest future expiration
            closest_date = min([d for d in expirations if datetime.datetime.strptime(d, '%Y%m%d').date() >= today], 
                               key=lambda x: abs((datetime.datetime.strptime(x, '%Y%m%d').date() - target_date_approx).days))
            
            if closest_date not in target_dates:
                target_dates.append(closest_date)
        
        print(f"  Target Expirations: {target_dates}")

        # Filter Strikes
        target_max_strike = current_price * (1 - config.MIN_OTM_PCT)
        target_min_strike = current_price * (1 - config.MAX_OTM_PCT)
        
        strikes = [k for k in chain.strikes if target_min_strike <= k <= target_max_strike]
        print(f"  Target Strikes ({len(strikes)}): {strikes}")

        # Request Market Data for filtered options
        contracts = []
        for exp in target_dates:
            for strike in strikes:
                contract = Option(stock.symbol, exp, strike, 'P', 'SMART')
                contracts.append(contract)
        
        if not contracts:
             print("  No contracts found matching criteria.")
             continue

        # Qualify contracts is slow for many, but safer. 
        # For speed we might skip or do in batches, but let's qualify.
        print(f"  Qualifying {len(contracts)} contracts...")
        contracts = await ib.qualifyContractsAsync(*contracts)
        
        print(f"  Requesting market data...")
        tickers = [ib.reqMktData(c, '', False, False) for c in contracts]
        
        # Wait for data
        # Simple wait loop; in production use events
        for _ in range(50):
            if all(t.bid != -1 or t.close != float('nan') for t in tickers): # Basic check
                break
            await asyncio.sleep(0.1)
            
        # Process Results
        for t in tickers:
            contract = t.contract
            
            # Determine Premium
            # Use bid price if available (conservative for selling), else last or close
            # Note: IBKR returns -1 for empty bid
            premium = t.bid
            if premium <= 0:
                premium = t.last if not pd.isna(t.last) else t.close
                
            if pd.isna(premium) or premium <= 0:
                continue # Skip if no valid price data
            
            # Calculate Return
            strike = contract.strike
            collateral = strike * 100
            premium_total = premium * 100
            
            # Days to Expiration
            exp_date = datetime.datetime.strptime(contract.lastTradeDateOrContractMonth, '%Y%m%d').date()
            dte = (exp_date - today).days
            if dte <= 0: dte = 1 # Avoid div/0
            
            roi = premium_total / collateral
            annualized_roi = roi * (365 / dte)
            
            results.append({
                'Stock': contract.symbol,
                'Expiration': contract.lastTradeDateOrContractMonth,
                'DTE': dte,
                'Strike': strike,
                'Price': current_price,
                'OTM %': f"{(1 - strike/current_price)*100:.1f}%",
                'Premium': premium,
                'ROI %': roi * 100,
                'Ann. ROI %': annualized_roi * 100
            })

    # Summary
    if results:
        df = pd.DataFrame(results)
        df = df.sort_values('Ann. ROI %', ascending=False)
        print("\n" + tabulate(df, headers='keys', tablefmt='psql', floatfmt=".2f"))
    else:
        print("\nNo opportunities found.")

    ib.disconnect()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        print(f"An error occurred: {e}")
