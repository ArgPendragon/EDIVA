import os
import json

# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------
# Input folder containing your chunk files (e.g., chunk001.json, chunk002.json, etc.)
INPUT_FOLDER = "D:/EDIVA/cardonaproject/processed/1God"

# The output folder where slimmed files with context will be stored.
SLIM_FOLDER = os.path.join(INPUT_FOLDER, "slim")
os.makedirs(SLIM_FOLDER, exist_ok=True)

# The allowed keys for each page object (do not include "bibliography" or "image_present")
ALLOWED_KEYS = ["page_type", "page_number", "content", "captions", "headers"]

# ------------------------------------------------------------------------------
# Helper Functions
# ------------------------------------------------------------------------------

def extract_slim_fields(data):
    """
    Given JSON data (a list or a single page object),
    return a list of page objects with only the allowed keys.
    """
    def slim_item(item):
        # Create a new dictionary containing only the allowed keys
        return { key: item.get(key) for key in ALLOWED_KEYS if key in item }
    
    if isinstance(data, list):
        return [slim_item(item) for item in data]
    elif isinstance(data, dict):
        return [slim_item(data)]
    else:
        return []

def extract_context_from_data(data, which="first", length=100):
    """
    Extracts a context snippet from the 'content' field in the data.
    
    Args:
        data (list or dict): The JSON data.
        which (str): "first" for the first 'length' characters,
                     "last" for the last 'length' characters.
        length (int): The number of characters to extract.
    
    Returns:
        str: The context snippet.
    """
    # Ensure data is a list.
    if isinstance(data, dict):
        data = [data]
    if not data:
        return ""
    
    # Choose the appropriate page (first for "first", last for "last")
    page = data[0] if which == "first" else data[-1]
    content = page.get("content", "")
    if which == "first":
        return content[:length].strip()
    else:
        return content[-length:].strip()

def process_file_with_context(current_file, previous_file, next_file):
    """
    Process a single file:
      - Loads the current file and extracts its slim page objects.
      - Loads the previous file (if available) and extracts the last 100 characters
        of its 'content' field.
      - Loads the next file (if available) and extracts the first 100 characters
        of its 'content' field.
      - Writes a new JSON object with keys "prev_context", "pages", and "next_context"
        to the SLIM_FOLDER using the same filename.
    """
    # Load current file.
    try:
        with open(current_file, "r", encoding="utf-8") as f:
            current_data = json.load(f)
    except Exception as e:
        print(f"Error reading {current_file}: {e}")
        return

    slim_pages = extract_slim_fields(current_data)
    
    # Extract previous context (last 100 characters).
    prev_context = ""
    if previous_file and os.path.exists(previous_file):
        try:
            with open(previous_file, "r", encoding="utf-8") as f:
                prev_data = json.load(f)
            prev_context = extract_context_from_data(prev_data, which="last", length=100)
        except Exception as e:
            print(f"Error reading previous file {previous_file}: {e}")
    
    # Extract next context (first 100 characters).
    next_context = ""
    if next_file and os.path.exists(next_file):
        try:
            with open(next_file, "r", encoding="utf-8") as f:
                next_data = json.load(f)
            next_context = extract_context_from_data(next_data, which="first", length=100)
        except Exception as e:
            print(f"Error reading next file {next_file}: {e}")
    
    output_data = {
        "prev_context": prev_context,
        "pages": slim_pages,
        "next_context": next_context
    }
    
    filename = os.path.basename(current_file)
    output_file = os.path.join(SLIM_FOLDER, filename)
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=4, ensure_ascii=False)
        print(f"Processed {filename} with context.")
    except Exception as e:
        print(f"Error writing {output_file}: {e}")

def main():
    # Get a sorted list of JSON files in the INPUT_FOLDER
    files = [f for f in os.listdir(INPUT_FOLDER) if f.endswith(".json")]
    files.sort()  # Assumes that lexicographic order matches the desired order.
    
    # Build full file paths.
    full_paths = [os.path.join(INPUT_FOLDER, f) for f in files]
    
    for i, current_file in enumerate(full_paths):
        previous_file = full_paths[i-1] if i > 0 else None
        next_file = full_paths[i+1] if i < len(full_paths) - 1 else None
        process_file_with_context(current_file, previous_file, next_file)
    
    print("All files processed with context.")

# ------------------------------------------------------------------------------
# Main Execution
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    main()
