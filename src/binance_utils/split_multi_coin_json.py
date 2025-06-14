import json

INPUT_JSON = '/Users/krishnayadav/Documents/test_projects/telegram_trade/binance_future.json'
OUTPUT_JSON = '/Users/krishnayadav/Documents/test_projects/telegram_trade/binance_future_split.json'

with open(INPUT_JSON, 'r') as f:
    data = json.load(f)

split_data = []
for entry in data:
    coin_names = entry.get('coin_name', {})
    if len(coin_names) > 1:
        for coin in coin_names:
            new_entry = entry.copy()
            new_entry['coin_name'] = {coin: True}
            split_data.append(new_entry)
    else:
        split_data.append(entry)

with open(OUTPUT_JSON, 'w') as f:
    json.dump(split_data, f, ensure_ascii=False, indent=2)

print(f"Done! Split data saved to {OUTPUT_JSON}") 