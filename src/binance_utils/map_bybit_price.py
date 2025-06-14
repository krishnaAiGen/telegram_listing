import json
import requests
import pandas as pd
from datetime import datetime, timezone, timedelta
import time
import os

INPUT_JSON = '/Users/krishnayadav/Documents/test_projects/telegram_listing/binance_data/bybit_futures_coin_symbols_sorted.json'
OUTPUT_CSV = '/Users/krishnayadav/Documents/test_projects/telegram_listing/binance_data/bybit_coin_price_analysis.csv'
PRICE_DATA_FOLDER = '/Users/krishnayadav/Documents/test_projects/telegram_listing/binance_data/bybit_coin_price'

# Create bybit_coin_price folder if it doesn't exist
os.makedirs(PRICE_DATA_FOLDER, exist_ok=True)

# Get valid Bybit futures symbols at the start
def get_bybit_futures_symbols():
    """Get all valid Bybit futures symbols"""
    url = 'https://api.bybit.com/v5/market/instruments-info'
    params = {'category': 'linear'}
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        if data['retCode'] == 0:
            return set(instrument['symbol'] for instrument in data['result']['list'] 
                      if instrument['status'] == 'Trading')
    except Exception as e:
        print(f"Error fetching Bybit symbols: {e}")
    
    return set()

futures_symbols = get_bybit_futures_symbols()
print(f"Found {len(futures_symbols)} active Bybit futures symbols")

def get_first_kline_bybit(symbol, interval='5'):
    """Get the very first kline from Bybit (when coin was listed)"""
    url = 'https://api.bybit.com/v5/market/kline'
    params = {
        'category': 'linear',
        'symbol': symbol,
        'interval': interval,
        'limit': 1,
        'start': 0  # Get from the very beginning
    }
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        if data['retCode'] == 0 and data['result']['list']:
            return data['result']['list'][0]
    except Exception as e:
        print(f"  Error getting first kline for {symbol}: {e}")
    
    return None

def get_klines_for_duration_bybit(symbol, start_time, hours=48, interval='5'):
    """Get klines for specified duration from start_time in 5-minute intervals using Bybit API"""
    url = 'https://api.bybit.com/v5/market/kline'
    end_time = start_time + timedelta(hours=hours)
    
    # Calculate how many klines we need (48 hours = 576 5-minute intervals)
    target_klines = (hours * 60) // 5
    
    all_klines = []
    current_start = start_time
    
    print(f"    Fetching data from {start_time.isoformat()} to {end_time.isoformat()}")
    print(f"    Target klines needed: {target_klines}")
    
    while current_start < end_time and len(all_klines) < target_klines:
        # Calculate end time for this batch (max 1000 klines per request)
        batch_end = min(end_time, current_start + timedelta(minutes=5000))  # 1000 * 5 minutes
        
        params = {
            'category': 'linear',
            'symbol': symbol,
            'interval': interval,
            'start': int(current_start.timestamp() * 1000),
            'end': int(batch_end.timestamp() * 1000),
            'limit': 1000
        }
        
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            if data['retCode'] == 0 and data['result']['list']:
                klines = data['result']['list']
                # Bybit returns data in reverse chronological order, so reverse it
                klines.reverse()
                
                # Filter klines to ensure they're within our time range
                filtered_klines = []
                for kline in klines:
                    kline_time = datetime.utcfromtimestamp(int(kline[0]) / 1000).replace(tzinfo=timezone.utc)
                    if start_time <= kline_time <= end_time:
                        filtered_klines.append(kline)
                
                all_klines.extend(filtered_klines)
                print(f"    Batch: Got {len(filtered_klines)} klines, Total: {len(all_klines)}")
                
                if len(klines) < 1000:  # No more data available
                    print(f"    Reached end of available data (got {len(klines)} klines in last batch)")
                    break
                
                # Update current_start to the last kline's time + 5 minutes
                if filtered_klines:
                    last_kline_time = datetime.utcfromtimestamp(int(filtered_klines[-1][0]) / 1000).replace(tzinfo=timezone.utc)
                    current_start = last_kline_time + timedelta(minutes=5)
                else:
                    break
            else:
                print(f"    API Error: retCode={data.get('retCode')}, retMsg={data.get('retMsg')}")
                break
        except Exception as e:
            print(f"    Error fetching klines: {e}")
            break
        
        time.sleep(0.1)  # Small delay to avoid rate limits
    
    print(f"    Final result: {len(all_klines)} klines collected")
    return all_klines

def save_price_data_bybit(symbol, klines_data, listing_time):
    """Save Bybit price data to JSON file"""
    if not klines_data:
        return
    
    # Prepare price data in a structured format
    price_data = {
        'symbol': symbol,
        'exchange': 'bybit',
        'listing_time': listing_time.isoformat(),
        'interval': '5m',
        'data_points': len(klines_data),
        'price_history': []
    }
    
    for i, kline in enumerate(klines_data):
        # Bybit kline format: [startTime, openPrice, highPrice, lowPrice, closePrice, volume, turnover]
        price_point = {
            'time_index': i,  # Index from 0 (listing time)
            'timestamp': datetime.utcfromtimestamp(int(kline[0]) / 1000).replace(tzinfo=timezone.utc).isoformat(),
            'open_price': float(kline[1]),
            'high_price': float(kline[2]),
            'low_price': float(kline[3]),
            'close_price': float(kline[4]),
            'volume': float(kline[5]),
            'minutes_from_listing': i * 5  # 5-minute intervals
        }
        price_data['price_history'].append(price_point)
    
    # Save to JSON file
    filename = f"{symbol}.json"
    filepath = os.path.join(PRICE_DATA_FOLDER, filename)
    
    with open(filepath, 'w') as f:
        json.dump(price_data, f, indent=2)
    
    print(f"  Saved price data to: {filepath}")

def analyze_prices_bybit(symbol, message_timestamp):
    """Analyze price data for a coin from its listing time using Bybit API"""
    
    # Parse the message timestamp to get the listing announcement time
    try:
        # Handle different timestamp formats
        if isinstance(message_timestamp, str):
            if '+' in message_timestamp:
                listing_time = datetime.fromisoformat(message_timestamp.replace('Z', '+00:00'))
            else:
                listing_time = datetime.fromisoformat(message_timestamp).replace(tzinfo=timezone.utc)
        else:
            listing_time = datetime.fromisoformat(str(message_timestamp)).replace(tzinfo=timezone.utc)
    except Exception as e:
        print(f"  Error parsing timestamp {message_timestamp}: {e}")
        return {'error': f'invalid timestamp format: {message_timestamp}'}
    
    print(f"  Listing announced at: {listing_time.isoformat()}")
    
    # Get the price at the listing announcement time (or closest available)
    # We'll get klines starting from the listing time
    klines_data = get_klines_for_duration_bybit(symbol, listing_time, hours=48, interval='5')
    
    if not klines_data or len(klines_data) < 2:
        return {
            'listing_announcement_time': listing_time.isoformat(),
            'opening_price': None,
            'closing_price': None,
            'highest_price': None,
            'lowest_price': None,
            'highest_gain_percent': None,
            'lowest_gain_percent': None,
            'highest_price_time_min': None,
            'lowest_price_time_min': None,
            'data_points_count': len(klines_data) if klines_data else 0,
            'error': f'insufficient data - only {len(klines_data) if klines_data else 0} data points available'
        }
    
    # Get the opening price (first available price after listing announcement)
    opening_price = float(klines_data[0][1])  # Open price of first kline
    actual_start_time = datetime.utcfromtimestamp(int(klines_data[0][0]) / 1000).replace(tzinfo=timezone.utc)
    
    print(f"  First available price at: {actual_start_time.isoformat()}")
    print(f"  Opening price: {opening_price}")
    
    # Save the price data to JSON file
    save_price_data_bybit(symbol, klines_data, listing_time)
    
    # Calculate statistics from 48 hours of data
    closing_price = float(klines_data[-1][4])  # Close price of last kline
    
    # Get high and low prices for each kline
    high_prices = [float(k[2]) for k in klines_data]
    low_prices = [float(k[3]) for k in klines_data]
    
    highest_price = max(high_prices)
    lowest_price = min(low_prices)
    
    # Find the time index when highest and lowest prices occurred
    highest_time_idx = high_prices.index(highest_price)
    lowest_time_idx = low_prices.index(lowest_price)
    
    # Convert to minutes from listing announcement (5-minute intervals)
    highest_time_minutes = highest_time_idx * 5
    lowest_time_minutes = lowest_time_idx * 5
    
    # Calculate percentage gains from opening price
    highest_gain = (highest_price - opening_price) / opening_price * 100
    lowest_gain = (lowest_price - opening_price) / opening_price * 100
    
    return {
        'exchange': 'bybit',
        'listing_announcement_time': listing_time.isoformat(),
        'actual_start_time': actual_start_time.isoformat(),
        'opening_price': opening_price,
        'closing_price': closing_price,
        'highest_price': highest_price,
        'lowest_price': lowest_price,
        'highest_gain_percent': round(highest_gain, 2),
        'lowest_gain_percent': round(lowest_gain, 2),
        'highest_price_time_min': highest_time_minutes,
        'lowest_price_time_min': lowest_time_minutes,
        'data_points_count': len(klines_data),
        'analysis_period': '48 hours from listing announcement (5m intervals)',
        'price_data_saved': f"{symbol}.json"
    }

def main():
    # Check if input file exists
    if not os.path.exists(INPUT_JSON):
        print(f"Error: Input file not found: {INPUT_JSON}")
        print("Please make sure the file exists before running this script.")
        return
    
    with open(INPUT_JSON, 'r') as f:
        data = json.load(f)

    results = []
    total = len(data)
    
    print(f"Price data will be saved to: {PRICE_DATA_FOLDER}")
    print(f"Starting analysis of {total} coins using Bybit API...\n")
    
    for idx, entry in enumerate(data, 1):
        symbol = entry['symbol']
        timestamp = entry['timestamp']
        
        result = {
            'symbol': symbol,
            'timestamp': timestamp,
            'coin_name': entry['coin_name'],
            'message': entry['message']
        }
        
        print(f"Processing {idx}/{total}: {symbol} (remaining: {total-idx})")
        
        # Check if symbol is currently listed on Bybit futures
        if symbol not in futures_symbols:
            result['error'] = 'not currently listed on Bybit futures'
            print(f"  {symbol}: Not currently listed on Bybit futures")
        else:
            print(f"  {symbol}: Currently listed, fetching historical data...")
            price_data = analyze_prices_bybit(symbol, timestamp)
            
            if 'error' in price_data:
                result['error'] = price_data['error']
                print(f"  Error: {price_data['error']}")
            else:
                result.update(price_data)
                print(f"  Success: Analyzed {price_data['data_points_count']} data points (5m intervals)")
                print(f"  Highest gain: {price_data['highest_gain_percent']}% at {price_data['highest_price_time_min']} minutes")
                print(f"  Lowest gain: {price_data['lowest_gain_percent']}% at {price_data['lowest_price_time_min']} minutes")
        
        results.append(result)
        time.sleep(0.2)  # Rate limiting
        print()  # Empty line for readability

    # Save results to CSV
    df = pd.DataFrame(results)
    df.to_csv(OUTPUT_CSV, index=False)
    print(f"Analysis complete! Results saved to {OUTPUT_CSV}")
    
    # Print summary
    successful_analyses = len([r for r in results if 'error' not in r])
    print(f"Successfully analyzed: {successful_analyses}/{total} coins")
    print(f"Price data files saved in: {PRICE_DATA_FOLDER}")
    
    # List saved files
    if os.path.exists(PRICE_DATA_FOLDER):
        saved_files = [f for f in os.listdir(PRICE_DATA_FOLDER) if f.endswith('.json')]
        print(f"Total price data files created: {len(saved_files)}")

if __name__ == '__main__':
    main() 