import json
from tqdm import tqdm
from openai import OpenAI
import os
from dotenv import load_dotenv
load_dotenv()

# Set your OpenAI API key (you can also use environment variable)
print(os.getenv("OPENAI_API_KEY"))
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


BINANCE_FUTURE_JSON = '/Users/krishnayadav/Documents/test_projects/telegram_trade/binance_future.json'
BINANCE_SYMBOLS_JSON = '/Users/krishnayadav/Documents/test_projects/telegram_trade/src/binance_futures_symbols.json'

# Load messages
with open(BINANCE_FUTURE_JSON, 'r') as f:
    messages = json.load(f)

# Load Binance futures symbols
with open(BINANCE_SYMBOLS_JSON, 'r') as f:
    symbols = json.load(f)

def ask_gpt_for_coin(message, symbols):
    prompt = (
        f"Given the following Binance futures symbols: {symbols}\n"
        f"and the following message: '{message}',\n"
        "which symbol(s) from the list are mentioned or implied in the message? "
        "Return a list of matching symbols. If none, return an empty list."
    )

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=100,
        temperature=0
    )
    # Extract the list from the response
    content = response.choices[0].message.content
    try:
        # Try to parse as JSON list
        result = json.loads(content)
        if isinstance(result, list):
            return result
    except Exception:
        # Fallback: try to extract symbols from text
        return [s for s in symbols if s in content]
    return []

# Iterate and update messages with coin_name using a progress bar
for msg in tqdm(messages, desc="Matching coins with GPT"):
    coin_names = ask_gpt_for_coin(msg['message'], symbols)
    # Store as dict: {symbol: True, ...}
    msg['coin_name'] = {symbol: True for symbol in coin_names}
    if coin_names:
        print(f"For message: '{msg['message']}'\nMatched coin name(s): {', '.join(coin_names)}\n")
    else:
        print(f"For message: '{msg['message']}'\nNo coin name matched.\n")

# Save the updated messages back to binance.json
with open(BINANCE_FUTURE_JSON, 'w') as f:
    json.dump(messages, f, ensure_ascii=False, indent=2)

print("Matching complete. Updated binance.json with coin names.") 