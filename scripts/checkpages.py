import json
import argparse
from collections import Counter
from pathlib import Path

def extract_page_numbers(data):
    """ Recursively extract page numbers from a JSON structure """
    page_numbers = []

    if isinstance(data, list):  # JSON is a list
        for item in data:
            page_numbers.extend(extract_page_numbers(item))
    elif isinstance(data, dict):  # JSON is a dictionary
        if "page_number" in data and isinstance(data["page_number"], (int, float)):
            page_numbers.append(int(data["page_number"]))  # Convert to integer
        for value in data.values():  # Check nested structures
            page_numbers.extend(extract_page_numbers(value))
    
    return page_numbers

def analyze_json_pages(json_file):
    json_path = Path(json_file)

    if not json_path.exists():
        print(f"Error: File '{json_file}' not found.")
        return

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            page_numbers = extract_page_numbers(data)
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON format in '{json_file}'.")
        return

    # Remove None values if any exist
    page_numbers = [num for num in page_numbers if num is not None]

    if not page_numbers:
        print("No valid page numbers found.")
        return

    max_page = max(page_numbers) if page_numbers else 0  # Handle empty list safely
    page_count = Counter(page_numbers)

    missing_pages = sorted(set(range(1, max_page + 1)) - set(page_numbers))
    duplicate_pages = [page for page, count in page_count.items() if count > 1]

    print(f"Max page number found: {max_page}")
    print(f"Missing pages: {missing_pages if missing_pages else 'None'}")
    print(f"Duplicated pages: {duplicate_pages if duplicate_pages else 'None'}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze missing or duplicated page numbers in a JSON file.")
    parser.add_argument("json_file", nargs="?", default="chunk_merged.json", help="Path to the JSON file (default: chunk_merged.json)")
    args = parser.parse_args()

    analyze_json_pages(args.json_file)
