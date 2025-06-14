import requests
import json

def get_binance_futures_symbols():
    """
    Fetch all symbols listed on Binance USDT-margined futures using Binance API.
    Returns:
        List[str]: List of symbol strings (e.g., ['BTCUSDT', 'ETHUSDT', ...])
    """
    url = 'https://fapi.binance.com/fapi/v1/exchangeInfo'
    response = requests.get(url)
    response.raise_for_status()
    data = response.json()
    symbols = [s['symbol'] for s in data['symbols'] if s['contractType'] == 'PERPETUAL']
    return symbols

if __name__ == "__main__":
    symbols = get_binance_futures_symbols()
    print("Binance USDT-margined futures symbols:")
    print(symbols)
    with open('binance_futures_symbols.json', 'w') as f:
        json.dump(symbols, f, indent=2) 