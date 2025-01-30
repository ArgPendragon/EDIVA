import cv2
import pytesseract
import os
from pathlib import Path
import json
import logging
import numpy as np
from natsort import natsorted  
from PIL import Image
import re

# Setup logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Ensure Tesseract is installed and set its path
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def preprocess_image(image_path):
    """Preprocess image for OCR (handles noise, low contrast, and blurring)."""
    logging.info(f"📷 Preprocessing image: {image_path}")
    image = cv2.imread(str(image_path))

    if image is None:
        logging.error(f"🚨 ERROR: Image not found or unreadable: {image_path}")
        return None

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Apply denoising to remove noise while preserving text
    denoised = cv2.fastNlMeansDenoising(gray, None, 30, 7, 21)

    # Apply adaptive thresholding for better contrast
    thresh = cv2.adaptiveThreshold(denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)

    logging.info(f"✅ Exiting preprocess_image for: {image_path}")
    return thresh

def run_ocr(image_path, psm_mode):
    """Run OCR with the specified PSM mode and return text."""
    logging.info(f"📄 Running OCR on: {image_path} (PSM {psm_mode})")
    
    try:
        image = Image.open(image_path)
    except Exception as e:
        logging.error(f"🚨 ERROR: Could not open image {image_path} - {e}")
        return ""

    custom_config = f'--oem 3 --psm {psm_mode} -c preserve_interword_spaces=1'
    text = pytesseract.image_to_string(image, config=custom_config, lang='eng').strip()

    logging.info(f"✅ OCR result (PSM {psm_mode}): {len(text)} characters extracted.")
    return text

def adaptive_ocr(image_path):
    """Run OCR adaptively, trying different modes only if needed."""
    logging.info(f"🛠 Adaptive OCR started for {image_path}")

    text_psm6 = run_ocr(image_path, 6)  # Start with normal text mode
    if len(text_psm6) > 50:  # If the result seems good, return it
        return text_psm6

    text_psm4 = run_ocr(image_path, 4)  # Try multi-column mode if needed
    text_psm11 = run_ocr(image_path, 11)  # Try sparse text mode

    # Choose the best result
    results = {"psm6": text_psm6, "psm4": text_psm4, "psm11": text_psm11}
    best_psm = max(results, key=lambda k: len(results[k]), default="psm6")
    best_text = results[best_psm]

    logging.info(f"✅ Best OCR mode for {image_path}: {best_psm} (Extracted {len(best_text)} chars)")
    return best_text

def detect_bibliography(image_path):
    """Detect smaller text at the bottom of the page (bibliography)."""
    logging.info(f"📚 Extracting bibliography from: {image_path}")

    image = cv2.imread(str(image_path))
    if image is None:
        logging.error(f"🚨 ERROR: Failed to load image for bibliography: {image_path}, skipping.")
        return ""

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    bottom_section = gray[int(h * 0.75):, :]

    if bottom_section is None or bottom_section.size == 0:
        return ""

    bibliography_text = pytesseract.image_to_string(bottom_section, lang='eng').strip()
    logging.info(f"✅ Bibliography OCR result: {len(bibliography_text)} characters extracted.")
    return bibliography_text

def process_images_to_json(directory, output_dir):
    """Process images and save structured JSON in 10-image chunks."""
    logging.info(f"🗂 Processing images from: {directory}")

    directory = Path(directory)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    image_files = natsorted(list(directory.glob("*.png")) + 
                        list(directory.glob("*.jpg")) + 
                        list(directory.glob("*.jpeg")))

    logging.info(f"📂 Found {len(image_files)} images.")

    all_pages = []

    for index, img_path in enumerate(image_files, start=1):
        logging.info(f"📄 Processing image {index}/{len(image_files)}: {img_path.name}")

        text = adaptive_ocr(img_path)
        bibliography_text = detect_bibliography(img_path)

        page_json = {
            "page_number": index,
            "subsections": [{"title": "Full Text", "content": text}] if text else [],
            "bibliography": bibliography_text.split("\n") if bibliography_text else []
        }

        all_pages.append(page_json)

        # Save every 10 pages to avoid memory overload
        if index % 10 == 0:
            with open(output_dir / f"output_{index//10}.json", 'w', encoding='utf-8') as f:
                json.dump(all_pages, f, indent=4, ensure_ascii=False)
            logging.info(f"✅ Chunk saved: output_{index//10}.json")
            all_pages = []  # Clear memory

    logging.info(f"✅ Processing complete!")

if __name__ == "__main__":
    process_images_to_json("D:/cardotest/ExtractedImages/1God", "D:/cardotest/ExtractedImages/1God/chunks")