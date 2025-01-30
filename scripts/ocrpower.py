import cv2
import pytesseract
import os
import json
import logging
import re
from pathlib import Path
from natsort import natsorted  
from PIL import Image
import numpy as np

# Setup logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

last_reference_number = 0  # Track last detected reference number
current_chapter = None  # Track the current chapter for resetting references

def run_ocr(image_path, psm_mode=6):
    """Run OCR and return extracted text."""
    logging.info(f"📄 Running OCR on: {image_path} (PSM {psm_mode})")
    try:
        if not os.path.exists(image_path):
            logging.error(f"🚨 ERROR: File does not exist - {image_path}")
            return ""
        
        image = Image.open(image_path)
        custom_config = f'--oem 3 --psm {psm_mode} -c preserve_interword_spaces=1'
        text = pytesseract.image_to_string(image, config=custom_config, lang='eng').strip()
        return text
    except Exception as e:
        logging.error(f"🚨 OCR failed for {image_path}: {e}", exc_info=True)
        return ""

def detect_black_lines(image_path):
    """Detects black separator lines and filters out long ones (image borders)."""
    logging.info(f"🔍 Detecting black separator lines in: {image_path}")
    try:
        if not os.path.exists(image_path):
            logging.error(f"🚨 ERROR: File does not exist - {image_path}")
            return None

        image = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if image is None:
            logging.error(f"🚨 ERROR: Unable to read image: {image_path}")
            return None

        height, width = image.shape[:2] if image.shape else (0, 0)
        edges = cv2.Canny(image, 50, 150)
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=100, minLineLength=100, maxLineGap=5)
        
        valid_lines = []
        if lines is not None:
            for line in lines:
                x1, y1, x2, y2 = line[0]
                if abs(y1 - y2) < 10 and abs(x2 - x1) < width * 0.5:
                    valid_lines.append((x1, y1, x2, y2))
        
        if valid_lines:
            y_positions = [y1 for _, y1, _, _ in valid_lines]
            lowest_line = max(y_positions)
            logging.info(f"✅ Detected separator line at Y={lowest_line}")
            return lowest_line
        
        logging.warning("⚠ No valid separator line detected.")
        return None
    except Exception as e:
        logging.error(f"🚨 Exception in detect_black_lines: {e}", exc_info=True)
        return None

def detect_chapters(text):
    """Detects chapters and subchapters from index pages."""
    try:
        chapter_titles = re.findall(r'\b(?:Chapter|CHAPTER)\s+\d+[:.]?\s*(.*)', text, re.IGNORECASE)
        return chapter_titles if chapter_titles else None
    except Exception as e:
        logging.error(f"🚨 Exception in detect_chapters: {e}", exc_info=True)
        return None

def classify_index_page(text):
    """Classify index pages correctly, distinguishing between true index pages, acknowledgments, or blank pages."""
    try:
        if not text.strip():
            return "blank"
        
        non_index_keywords = ["Acknowledgments", "Preface", "Foreword", "Introduction"]
        for keyword in non_index_keywords:
            if re.search(rf'\b{keyword}\b', text, re.IGNORECASE):
                return "non-index"
        
        detected_chapters = detect_chapters(text)
        return "index" if detected_chapters else "non-index"
    except Exception as e:
        logging.error(f"🚨 Exception in classify_index_page: {e}", exc_info=True)
        return "error"

def extract_bibliography(text, image_path):
    """Extracts bibliography using detected separator lines."""
    try:
        separator_y = detect_black_lines(image_path)
        if separator_y is None:
            logging.warning("⚠ No separator line found, skipping bibliography extraction.")
            return text, []

        lines = text.split("\n")
        bibliography = []
        biblio_start_index = None
        for i, line in enumerate(lines):
            if re.match(r"(\d{1,2})\.\s(.+)", line):
                biblio_start_index = i
                break

        if biblio_start_index is not None:
            bibliography = [{"reference_number": match.group(1), "content": match.group(2)}
                            for match in (re.match(r"(\d{1,2})\.\s(.+)", line) for line in lines[biblio_start_index:]) if match]
            text = "\n".join(lines[:biblio_start_index])
            logging.info(f"✅ Extracted {len(bibliography)} bibliography entries.")
        else:
            logging.warning("⚠ No numbered references detected in bibliography section.")
        
        return text, bibliography
    except Exception as e:
        logging.error(f"🚨 Exception in extract_bibliography: {e}", exc_info=True)
        return text, []

if __name__ == "__main__":
    try:
        test_image = "sample_image.png"  # Change this to an actual file
        logging.info(f"🟢 Starting OCR script with test image: {test_image}")
        extracted_text = run_ocr(test_image)
        logging.info(f"Extracted text:\n{extracted_text}")
    except Exception as e:
        logging.critical(f"🚨 Unhandled Exception: {e}", exc_info=True)
