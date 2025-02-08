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
    Remove leading page numbers from bibliography entries.
    Assumes each entry is on a separate line and begins with a number,
    optionally followed by punctuation (like . or -) and spaces.
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
                # break on first non-sequential number
                break
    return score

def process_bibliography_page(image_path, page_info):
    """
    Process the bibliography area of a single page:
      - Crop the area below separator_y.
      - Run three OCR passes with different configurations.
      - Choose the best result based on a combined heuristic:
            (sequential score, digit line count, text length)
      - Remove leading page numbers from the result.
      - Return the cleaned bibliography text.
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
        # Crop the bibliography region (everything below separator_y)
        biblio_region = original_image.crop((0, separator_y, width, height))
    except Exception as e:
        logging.error(f"Error processing bibliography region: {e}")
        return ""
    
    # Define three OCR configurations (these can be tweaked further)
    ocr_configs = [
        '--oem 3 --psm 6 -c preserve_interword_spaces=1',
        '--oem 3 --psm 4 -c preserve_interword_spaces=1',
        '--oem 1 --psm 6 -c preserve_interword_spaces=1'
    ]
    
    ocr_results = []
    for config in ocr_configs:
        text = run_ocr_on_image(biblio_region, config=config)
        ocr_results.append(text)
    
    # Use a composite heuristic: primary factor is sequential numbering,
    # then digit-line count, and finally overall text length.
    best_text = max(ocr_results, key=lambda x: (sequential_number_score(x), digit_line_count(x), len(x)))
    
    # Remove any leading page numbers from each bibliography entry.
    cleaned_text = remove_page_numbers_from_biblio(best_text)
    # Clean up extra spaces/newlines.
    cleaned_text = "\n".join([line.strip() for line in cleaned_text.splitlines() if line.strip()])
    return cleaned_text

def process_bibliography(input_dir):
    """
    Process the bibliography portion of each page listed in bookindex.json.
    For pages with a 'separator_y' defined, process the bibliography using multi-scan OCR.
    The new index (with updated bibliography fields) is saved in a separate file.
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

    new_book_index = []  # We'll create a new structure with updated bibliography only
    total_pages = len(original_book_index)
    logging.info(f"Processing bibliography for {total_pages} page(s).")
    
    for idx, page_info in enumerate(original_book_index, start=1):
        new_page_info = dict(page_info)  # Copy other metadata
        image_file = page_info.get("file", "")
        image_path = script_dir / image_file
        if not image_path.exists():
            logging.warning(f"Missing image file {image_file}, skipping page {idx}.")
            new_page_info["bibliography"] = ""
        elif page_info.get("separator_y") is not None:
            logging.info(f"Processing bibliography for {image_file} ({idx}/{total_pages})")
            biblio_text = process_bibliography_page(image_path, page_info)
            new_page_info["bibliography"] = biblio_text
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
    Logs per-page metrics and a summary:
      - Digit-line count: Number of lines starting with a digit.
      - Sequential numbering score: How many consecutive numbers starting with 1.
      - Text length.
    """
    total_pages = len(original_index)
    improved_seq = 0
    improved_digit = 0
    improved_length = 0
    compared_pages = 0

    for i, (orig_page, new_page) in enumerate(zip(original_index, new_index)):
        orig_text = orig_page.get("bibliography", "")
        new_text = new_page.get("bibliography", "")
        # Only compare pages that have a bibliography region (either original or new)
        if not (orig_text or new_text):
            continue

        orig_digit = digit_line_count(orig_text)
        new_digit = digit_line_count(new_text)
        orig_seq = sequential_number_score(orig_text)
        new_seq = sequential_number_score(new_text)
        orig_len = len(orig_text)
        new_len = len(new_text)
        compared_pages += 1

        logging.info(f"Page {i+1}:")
        logging.info(f"  Original -> digit_count: {orig_digit}, sequential_score: {orig_seq}, length: {orig_len}")
        logging.info(f"  New      -> digit_count: {new_digit}, sequential_score: {new_seq}, length: {new_len}")

        if new_seq > orig_seq:
            improved_seq += 1
            logging.info("  Improvement: Better sequential numbering.")
        if new_digit > orig_digit:
            improved_digit += 1
            logging.info("  Improvement: More bibliography lines starting with digits.")
        if new_len > orig_len:
            improved_length += 1
            logging.info("  Improvement: Longer OCR output (more content captured).")
    
    logging.info("Comparison Summary:")
    logging.info(f"  Pages compared: {compared_pages} out of {total_pages}")
    logging.info(f"  Pages with improved sequential numbering: {improved_seq}")
    logging.info(f"  Pages with more digit-leading lines: {improved_digit}")
    logging.info(f"  Pages with longer text: {improved_length}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Bibliography OCR Script: Multi-scan OCR for improved bibliography extraction and page number removal."
    )
    parser.add_argument("--input", default=".", help="Directory containing images and bookindex.json")
    args = parser.parse_args()
    
    result = process_bibliography(args.input)
    if result is not None:
        original_index, new_index = result
        compare_bibliography(original_index, new_index)
