import json
from datetime import datetime

def sort_messages_by_timestamp():
    """Sort messages in coin_symbols_from_message.json by timestamp"""
    
    # File paths
    input_file = '/Users/krishnayadav/Documents/test_projects/telegram_listing/binance_data/bybit_futures_coin_symbols.json'
    output_file = '/Users/krishnayadav/Documents/test_projects/telegram_listing/binance_data/bybit_futures_coin_symbols_sorted.json'
    try:
        # Load the JSON data
        print(f"Loading data from: {input_file}")
        with open(input_file, 'r') as f:
            data = json.load(f)
        
        print(f"Loaded {len(data)} messages")
        
        # Sort by timestamp
        print("Sorting messages by timestamp...")
        sorted_data = sorted(data, key=lambda x: x['timestamp'])
        
        # Save sorted data
        print(f"Saving sorted data to: {output_file}")
        with open(output_file, 'w') as f:
            json.dump(sorted_data, f, indent=2)
        
        print(f"Successfully sorted {len(sorted_data)} messages by timestamp")
        
        # Display first and last timestamps for verification
        if sorted_data:
            first_timestamp = sorted_data[0]['timestamp']
            last_timestamp = sorted_data[-1]['timestamp']
            
            print(f"\nTimestamp range:")
            print(f"  First message: {first_timestamp}")
            print(f"  Last message:  {last_timestamp}")
            
            # Convert to readable dates for verification
            try:
                first_date = datetime.fromtimestamp(int(first_timestamp))
                last_date = datetime.fromtimestamp(int(last_timestamp))
                print(f"\nReadable dates:")
                print(f"  First message: {first_date}")
                print(f"  Last message:  {last_date}")
            except:
                print("Note: Timestamps might not be in Unix format")
        
        print(f"\nSorted file saved successfully: {output_file}")
        
    except FileNotFoundError:
        print(f"Error: Input file not found: {input_file}")
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON format in input file: {e}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    sort_messages_by_timestamp() 