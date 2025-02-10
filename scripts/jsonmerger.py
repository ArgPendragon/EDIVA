import os
import re
import json
import argparse
import unicodedata
from pathlib import Path

def clean_text(text: str) -> str:
    """
    Normalize the text using Unicode normalization (NFKC).
    This converts sequences like '\u201c' into their actual characters.
    """
    normalized = unicodedata.normalize("NFKC", text)
    return normalized

def recursively_clean(data):
    """
    Recursively process the JSON structure so that every string found
    is normalized using the clean_text function.
    """
    if isinstance(data, dict):
        return {key: recursively_clean(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [recursively_clean(item) for item in data]
    elif isinstance(data, str):
        return clean_text(data)
    else:
        return data

def merge_json_files(input_folder):
    input_path = Path(input_folder)
    # Filter JSON files that match the pattern (non-digits + 3 digits).json
    json_files = [f for f in input_path.glob("*.json") if re.search(r"(\D+)(\d{3})\.json$", f.name)]

    grouped_files = {}
    for file in json_files:
        match = re.match(r"(\D+)(\d{3})\.json$", file.name)
        if match:
            prefix, num = match.groups()
            if prefix not in grouped_files:
                grouped_files[prefix] = []
            grouped_files[prefix].append((int(num), file))

    for prefix, files in grouped_files.items():
        files.sort()  # Sort by the numeric value extracted from the filename.
        merged_data = []
        
        for _, file in files:
            with open(file, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                    if isinstance(data, list):
                        merged_data.extend(data)
                    else:
                        merged_data.append(data)
                except json.JSONDecodeError:
                    print(f"Skipping invalid JSON: {file}")

        # Clean the merged data to normalize Unicode characters.
        cleaned_data = recursively_clean(merged_data)
        
        output_file = input_path / f"{prefix}merged.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(cleaned_data, f, indent=4, ensure_ascii=False)
        print(f"Merged {len(files)} files into {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Merge JSON files based on numeric order and clean Unicode escapes.")
    parser.add_argument("input_folder", type=str, help="Folder containing JSON files")
    args = parser.parse_args()

    merge_json_files(args.input_folder)
