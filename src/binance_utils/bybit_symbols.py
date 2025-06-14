import requests
import json

RESULT_DIR = '/Users/krishnayadav/Documents/test_projects/telegram_listing/binance_data'


def get_bybit_futures_symbols():
    """
    Fetch all symbols listed on Bybit USDT perpetual futures using Bybit API.
    Returns:
        List[str]: List of symbol strings (e.g., ['BTCUSDT', 'ETHUSDT', ...])
    """
    url = 'https://api.bybit.com/v5/market/instruments-info'
    params = {
        'category': 'linear'  # linear = USDT perpetual futures
    }
    
    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()
    
    # Extract symbols from the response
    symbols = []
    if data['retCode'] == 0:  # Success response code for Bybit
        for instrument in data['result']['list']:
            if instrument['status'] == 'Trading':  # Only active trading pairs
                symbols.append(instrument['symbol'])
    
    return symbols

if __name__ == "__main__":
    symbols = get_bybit_futures_symbols()
    print("Bybit USDT perpetual futures symbols:")
    print(f"Total symbols found: {len(symbols)}")
    print(symbols[:10])  # Print first 10 symbols as preview
    
    # Save to JSON file
    with open(RESULT_DIR + '/bybit_futures_symbols.json', 'w') as f:
        json.dump(symbols, f, indent=2)
    
    print(f"\nAll symbols saved to 'bybit_futures_symbols.json'") 