import os
import re
import json
import argparse
from pathlib import Path

def merge_json_files(input_folder):
    input_path = Path(input_folder)
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
        files.sort()  # Sort by numeric value
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

        output_file = input_path / f"{prefix}merged.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(merged_data, f, indent=4)
        print(f"Merged {len(files)} files into {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Merge JSON files based on numeric order.")
    parser.add_argument("input_folder", type=str, help="Folder containing JSON files")
    args = parser.parse_args()

    merge_json_files(args.input_folder)
