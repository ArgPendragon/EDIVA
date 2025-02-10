import os
import json

# -------------------------------
# Configuration
# -------------------------------
# Folder containing the original JSON chunk files (before processing).
INPUT_FOLDER = "D:/EDIVA/cardonaproject/raw/1God/"
# Folder containing the processed JSON chunk files.
OUTPUT_FOLDER = "D:/EDIVA/cardonaproject/tradotto/1God"

# The minimal ratio between output and input content lengths (e.g., 0.9 = 90%).
CONTENT_LENGTH_THRESHOLD = 0.9

# -------------------------------
# Helper Functions
# -------------------------------
def load_json(filepath):
    """Load JSON data from a file."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise Exception(f"Error loading JSON from {filepath}: {e}")

def extract_pages(data):
    """
    Given JSON data that is either a list of pages or a dict containing a "pages" key,
    return the list of pages.
    """
    if isinstance(data, dict) and "pages" in data:
        return data["pages"]
    elif isinstance(data, list):
        return data
    else:
        return None

def check_file_integrity(input_file, output_file):
    """
    Compare a single input file and its corresponding output file.
    Returns a list of issues found (an empty list means the file passed all checks).
    """
    issues = []
    try:
        input_data = load_json(input_file)
    except Exception as e:
        issues.append(str(e))
        return issues

    try:
        output_data = load_json(output_file)
    except Exception as e:
        issues.append(str(e))
        return issues

    input_pages = extract_pages(input_data)
    output_pages = extract_pages(output_data)

    if input_pages is None:
        issues.append("Input file structure is not a list or dict with 'pages'.")
        return issues
    if output_pages is None:
        issues.append("Output file structure is not a list or dict with 'pages'.")
        return issues

    # 1. Check that the number of pages is the same.
    if len(input_pages) != len(output_pages):
        issues.append(f"Page count mismatch: input has {len(input_pages)} pages, output has {len(output_pages)} pages.")

    # 2. Compare page numbering.
    input_page_numbers = [page.get("page_number") for page in input_pages if isinstance(page, dict)]
    output_page_numbers = [page.get("page_number") for page in output_pages if isinstance(page, dict)]
    if input_page_numbers != output_page_numbers:
        issues.append(f"Page numbering mismatch:\n  Input page numbers: {input_page_numbers}\n  Output page numbers: {output_page_numbers}")

    # 3. Check that the "content" field length is similar.
    for idx, (in_page, out_page) in enumerate(zip(input_pages, output_pages)):
        if not (isinstance(in_page, dict) and isinstance(out_page, dict)):
            issues.append(f"Page {idx+1}: Page data is not a dictionary.")
            continue

        in_content = in_page.get("content", "")
        out_content = out_page.get("content", "")
        # Only check if there is content in the input.
        if isinstance(in_content, str) and len(in_content) > 0:
            ratio = len(out_content) / len(in_content)
            if ratio < CONTENT_LENGTH_THRESHOLD:
                issues.append(
                    f"File {os.path.basename(input_file)} page {in_page.get('page_number')}: "
                    f"content length ratio too low ({len(out_content)} vs {len(in_content)}; {ratio:.2f})."
                )
    return issues

def split_input_file(filepath):
    """
    Split the input file into two halves and write the halves as new files.
    The new files will be named with an added 'a' and 'b' before the .json extension.
    If the number of pages is even, split equally; if odd, the first file gets ceil(n/2) pages.
    """
    try:
        data = load_json(filepath)
    except Exception as e:
        print(f"Error loading {filepath} for splitting: {e}")
        return

    pages = extract_pages(data)
    if pages is None or not isinstance(pages, list):
        print(f"File {filepath} does not contain a valid list of pages. Skipping split.")
        return

    n = len(pages)
    if n == 0:
        print(f"File {filepath} contains no pages. Skipping split.")
        return

    # Compute split indices.
    if n % 2 == 0:
        split_index = n // 2
    else:
        split_index = (n + 1) // 2  # First half gets the extra page.

    first_half = pages[:split_index]
    second_half = pages[split_index:]

    # Prepare new filenames.
    base, ext = os.path.splitext(os.path.basename(filepath))
    file_a = os.path.join(os.path.dirname(filepath), f"{base}a{ext}")
    file_b = os.path.join(os.path.dirname(filepath), f"{base}b{ext}")

    # Write the two halves.
    try:
        with open(file_a, "w", encoding="utf-8") as f:
            json.dump(first_half, f, indent=4, ensure_ascii=False)
        with open(file_b, "w", encoding="utf-8") as f:
            json.dump(second_half, f, indent=4, ensure_ascii=False)
        print(f"Split {os.path.basename(filepath)} into:")
        print(f"  {os.path.basename(file_a)} with {len(first_half)} pages")
        print(f"  {os.path.basename(file_b)} with {len(second_half)} pages")
    except Exception as e:
        print(f"Error writing split files for {filepath}: {e}")

# -------------------------------
# Main Execution
# -------------------------------
def main():
    # Get sorted lists of JSON filenames from each folder.
    input_files = sorted([f for f in os.listdir(INPUT_FOLDER) if f.endswith(".json")])
    output_files = sorted([f for f in os.listdir(OUTPUT_FOLDER) if f.endswith(".json")])
    
    # Build the set of all filenames (if some files are missing from one folder, we flag that too).
    all_files = set(input_files) | set(output_files)
    overall_issues = {}

    for filename in sorted(all_files):
        file_issues = []
        input_path = os.path.join(INPUT_FOLDER, filename)
        output_path = os.path.join(OUTPUT_FOLDER, filename)
        if not os.path.exists(input_path):
            file_issues.append("Missing in input folder.")
        if not os.path.exists(output_path):
            file_issues.append("Missing in output folder.")
        # If file exists in both folders, perform the integrity checks.
        if os.path.exists(input_path) and os.path.exists(output_path):
            issues = check_file_integrity(input_path, output_path)
            file_issues.extend(issues)
        if file_issues:
            overall_issues[filename] = file_issues

    # Print the integrity issues.
    if overall_issues:
        print("Integrity issues found in the following files:")
        for filename, issues in overall_issues.items():
            print(f"\nFile: {filename}")
            for issue in issues:
                print(f"  - {issue}")
    else:
        print("All files passed integrity checks.")

    # Ask the user whether to split the problematic input files.
    if overall_issues:
        answer = input("\nDo you want to split the unmatched input files into two halves? (y/n): ")
        if answer.strip().lower().startswith("y"):
            print("\nSplitting the following input files:")
            for filename in sorted(overall_issues.keys()):
                input_path = os.path.join(INPUT_FOLDER, filename)
                if os.path.exists(input_path):
                    split_input_file(input_path)
                else:
                    print(f"Skipping {filename}: file not found in input folder.")
                    
            # Ask whether to delete the original files after splitting.
            delete_answer = input("\nDo you want to delete the original files after splitting them into a and b parts? (y/n): ")
            if delete_answer.strip().lower().startswith("y"):
                for filename in sorted(overall_issues.keys()):
                    input_path = os.path.join(INPUT_FOLDER, filename)
                    if os.path.exists(input_path):
                        try:
                            os.remove(input_path)
                            print(f"Deleted original file: {filename}")
                        except Exception as e:
                            print(f"Error deleting {filename}: {e}")
            else:
                print("Original files retained.")
                    
if __name__ == "__main__":
    main()
