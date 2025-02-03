import cv2
import pytesseract
import os
import json
import logging
import numpy as np
import argparse
from pathlib import Path
from PIL import Image

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def preprocess_image(image_path):
    """Preprocess image for better OCR accuracy."""
    image = cv2.imread(str(image_path))
    if image is None:
        logging.error(f"ERROR: Image not found or unreadable: {image_path}")
        return None
    try:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        enhanced = cv2.convertScaleAbs(gray, alpha=2.0, beta=15)
        denoised = cv2.fastNlMeansDenoising(enhanced, None, 30, 7, 21)
        return cv2.adaptiveThreshold(denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
    except Exception as e:
        logging.error(f"ERROR during preprocessing: {e}")
        return None

def run_ocr(image):
    """Run OCR twice with different PSM modes and merge results."""
    try:
        config_psm6 = '--oem 3 --psm 6 -c preserve_interword_spaces=1'
        config_psm3 = '--oem 3 --psm 3 -c preserve_interword_spaces=1'

        # First OCR run with PSM 6 (structured text)
        text_psm6 = pytesseract.image_to_string(image, config=config_psm6, lang='eng').strip()
        
        # Second OCR run with PSM 3 (detects multiple blocks of text)
        text_psm3 = pytesseract.image_to_string(image, config=config_psm3, lang='eng').strip()

        # Merge results intelligently
        if text_psm6 == text_psm3:
            return text_psm6  # If both are identical, return one
        else:
            return merge_text(text_psm6, text_psm3)

    except Exception as e:
        logging.error(f"OCR ERROR: {e}")
        return ""

def merge_text(text1, text2):
    """Merge OCR results intelligently by keeping unique content."""
    lines1 = set(text1.split("\n"))
    lines2 = set(text2.split("\n"))
    merged_lines = sorted(lines1 | lines2, key=lambda x: text1.find(x) if x in text1 else text2.find(x))
    return "\n".join(merged_lines)

def clean_bibliography(text, page_number):
    """Extract bibliography and remove unnecessary entries."""
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    if lines and lines[-1] == str(page_number):
        lines.pop()
    return lines

def process_page(image_path, page_info):
    """Process an individual page and extract necessary information."""
    try:
        image = Image.open(image_path)
    except Exception as e:
        logging.error(f"ERROR opening image {image_path}: {e}")
        return None
    
    main_text, bibliography = "", ""
    
    try:
        if 'black_line_y' in page_info:
            img_cv = cv2.imread(str(image_path))
            main_area = img_cv[:page_info['black_line_y'], :]
            bottom_area = img_cv[page_info['black_line_y']:, :]
            main_text = run_ocr(Image.fromarray(main_area))
            bibliography = run_ocr(Image.fromarray(bottom_area))
        else:
            main_text = run_ocr(image)
    except Exception as e:
        logging.error(f"ERROR processing OCR on {image_path}: {e}")
    
    return {
        "page_type": "intro" if page_info.get("section") == "intro" else "main",
        "image_present": page_info.get("type", "image-absent") == "image-present",
        "page_number": page_info.get("page_number"),
        "content": main_text,
        "bibliography": clean_bibliography(bibliography, page_info.get("page_number")),
        "captions": []
    }

def process_images(input_dir):
    """Process images and store extracted text in structured JSON format."""
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
    for index, page_info in enumerate(book_index, start=1):
        image_path = script_dir / page_info.get("file", "")
        if not image_path.exists():
            logging.warning(f"Missing image: {page_info.get('file', 'UNKNOWN')}, skipping.")
            continue
        
        logging.info(f"📄 Processing {page_info.get('file', 'UNKNOWN')} ({index}/{len(book_index)})")
        page_json = process_page(image_path, page_info)
        if page_json:
            all_pages.append(page_json)
        
        if index % 10 == 0 or index == len(book_index):
            chunk_file = output_dir / f"chunk_{(index // 10):03d}.json"
            with open(chunk_file, "w", encoding="utf-8") as f:
                json.dump(all_pages, f, indent=4, ensure_ascii=False)
            logging.info(f"✅ Saved chunk: {chunk_file}")
            all_pages = []
    
    logging.info("🎉 Processing complete! Chunks saved in {output_dir}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OCR Script for processing images to JSON")
    parser.add_argument("--input", default=".", help="Directory containing images")
    args = parser.parse_args()
    process_images(args.input)
