import json
import os

# ---------------------------
# SETTINGS
# ---------------------------
base_dir = r"D:\cardotest\ExtractedImages\1God\index_pages"
print(f"Base directory: {base_dir}")

# List of chunk files to process.
chunk_files = ["chunk_001.json", "chunk_002.json"]

# Define the desired page number range.
start_page = 5
end_page = 12  # inclusive

# Counter to assign new page numbers
current_page = start_page

# ---------------------------
# PROCESS EACH CHUNK FILE
# ---------------------------
for chunk in chunk_files:
    file_path = os.path.join(base_dir, chunk)
    print(f"Looking for file: {file_path}")
    if not os.path.isfile(file_path):
        print(f"File not found: {file_path}")
        continue

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            json_content = json.load(f)
    except Exception as err:
        print(f"Error reading {file_path}: {err}")
        continue

    if "data" not in json_content:
        print(f"File {file_path} does not contain a 'data' key; skipping.")
        continue

    # Iterate over each element in the data array.
    for item in json_content["data"]:
        # Stop if we've already assigned up to page 'end_page'
        if current_page > end_page:
            break

        # Optionally, add the new assigned page number to the item.
        # (You can change the key name if desired.)
        item["assigned_page_number"] = current_page

        # Determine output filename.
        output_filename = os.path.join(base_dir, f"Image_{current_page}.json")
        try:
            with open(output_filename, "w", encoding="utf-8") as outfile:
                json.dump(item, outfile, ensure_ascii=False, indent=4)
            print(f"Wrote page {current_page} to {output_filename}")
        except Exception as err:
            print(f"Error writing {output_filename}: {err}")

        current_page += 1

    # Stop processing further if we've reached the desired page count.
    if current_page > end_page:
        break

if current_page <= end_page:
    print(f"Warning: Fewer than {end_page - start_page + 1} pages were found. Last assigned page: {current_page - 1}")
else:
    print("Finished processing pages 5 through 12.")
