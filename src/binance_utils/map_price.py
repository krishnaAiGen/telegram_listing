import json
import requests
import pandas as pd
from datetime import datetime, timezone, timedelta
import time
import os

INPUT_JSON = '/Users/krishnayadav/Documents/test_projects/telegram_listing/coin_symbols_from_message.json'
OUTPUT_CSV = '/Users/krishnayadav/Documents/test_projects/telegram_listing/coin_price_analysis.csv'
PRICE_DATA_FOLDER = '/Users/krishnayadav/Documents/test_projects/telegram_listing/coin_alpha_price'

# Create coin_price folder if it doesn't exist
os.makedirs(PRICE_DATA_FOLDER, exist_ok=True)

# Get valid futures symbols at the start
futures_info = requests.get('https://fapi.binance.com/fapi/v1/exchangeInfo').json()
futures_symbols = set(s['symbol'] for s in futures_info['symbols'])

def get_first_kline(symbol, interval='5m'):
    """Get the very first kline (when coin was listed)"""
    url = 'https://fapi.binance.com/fapi/v1/klines'
    params = {
        'symbol': symbol,
        'interval': interval,
        'limit': 1,
        'startTime': 0  # get from the very beginning
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        klines = response.json()
        if klines:
            return klines[0]
    return None

def get_klines_for_duration(symbol, start_time, hours=48, interval='5m'):
    """Get klines for specified duration from start_time in 5-minute intervals"""
    url = 'https://fapi.binance.com/fapi/v1/klines'
    end_time = start_time + timedelta(hours=hours)
    
    # Calculate how many klines we need (48 hours = 576 5-minute intervals)
    limit = (hours * 60) // 5  # 5-minute intervals
    
    params = {
        'symbol': symbol,
        'interval': interval,
        'startTime': int(start_time.timestamp() * 1000),
        'endTime': int(end_time.timestamp() * 1000),
        'limit': min(limit, 1500)  # Binance has a limit of 1500 klines per request
    }
    
    all_klines = []
    current_start = start_time
    
    while current_start < end_time:
        params['startTime'] = int(current_start.timestamp() * 1000)
        params['endTime'] = int(min(end_time, current_start + timedelta(hours=125)).timestamp() * 1000)  # ~125 hours chunks for 5m intervals
        
        response = requests.get(url, params=params)
        if response.status_code == 200:
            klines = response.json()
            if not klines:
                break
            all_klines.extend(klines)
            # Update current_start to the last kline's close time + 5 minutes
            last_kline_time = datetime.utcfromtimestamp(klines[-1][6] / 1000).replace(tzinfo=timezone.utc)
            current_start = last_kline_time + timedelta(minutes=5)
        else:
            break
        
        time.sleep(0.1)  # Small delay to avoid rate limits
    
    return all_klines

def save_price_data(symbol, klines_data, listing_time):
    """Save price data to JSON file"""
    if not klines_data:
        return
    
    # Prepare price data in a structured format
    price_data = {
        'symbol': symbol,
        'listing_time': listing_time.isoformat(),
        'interval': '5m',
        'data_points': len(klines_data),
        'price_history': []
    }
    
    for i, kline in enumerate(klines_data):
        price_point = {
            'time_index': i,  # Index from 0 (listing time)
            'timestamp': datetime.utcfromtimestamp(kline[0] / 1000).replace(tzinfo=timezone.utc).isoformat(),
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

def analyze_prices(symbol, message_timestamp):
    """Analyze price data for a coin from its listing time"""
    
    # First, get the very first kline (when coin was listed) in 5-minute intervals
    first_kline = get_first_kline(symbol, interval='5m')
    if not first_kline:
        return {'error': 'no historical data found - coin may not be listed'}
    
    # Extract listing time and opening price
    listing_time = datetime.utcfromtimestamp(first_kline[0] / 1000).replace(tzinfo=timezone.utc)
    opening_price = float(first_kline[1])  # Open price of the first kline
    
    print(f"  Coin listed at: {listing_time.isoformat()}")
    print(f"  Opening price: {opening_price}")
    
    # Get 48 hours of data from listing time in 5-minute intervals
    klines_48h = get_klines_for_duration(symbol, listing_time, hours=48, interval='5m')
    
    if not klines_48h or len(klines_48h) < 2:
        return {
            'opening_price': opening_price,
            'opening_price_time': listing_time.isoformat(),
            'closing_price': None,
            'highest_price': None,
            'lowest_price': None,
            'highest_gain_percent': None,
            'lowest_gain_percent': None,
            'highest_price_time_min': None,
            'lowest_price_time_min': None,
            'data_points_count': len(klines_48h) if klines_48h else 0,
            'error': 'insufficient data for 48h analysis'
        }
    
    # Save the price data to JSON file
    save_price_data(symbol, klines_48h, listing_time)
    
    # Calculate statistics from 48 hours of data
    closing_price = float(klines_48h[-1][4])  # Close price of last kline
    
    # Get high and low prices for each kline
    high_prices = [float(k[2]) for k in klines_48h]
    low_prices = [float(k[3]) for k in klines_48h]
    
    highest_price = max(high_prices)
    lowest_price = min(low_prices)
    
    # Find the time index when highest and lowest prices occurred
    highest_time_idx = high_prices.index(highest_price)
    lowest_time_idx = low_prices.index(lowest_price)
    
    # Convert to minutes from listing (5-minute intervals)
    highest_time_minutes = highest_time_idx * 5
    lowest_time_minutes = lowest_time_idx * 5
    
    # Calculate percentage gains from opening price
    highest_gain = (highest_price - opening_price) / opening_price * 100
    lowest_gain = (lowest_price - opening_price) / opening_price * 100
    
    return {
        'opening_price': opening_price,
        'opening_price_time': listing_time.isoformat(),
        'closing_price': closing_price,
        'highest_price': highest_price,
        'lowest_price': lowest_price,
        'highest_gain_percent': round(highest_gain, 2),
        'lowest_gain_percent': round(lowest_gain, 2),
        'highest_price_time_min': highest_time_minutes,
        'lowest_price_time_min': lowest_time_minutes,
        'data_points_count': len(klines_48h),
        'analysis_period': '48 hours from listing (5m intervals)',
        'price_data_saved': f"{symbol}.json"
    }

def main():
    with open(INPUT_JSON, 'r') as f:
        data = json.load(f)

    results = []
    total = len(data)
    
    print(f"Price data will be saved to: {PRICE_DATA_FOLDER}")
    print(f"Starting analysis of {total} coins...\n")
    
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
        
        # Check if symbol is currently listed on Binance futures
        if symbol not in futures_symbols:
            result['error'] = 'not currently listed on Binance futures'
            print(f"  {symbol}: Not currently listed on Binance futures")
        else:
            print(f"  {symbol}: Currently listed, fetching historical data...")
            price_data = analyze_prices(symbol, timestamp)
            
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
    saved_files = [f for f in os.listdir(PRICE_DATA_FOLDER) if f.endswith('.json')]
    print(f"Total price data files created: {len(saved_files)}")

if __name__ == '__main__':
    main()