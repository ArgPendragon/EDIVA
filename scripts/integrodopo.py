import os
import json

# -------------------------------
# Configuration
# -------------------------------
# Folder containing the split JSON chunk files.
INPUT_FOLDER = "D:/EDIVA/cardonaproject/tradotto/1God/"

def load_json(filepath):
    """Load JSON data from a file."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading JSON from {filepath}: {e}")
        return None

def merge_parts(base_filename, dir_path):
    """
    For a given base filename (without the trailing 'a' or 'b' and extension),
    look for files named base + 'a.json' and base + 'b.json',
    merge their JSON content (assumed to be lists), and write the merged
    output to base + '.json' in the same directory.
    
    Before overwriting an existing merged file, the script checks for integrity:
      - If the existing file is identical to the new merge, it is left intact.
      - If there's a mismatch, the new merge is saved as base + '_merged_new.json'
        and the conflict is logged.
    
    In any case, after merging, the script deletes the 'a' and 'b' part files.
    """
    file_a = os.path.join(dir_path, f"{base_filename}a.json")
    file_b = os.path.join(dir_path, f"{base_filename}b.json")
    merged_file = os.path.join(dir_path, f"{base_filename}.json")

    if not os.path.exists(file_a) or not os.path.exists(file_b):
        print(f"Missing part for base {base_filename}: cannot merge.")
        return

    data_a = load_json(file_a)
    data_b = load_json(file_b)

    if data_a is None or data_b is None:
        print(f"Error loading parts for base {base_filename}: skipping merge.")
        return

    # Both parts should be lists; merge by concatenation.
    if not isinstance(data_a, list) or not isinstance(data_b, list):
        print(f"Data in parts for base {base_filename} is not a list: skipping merge.")
        return

    merged_data = data_a + data_b

    # Check if a merged file already exists.
    if os.path.exists(merged_file):
        existing_data = load_json(merged_file)
        if existing_data == merged_data:
            print(f"Merged file '{os.path.basename(merged_file)}' already exists and is identical. Keeping original.")
        else:
            # The existing file is different: save the new merged data in a new file.
            new_merged_file = os.path.join(dir_path, f"{base_filename}_merged_new.json")
            try:
                with open(new_merged_file, "w", encoding="utf-8") as f:
                    json.dump(merged_data, f, indent=4, ensure_ascii=False)
                print(f"Conflict for base '{base_filename}':")
                print(f"  Existing merged file '{os.path.basename(merged_file)}' differs from new merge.")
                print(f"  New merged file saved as '{os.path.basename(new_merged_file)}'.")
            except Exception as e:
                print(f"Error writing new merged file '{new_merged_file}': {e}")
    else:
        try:
            with open(merged_file, "w", encoding="utf-8") as f:
                json.dump(merged_data, f, indent=4, ensure_ascii=False)
            print(f"Merged parts into '{os.path.basename(merged_file)}' with {len(merged_data)} pages.")
        except Exception as e:
            print(f"Error writing merged file '{merged_file}': {e}")
            return

    # In any case, delete the a and b part files.
    try:
        os.remove(file_a)
        os.remove(file_b)
        print(f"Deleted part files: '{os.path.basename(file_a)}' and '{os.path.basename(file_b)}'.")
    except Exception as e:
        print(f"Error deleting part files for base '{base_filename}': {e}")

def main():
    # List all files in the INPUT_FOLDER that end with 'a.json'
    files = [f for f in os.listdir(INPUT_FOLDER) if f.endswith("a.json")]
    # For each file ending in 'a.json', determine the base and try to merge with the corresponding 'b.json'
    for file_a in files:
        if not file_a.endswith("a.json"):
            continue
        base = file_a[:-6]  # Remove the trailing 'a.json'
        merge_parts(base, INPUT_FOLDER)

if __name__ == "__main__":
    main()
