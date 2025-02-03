import os
import json
import argparse
import logging

# Configure logging (console only)
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

def split_json(data):
    """Splits any JSON object into two equal parts while keeping the structure"""
    if isinstance(data, list):  # If it's a list, split items
        mid = len(data) // 2
        return data[:mid], data[mid:]
    elif isinstance(data, dict):  # If it's a dict, split by keys
        keys = list(data.keys())
        mid = len(keys) // 2
        first_half = {k: data[k] for k in keys[:mid]}
        second_half = {k: data[k] for k in keys[mid:]}
        return first_half, second_half
    else:
        return data, None  # If not a dict/list, return as-is (shouldn't happen)

def process_chunks(input_dir, output_dir, max_size):
    """Scan directory and split large JSON files if needed"""
    if not os.path.exists(input_dir):
        logging.error(f"Input directory '{input_dir}' does not exist.")
        return

    os.makedirs(output_dir, exist_ok=True)  # Ensure output directory exists

    files = sorted(os.listdir(input_dir))  # Maintain order
    index_counter = 1  # Start indexing at 1

    for filename in files:
        if not filename.endswith(".json"):
            continue  # Skip non-JSON files

        file_path = os.path.join(input_dir, filename)

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)  # Load JSON

            content = json.dumps(data)  # Convert to string for size check

            if len(content) <= max_size:
                # If within limits, just rename it with the next available index
                new_filename = f"chunk_{str(index_counter).zfill(3)}.json"
                output_path = os.path.join(output_dir, new_filename)
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                logging.info(f"Copied {filename} as {new_filename} (size within limit).")
                index_counter += 1  # Move to next index
            else:
                # Split into two parts while keeping original structure
                part1, part2 = split_json(data)

                if part2 is None:
                    logging.warning(f"Skipping {filename}: Unable to split (unsupported format).")
                    continue

                new_filename_part1 = f"chunk_{str(index_counter).zfill(3)}.json"
                new_filename_part2 = f"chunk_{str(index_counter + 1).zfill(3)}.json"
                index_counter += 2  # Move index by 2 since we're splitting

                with open(os.path.join(output_dir, new_filename_part1), "w", encoding="utf-8") as f:
                    json.dump(part1, f, indent=2)
                with open(os.path.join(output_dir, new_filename_part2), "w", encoding="utf-8") as f:
                    json.dump(part2, f, indent=2)

                logging.info(f"Split {filename} into {new_filename_part1} and {new_filename_part2}.")

        except json.JSONDecodeError as e:
            logging.error(f"JSON error in {filename}: {e}")
        except OSError as e:
            logging.error(f"File error with {filename}: {e}")
        except Exception as e:
            logging.error(f"Unexpected error processing {filename}: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Split large JSON files into smaller parts.")
    parser.add_argument("-i", "--input", default="chunks", help="Input directory containing JSON files.")
    parser.add_argument("-o", "--output", help="Output directory for processed files.")
    parser.add_argument("-s", "--size", type=int, default=30000, help="Maximum character size before splitting.")

    args = parser.parse_args()

    # Default output directory behavior:
    # - If `-o` is provided, use it.
    # - If not provided, default to `<input_folder>/cutchunks` for flexibility.
    default_output = os.path.join(args.input, "cutchunks")
    args.output = args.output or default_output

    logging.info(f"Processing files from {args.input} → Saving to {args.output}")

    os.makedirs(args.output, exist_ok=True)  # Ensure output directory exists
    process_chunks(args.input, args.output, args.size)

    logging.info("Processing complete.")
