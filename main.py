import asyncio
import sys
from ib_insync import *
import pandas as pd
from tabulate import tabulate
from tabulate import tabulate
from zoneinfo import ZoneInfo
import datetime
import config

async def main():
    # 1. Connect to IBKR
    util.startLoop()  # Needed if running in notebook, but harmless here
    ib = IB()
    try:
        print(f"Connecting to IBKR at {config.IB_HOST}:{config.IB_PORT} with Client ID {config.IB_CLIENT_ID}...")
        await ib.connectAsync(config.IB_HOST, config.IB_PORT, clientId=config.IB_CLIENT_ID)
        print("Connected to IBKR!")
        
        # Request Delayed Market Data (Type 3)
        # This fixes "Requested market data requires additional subscription" errors for free/paper accounts
        ib.reqMarketDataType(3) 
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
        
        # Flatten smart exchanges and filter for standard options (multiplier 100)
        smart_chains = [c for c in chains if c.exchange == 'SMART' and c.multiplier == '100']
        if not smart_chains:
            # Fallback if no SMART
            smart_chains = [c for c in chains if c.multiplier == '100']
        
        if not smart_chains:
             print(f"No option chains found for {ticker}")
             continue
             
        # Aggregate all unique expirations from all chains
        all_expirations = set()
        for c in smart_chains:
            all_expirations.update(c.expirations)
        expirations = sorted(list(all_expirations))
        
        # Use configured timezone for today's date
        tz = ZoneInfo(config.TIMEZONE)
        now = datetime.datetime.now(tz)
        today = now.date()
        
        target_dates = []
        for target_days in config.TARGET_DAYS_TO_EXPIRATION:
            target_date_approx = today + datetime.timedelta(days=target_days)
            
            # Filter expirations to future only
            future_exps = [d for d in expirations if datetime.datetime.strptime(d, '%Y%m%d').date() >= today]
            
            if not future_exps:
                continue

            # Find closest expiration
            closest_date = min(future_exps, 
                               key=lambda x: abs((datetime.datetime.strptime(x, '%Y%m%d').date() - target_date_approx).days))
            
            if closest_date not in target_dates:
                target_dates.append(closest_date)
        
        print(f"  Target Expirations: {target_dates}")

        # Request Market Data for filtered options
        contracts = []
        target_max_strike = current_price * (1 - config.MIN_OTM_PCT)
        target_min_strike = current_price * (1 - config.MAX_OTM_PCT)

        for exp in target_dates:
            # Find chains that support this expiration
            valid_chains = [c for c in smart_chains if exp in c.expirations]
            
            if not valid_chains:
                continue

            for chain in valid_chains:
                # Filter strikes for this specific chain
                chain_strikes = [k for k in chain.strikes if target_min_strike <= k <= target_max_strike]
                
                if not chain_strikes:
                    continue
                    
                print(f"  For {exp} (Trading Class: {chain.tradingClass}): found {len(chain_strikes)} strikes")
                
                for strike in chain_strikes:
                    # Use tradingClass to ensure we get the specific contract from this chain
                    # This prevents Error 200 when SMART requires disambiguation
                    contract = Option(stock.symbol, exp, strike, 'P', 'SMART', tradingClass=chain.tradingClass)
                    contracts.append(contract)
        
        # Remove duplicates if multiple chains cover same contract (unlikely with different tradingClass but possible logic)
        # Using a dictionary to unique-ify by key properties might be safer, but ib_insync qualify usually handles identicals.
        # However, let's just proceed. The qualifyContractsAsync usually handles list of contracts fine.
        
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
        for _ in range(100): # Increased wait time to 10s
            if all(t.bid != -1 or t.close != float('nan') for t in tickers): # Basic check
                break
            await asyncio.sleep(0.1)
            
        # Process Results
        print(f"  Processing {len(tickers)} Option Tickers...")
        
        # Identify contracts execution that need historical data
        tasks = []
        indices_needing_history = []
        
        for i, t in enumerate(tickers):
            # Check if we have valid data
            has_data = (t.bid > 0) or (not pd.isna(t.last) and t.last > 0) or (not pd.isna(t.close) and t.close > 0)
            if not has_data:
                # Request historical data for this contract
                task = ib.reqHistoricalDataAsync(
                    t.contract, endDateTime='', durationStr='1 D',
                    barSizeSetting='1 day', whatToShow='MIDPOINT', useRTH=1
                )
                tasks.append(task)
                indices_needing_history.append(i)
        
        if tasks:
            print(f"  Fetching historical data for {len(tasks)} contracts (market closed/no data)...")
            history_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Update tickers/results with historical data
            for i, result in zip(indices_needing_history, history_results):
                if isinstance(result, list) and result:
                    # We have bars
                    close_price = result[-1].close
                    # We can't update t.close directly effectively as it's a Ticker object from stream
                    # But we can assume this is our premium for the logic below
                    # Let's store it in a side map or just modify the processing loop to handle it
                    tickers[i].__setattr__('temp_close', close_price)  # Monkey patch for local logic
                else:
                    tickers[i].__setattr__('temp_close', float('nan'))

        for t in tickers:
            contract = t.contract
            
            # Determine Premium
            premium = t.bid
            if premium <= 0:
                premium = t.last if not pd.isna(t.last) else t.close
            
            # Fallback to historical close if we fetched it
            if (pd.isna(premium) or premium <= 0) and hasattr(t, 'temp_close'):
                premium = t.temp_close

            if pd.isna(premium) or premium <= 0:
                continue # Skip if no valid price data
            
            # Calculate Return
            
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
                'Price': current_price,
                'Expiration': contract.lastTradeDateOrContractMonth,
                'DTE': dte,
                'Strike': strike,
                'OTM %': f"{(1 - strike/current_price)*100:.1f}",
                'Premium': premium,
                'ROI %': round(roi * 100, 2),
                'Ann. ROI %': round(annualized_roi * 100, 2)
            })

    # Summary
    if results:
        df = pd.DataFrame(results)
        df = df.sort_values('Ann. ROI %', ascending=False)
        print("\n" + tabulate(df, headers='keys', tablefmt='psql', floatfmt=".2f"))
        
        # Save to CSV
        # Save to CSV (using configured timezone for filename timestamp)
        # Note: 'now' is already timezone-aware from earlier
        timestamp = now.strftime('%Y%m%d_%H%M%S')
        csv_file = f'scan_results_{timestamp}.csv'
        df.to_csv(csv_file, index=False)
        print(f"\nResults saved to {csv_file}")
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
