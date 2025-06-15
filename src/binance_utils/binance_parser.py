import json
import re
from typing import List, Dict
import pandas as pd
import math

def parse_binance_messages(messages: List[Dict], output_file: str = 'binance.json'):
    """
    Tokenize each message, check for 'binance' and 'future' tokens (case-insensitive),
    and store the timestamp and whole message to a JSON file if both tokens are present.
    Args:
        messages (List[Dict]): List of messages, each with at least 'date' and 'message' keys.
        output_file (str): Output JSON file name (default: 'binance.json').
    """
    results = []
    for msg in messages:
        text = msg.get('message', '')
        print(text)
        if not isinstance(text, str):
            if text is None or (isinstance(text, float) and math.isnan(text)):
                text = ''
            else:
                text = str(text)
        tokens = re.findall(r'\w+', text.lower())
        print(tokens)
        if 'binance' in tokens and 'alpha' in tokens:
            results.append({
                'timestamp': str(msg.get('date', '')),
                'message': text
            })
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    # Load messages from CSV file
    df = pd.read_csv('/Users/krishnayadav/Documents/test_projects/telegram_trade/telegram_messages_2024-06-10_to_2025-06-10.csv')
    messages = df.to_dict('records')
    parse_binance_messages(messages)
