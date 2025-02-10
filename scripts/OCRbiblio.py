import cv2
import pytesseract
import os
import json
import logging
import numpy as np
import argparse
import re
from pathlib import Path
from PIL import Image

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def run_ocr_on_image(pil_img, config='--oem 3 --psm 6 -c preserve_interword_spaces=1', lang='eng'):
    """Run OCR on a PIL image and return the extracted text."""
    try:
        text = pytesseract.image_to_string(pil_img, config=config, lang=lang).strip()
        return text
    except Exception as e:
        logging.error(f"OCR error: {e}")
        return ""

def remove_page_numbers_from_biblio(text):
    """
    Remove any leading page numbers from bibliography entries.
    Assumes each entry starts with a number optionally followed by punctuation (e.g. '.' or '-')
    and whitespace.
    """
    cleaned_lines = []
    for line in text.splitlines():
        cleaned_line = re.sub(r'^\s*\d+[\.\-]?\s*', '', line)
        cleaned_lines.append(cleaned_line)
    return "\n".join(cleaned_lines)

def digit_line_count(text):
    """
    Count how many lines in the text start with a digit.
    """
    count = 0
    for line in text.splitlines():
        if re.match(r'^\s*\d+', line):
            count += 1
    return count

def sequential_number_score(text):
    """
    Calculate a score based on how many lines start with consecutive numbers beginning with 1.
    """
    lines = text.splitlines()
    score = 0
    expected = 1
    for line in lines:
        m = re.match(r'^\s*(\d+)', line)
        if m:
            num = int(m.group(1))
            if num == expected:
                score += 1
                expected += 1
            else:
                # stop counting if the sequence is broken
                break
    return score

def process_bibliography_page(image_path, page_info):
    """
    Process the bibliography area of a single page:
      - Crop the area below the provided separator_y.
      - Run three OCR passes with different configurations.
      - Choose the best result using a composite heuristic:
            (sequential numbering score, digit line count, overall text length)
      - Remove any spurious leading page numbers.
      - Return the OCR text.
    """
    try:
        original_image = Image.open(image_path)
    except Exception as e:
        logging.error(f"Error opening image {image_path}: {e}")
        return ""
    
    separator_y = page_info.get("separator_y")
    if separator_y is None:
        return ""
    
    try:
        separator_y = int(separator_y)
        width, height = original_image.size
        if not (0 < separator_y < height):
            logging.warning(f"separator_y value {separator_y} is out of bounds for image height {height}.")
            return ""
        # Crop bibliography region (everything below separator_y)
        biblio_region = original_image.crop((0, separator_y, width, height))
    except Exception as e:
        logging.error(f"Error processing bibliography region: {e}")
        return ""
    
    # Run OCR with three different parameter sets.
    ocr_configs = [
        '--oem 3 --psm 6 -c preserve_interword_spaces=1',
        '--oem 3 --psm 4 -c preserve_interword_spaces=1',
        '--oem 1 --psm 6 -c preserve_interword_spaces=1'
    ]
    
    ocr_results = []
    for config in ocr_configs:
        text = run_ocr_on_image(biblio_region, config=config)
        ocr_results.append(text)
    
    # Choose the best OCR result based on our composite heuristic.
    best_text = max(ocr_results, key=lambda x: (sequential_number_score(x), digit_line_count(x), len(x)))
    
    # Remove any residual leading page numbers.
    cleaned_text = remove_page_numbers_from_biblio(best_text)
    # Collapse extra spaces/newlines.
    cleaned_text = "\n".join([line.strip() for line in cleaned_text.splitlines() if line.strip()])
    return cleaned_text

def parse_biblio_entries(text):
    """
    Parse the OCR output text into a list of bibliography entries.
    Each nonempty line is assumed to be one entry.
    """
    entries = [line.strip() for line in text.splitlines() if line.strip()]
    return entries

def check_bibliography_entries(entries, page_info, reset_points):
    """
    Check that the bibliography numbering appears correct.
      - If the page is a reset point (i.e. its page number is in reset_points),
        the first entry should start with "1.".
      - In any case, check that the entries are sequential.
    Logs warnings if inconsistencies are detected.
    """
    page_num = page_info.get("page_number")
    try:
        page_num_int = int(page_num)
    except Exception:
        page_num_int = None

    # If this page should start a new bibliography sequence, check that the first entry starts with 1.
    if page_num_int and page_num_int in reset_points:
        if entries:
            m = re.match(r'^(\d+)', entries[0])
            if m:
                first_number = int(m.group(1))
                if first_number != 1:
                    logging.warning(f"Page {page_num_int}: Expected bibliography to reset to 1 but first entry starts with {first_number}.")
            else:
                logging.warning(f"Page {page_num_int}: Expected a numeric start in bibliography but got: {entries[0]}")
    
    # Check overall sequential numbering.
    expected = 1
    for entry in entries:
        m = re.match(r'^(\d+)', entry)
        if m:
            number = int(m.group(1))
            if number != expected:
                logging.warning(f"Page {page_num_int}: Expected entry number {expected} but found {number} in: {entry}")
                expected = number + 1
            else:
                expected += 1
        else:
            logging.warning(f"Page {page_num_int}: Entry does not start with a number: {entry}")

def extract_reset_points(book_index):
    """
    Look through the index pages in the original book index to extract bibliography reset points.
    Assumes that in index pages (page_type == "index") the parsed 'index' field contains chapters
    with entries whose 'page_number' marks the bibliography reset for that chapter.
    Returns a set of page numbers (as integers) where the bibliography numbering should reset.
    """
    reset_points = set()
    for page in book_index:
        if page.get("page_type") == "index" and "index" in page:
            for chapter in page["index"]:
                for entry in chapter.get("entries", []):
                    try:
                        pnum = int(entry.get("page_number", "0"))
                        reset_points.add(pnum)
                    except Exception:
                        continue
    return reset_points

def process_bibliography(input_dir):
    """
    Process all pages with a bibliography region in the provided bookindex.
      - For each page with a defined separator_y, process the bibliography area with multi‑scan OCR.
      - Parse the OCR result into a list of bibliography entries.
      - Check the numbering using reset points extracted from index pages.
      - Build a new index structure (without altering the original bookindex.json).
      - Save the new data into bookindexbiblio.json.
    Returns both the original and new book indexes.
    """
    script_dir = Path(input_dir)
    input_file = script_dir / "bookindex.json"
    output_file = script_dir / "bookindexbiblio.json"

    if not input_file.exists():
        logging.error("ERROR: bookindex.json not found!")
        return None

    try:
        with open(input_file, "r", encoding="utf-8") as f:
            original_book_index = json.load(f)
    except Exception as e:
        logging.error(f"ERROR loading bookindex.json: {e}")
        return None

    # Extract reset page numbers from index pages.
    reset_points = extract_reset_points(original_book_index)
    logging.info(f"Detected bibliography reset points (from index pages): {sorted(reset_points)}")

    new_book_index = []  # New structure with updated bibliography field (as a single formatted string)
    total_pages = len(original_book_index)
    logging.info(f"Processing bibliography for {total_pages} page(s).")
    
    for idx, page_info in enumerate(original_book_index, start=1):
        new_page_info = dict(page_info)  # Copy metadata
        image_file = page_info.get("file", "")
        image_path = script_dir / image_file
        if not image_path.exists():
            logging.warning(f"Missing image file {image_file}, skipping page {idx}.")
            new_page_info["bibliography"] = ""
        elif page_info.get("separator_y") is not None:
            logging.info(f"Processing bibliography for {image_file} ({idx}/{total_pages})")
            ocr_text = process_bibliography_page(image_path, page_info)
            entries = parse_biblio_entries(ocr_text)
            # Check numbering consistency against reset points.
            check_bibliography_entries(entries, page_info, reset_points)
            # Format as a single string (one entry per line)
            formatted_biblio = "\n".join(entries)
            new_page_info["bibliography"] = formatted_biblio
        else:
            new_page_info["bibliography"] = ""
        new_book_index.append(new_page_info)
    
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(new_book_index, f, indent=4, ensure_ascii=False)
        logging.info(f"Saved new bibliography JSON to {output_file}")
    except Exception as e:
        logging.error(f"Error writing to {output_file}: {e}")
    
    return original_book_index, new_book_index

def compare_bibliography(original_index, new_index):
    """
    Compare the bibliography fields from the original and new book indexes.
    For each page, log:
      - The number of bibliography entries (as determined by splitting the string by newline).
      - The first entry (which should indicate a reset if appropriate).
    """
    compared_pages = 0
    for i, (orig_page, new_page) in enumerate(zip(original_index, new_index)):
        orig_biblio = orig_page.get("bibliography", "")
        orig_entries = parse_biblio_entries(orig_biblio)
        new_biblio = new_page.get("bibliography", "")
        new_entries = parse_biblio_entries(new_biblio)
        if not (orig_entries or new_entries):
            continue
        compared_pages += 1
        logging.info(f"Page {i+1} comparison:")
        logging.info(f"  Original: {len(orig_entries)} entries. First: {orig_entries[0] if orig_entries else 'N/A'}")
        logging.info(f"  New     : {len(new_entries)} entries. First: {new_entries[0] if new_entries else 'N/A'}")
    logging.info(f"Compared bibliography on {compared_pages} page(s).")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Bibliography OCR Script: Multi-scan OCR with formatted single-string bibliography output and index‑based numbering checks."
    )
    parser.add_argument("--input", default=".", help="Directory containing images and bookindex.json")
    args = parser.parse_args()
    
    result = process_bibliography(args.input)
    if result is not None:
        original_index, new_index = result
        compare_bibliography(original_index, new_index)
