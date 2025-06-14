import json
import re

INPUT_JSON = '/Users/krishnayadav/Documents/test_projects/telegram_listing/binance_data/bybit_futures.json'
OUTPUT_JSON = '/Users/krishnayadav/Documents/test_projects/telegram_listing/binance_data/bybit_futures_coin_symbols.json'

with open(INPUT_JSON, 'r') as f:
    data = json.load(f)

results = []
for entry in data:
    message = entry.get('message', '')
    timestamp = entry.get('timestamp', '')
    # Find all $COIN patterns (letters, numbers, underscores)
    coins = re.findall(r'\$([A-Za-z0-9_]+)', message)
    for coin in coins:
        results.append({
            'coin_name': coin.upper(),
            'symbol': f'{coin.upper()}USDT',
            'timestamp': timestamp,
            'message': message
        })

with open(OUTPUT_JSON, 'w') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"Done! Extracted coin symbols saved to {OUTPUT_JSON}") 