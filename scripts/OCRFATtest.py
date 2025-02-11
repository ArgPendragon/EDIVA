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
from collections import defaultdict

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def normalize_coords(coords):
    """Normalize coordinates to a list of four integers [x, y, w, h]."""
    if coords is None:
        return None
    if isinstance(coords, dict):
        try:
            return [int(coords.get("x", 0)), int(coords.get("y", 0)),
                    int(coords.get("w", 0)), int(coords.get("h", 0))]
        except Exception as e:
            logging.error(f"Error normalizing dict coords {coords}: {e}")
            return None
    elif isinstance(coords, (list, tuple)):
        try:
            return [int(c) for c in coords]
        except Exception as e:
            logging.error(f"Error normalizing list coords {coords}: {e}")
            return None
    else:
        logging.error(f"Unknown coords format: {coords}")
        return None

def is_valid_caption(text):
    """Check if the OCR'd caption contains at least one word of 4 or more letters."""
    words = re.findall(r'\b\w{4,}\b', text)
    return len(words) > 0

def crop_region(image, coords):
    """Crop a region from a PIL image using normalized coordinates."""
    norm_coords = normalize_coords(coords)
    if norm_coords is None:
        return None
    try:
        x, y, w, h = norm_coords
        return image.crop((x, y, x + w, y + h))
    except Exception as e:
        logging.error(f"crop_region error with coords {coords}: {e}")
        return None

def mask_exclusion_areas(pil_img, regions):
    """Mask (whiten out) regions in the image specified by a list of [x, y, w, h]."""
    cv_img = np.array(pil_img.convert('RGB'))
    for coords in regions:
        norm_coords = normalize_coords(coords)
        if norm_coords is None:
            continue
        try:
            x, y, w, h = norm_coords
            cv_img[y:y + h, x:x + w] = [255, 255, 255]
        except Exception as e:
            logging.error(f"mask_exclusion_areas error with coords {coords}: {e}")
    return Image.fromarray(cv_img)

def run_ocr_on_image(pil_img, config='--oem 3 --psm 6 -c preserve_interword_spaces=1', lang='eng'):
    """Run OCR on a PIL image and return the extracted text."""
    try:
        text = pytesseract.image_to_string(pil_img, config=config, lang=lang).strip()
        return text
    except Exception as e:
        logging.error(f"OCR error: {e}")
        return ""

def detect_headers_simple(text):
    """
    A simple header detection routine:
      - Splits text into lines.
      - If a line is nonempty, longer than 3 characters, and completely uppercase,
        it is flagged as a header.
    Returns a list of header strings.
    """
    headers = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and len(stripped) > 3 and stripped == stripped.upper():
            headers.append(stripped)
    return headers

def parse_index_page(index_text):
    """
    Parse OCR text from an index page to extract chapter information.
    If no chapters are found, the calling code may fall back to standard OCR.
    """
    lines = [line.strip() for line in index_text.splitlines() if line.strip()]
    chapters = []
    current_chapter = None
    for line in lines:
        if re.match(r'^Chapter\s+\d+', line, re.IGNORECASE):
            if current_chapter:
                chapters.append(current_chapter)
            current_chapter = {"chapter_number": line, "chapter_title": "", "entries": []}
        elif current_chapter and not current_chapter.get("chapter_title"):
            current_chapter["chapter_title"] = line
        else:
            m = re.search(r'(\d+)$', line)
            if m and current_chapter:
                page_number = m.group(1)
                entry_text = line[:m.start()].strip()
                current_chapter["entries"].append({"text": entry_text, "page_number": page_number})
    if current_chapter:
        chapters.append(current_chapter)
    return chapters

def process_page(image_path, page_info):
    """
    Process a single page image.
      - For index pages: if chapter info is extracted use it; otherwise, fall back to normal OCR.
      - For main pages:
          1. Extract caption areas (internal/external) and add valid ones.
          2. Extract the bibliography region (if a separator_y is provided) and mask it.
          3. Run OCR on the remaining (masked) image to get the main text.
          4. Detect headers from the main text using a simple uppercase rule.
      - Clean out extraneous whitespace from the final text while preserving Markdown formatting.
    """
    try:
        original_image = Image.open(image_path)
    except Exception as e:
        logging.error(f"Error opening image {image_path}: {e}")
        return None

    page_number = page_info.get("page_number")
    image_present = page_info.get("type", "image-absent") == "image-present"
    page_type = page_info.get("page_type", "main")

    # Special handling for index (or introductory) pages.
    if page_type == "index":
        index_text = run_ocr_on_image(original_image)
        chapters = parse_index_page(index_text)
        if chapters:
            return {
                "page_type": page_type,
                "page_number": page_number,
                "index": chapters
            }
        else:
            logging.info("Index page parsing failed, reverting to normal OCR.")
            page_type = "main"

    captions = []
    exclusion_regions = []

    # Process caption areas.
    if page_info.get("internal_caption_coordinates"):
        coords = page_info["internal_caption_coordinates"]
        internal_caption_img = crop_region(original_image, coords)
        if internal_caption_img is not None:
            text_internal = run_ocr_on_image(internal_caption_img)
            if is_valid_caption(text_internal):
                # Preserve newlines and spacing for Markdown formatting.
                captions.append({"source": "internal", "text": text_internal.strip()})
                exclusion_regions.append(coords)
        else:
            logging.error("Internal caption region could not be cropped.")

    if page_info.get("external_caption_coordinates"):
        coords = page_info["external_caption_coordinates"]
        external_caption_img = crop_region(original_image, coords)
        if external_caption_img is not None:
            text_external = run_ocr_on_image(external_caption_img)
            if is_valid_caption(text_external):
                # Preserve newlines and spacing for Markdown formatting.
                captions.append({"source": "external", "text": text_external.strip()})
                exclusion_regions.append(coords)
        else:
            logging.error("External caption region could not be cropped.")

    # Process bibliography area.
    bibliography_text = ""
    if page_info.get("separator_y") is not None:
        try:
            separator_y = int(page_info["separator_y"])
            width, height = original_image.size
            if 0 < separator_y < height:
                biblio_region = original_image.crop((0, separator_y, width, height))
                bibliography_raw = run_ocr_on_image(biblio_region)
                # Just strip extra whitespace, preserving any Markdown formatting (e.g. newlines).
                bibliography_text = bibliography_raw.strip()
                exclusion_regions.append([0, separator_y, width, height - separator_y])
            else:
                logging.warning(f"separator_y value {separator_y} is out of bounds for image height {height}.")
        except Exception as e:
            logging.error(f"Error processing bibliography region: {e}")

    # Exclude image areas (if any).
    if page_info.get("image_coordinates"):
        exclusion_regions.append(page_info["image_coordinates"])

    # Process main text.
    main_text_image = mask_exclusion_areas(original_image, exclusion_regions)
    main_text_raw = run_ocr_on_image(main_text_image)
    headers = detect_headers_simple(main_text_raw)
    # Preserve the original newlines and spacing for Markdown formatting.
    main_text = main_text_raw.strip()

    # Build output with main_text listed first.
    page_output = {
        "page_type": page_type,
        "image_present": image_present,
        "page_number": page_number,
        "main_text": main_text,
        "captions": captions,
        "bibliography": bibliography_text,
        "headers": headers
    }
    return page_output

def process_images(input_dir):
    """
    Process images using the provided JSON index (bookindex.json).
    Every 10 pages (or at the end), the current batch is saved.
    If a batch's JSON exceeds 25k characters, it is split into two chunks.
    """
    script_dir = Path(input_dir)
    input_file = script_dir / "bookindex.json"
    output_dir = script_dir / "chunks"
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_file.exists():
        logging.error("ERROR: bookindex.json not found!")
        return

    try:
        with open(input_file, "r", encoding="utf-8") as f:
            book_index = json.load(f)
    except Exception as e:
        logging.error(f"ERROR loading bookindex.json: {e}")
        return

    all_pages = []
    chunk_counter = 1
    total_pages = len(book_index)
    for index, page_info in enumerate(book_index, start=1):
        image_path = script_dir / page_info.get("file", "")
        if not image_path.exists():
            logging.warning(f"Missing image: {page_info.get('file', 'UNKNOWN')}, skipping.")
            continue

        logging.info(f"Processing {page_info.get('file', 'UNKNOWN')} ({index}/{total_pages})")
        page_json = process_page(image_path, page_info)
        if page_json:
            all_pages.append(page_json)

        if index % 10 == 0 or index == total_pages:
            batch_json = json.dumps(all_pages, indent=4, ensure_ascii=False)
            if len(batch_json) > 25000 and len(all_pages) > 1:
                mid = len(all_pages) // 2
                first_half = all_pages[:mid]
                second_half = all_pages[mid:]
                chunk_file = output_dir / f"chunk_{chunk_counter:03d}.json"
                with open(chunk_file, "w", encoding="utf-8") as f:
                    json.dump(first_half, f, indent=4, ensure_ascii=False)
                logging.info(f"Saved chunk: {chunk_file} (contains {len(first_half)} page(s))")
                chunk_counter += 1
                chunk_file = output_dir / f"chunk_{chunk_counter:03d}.json"
                with open(chunk_file, "w", encoding="utf-8") as f:
                    json.dump(second_half, f, indent=4, ensure_ascii=False)
                logging.info(f"Saved chunk: {chunk_file} (contains {len(second_half)} page(s))")
                chunk_counter += 1
            else:
                chunk_file = output_dir / f"chunk_{chunk_counter:03d}.json"
                with open(chunk_file, "w", encoding="utf-8") as f:
                    json.dump(all_pages, f, indent=4, ensure_ascii=False)
                logging.info(f"Saved chunk: {chunk_file} (contains {len(all_pages)} page(s))")
                chunk_counter += 1
            all_pages = []

    logging.info(f"Processing complete! Chunks saved in {output_dir}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Refined OCR Script: Single-String Bibliography, Simple Header Detection, and Cleaned Text Output (Markdown formatting preserved)"
    )
    parser.add_argument("--input", default=".", help="Directory containing images and bookindex.json")
    args = parser.parse_args()
    process_images(args.input)
