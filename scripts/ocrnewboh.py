import cv2
import pytesseract
import os
from pathlib import Path
import json
import logging
import numpy as np
import re
from natsort import natsorted  
from PIL import Image

# Setup logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def preprocess_image(image_path):
    """Preprocess image for better OCR accuracy."""
    logging.info(f"📷 Preprocessing image: {image_path}")
    image = cv2.imread(str(image_path))

    if image is None:
        logging.error(f"🚨 ERROR: Image not found or unreadable: {image_path}")
        return None

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    enhanced = cv2.convertScaleAbs(gray, alpha=1.5, beta=10)
    denoised = cv2.fastNlMeansDenoising(enhanced, None, 30, 7, 21)
    kernel = np.ones((2,2), np.uint8)
    morph = cv2.morphologyEx(denoised, cv2.MORPH_CLOSE, kernel)
    thresh = cv2.adaptiveThreshold(morph, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)

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

    text_psm6 = run_ocr(image_path, 6)  # Normal text mode
    if len(text_psm6) > 50:  # Acceptable quality
        return text_psm6

    text_psm4 = run_ocr(image_path, 4)  # Multi-column mode
    text_psm3 = run_ocr(image_path, 3)  # Sparse + tables mode

    results = {"psm6": text_psm6, "psm4": text_psm4, "psm3": text_psm3}
    best_psm = max(results, key=lambda k: len(results[k]), default="psm6")
    best_text = results[best_psm]

    logging.info(f"✅ Best OCR mode for {image_path}: {best_psm} (Extracted {len(best_text)} chars)")
    return best_text

def clean_ocr_text(text):
    """Clean OCR text by removing initial noise, fixing formatting."""
    lines = text.split("\n")
    
    # Remove excessive gibberish in the first few lines
    cleaned_lines = []
    for line in lines:
        if len(re.findall(r'[a-zA-Z]', line)) > 3:  # Ensure it's not mostly symbols
            cleaned_lines.append(line.strip())

    return "\n".join(cleaned_lines)

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
    
    # Keep only properly formatted bibliography lines
    bibliography_text = "\n".join([line.strip() for line in bibliography_text.split("\n") if len(line.strip()) > 5])
    
    logging.info(f"✅ Bibliography OCR result: {len(bibliography_text)} characters extracted.")
    return bibliography_text

def process_images_to_json():
    """Automatically process images in the script's directory and save structured JSON in 'chunks' folder."""
    
    # Automatically detect the script directory
    script_dir = Path(__file__).parent
    output_dir = script_dir / "chunks"
    output_dir.mkdir(parents=True, exist_ok=True)  # Ensure the chunks directory exists

    logging.info(f"📂 Looking for images in: {script_dir}")

    # Collect all image files in the script's directory
    image_files = natsorted(list(script_dir.glob("*.png")) + 
                            list(script_dir.glob("*.jpg")) + 
                            list(script_dir.glob("*.jpeg")))

    if not image_files:
        logging.warning("🚨 No images found in the directory. Exiting.")
        return

    logging.info(f"📂 Found {len(image_files)} images.")

    all_pages = []
    chunk_number = 1  

    for index, img_path in enumerate(image_files, start=1):
        logging.info(f"📄 Processing image {index}/{len(image_files)}: {img_path.name}")

        raw_text = adaptive_ocr(img_path)  # Extract text
        cleaned_text = clean_ocr_text(raw_text)  # Remove garbage text

        bibliography_text = detect_bibliography(img_path)

        page_type = "index" if index <= 12 else "main"
        page_number = None if index <= 12 else index - 12

        subsections = [{"title": "", "content": cleaned_text}] if cleaned_text else []

        page_json = {
            "type": page_type,
            "page_number": page_number,
            "subsections": subsections,
            "bibliography": bibliography_text.split("\n") if bibliography_text else []
        }

        all_pages.append(page_json)

        # Save every 10 pages
        if index % 10 == 0 or index == len(image_files):  
            chunk_name = f"chunk{chunk_number:03d}.json"
            with open(output_dir / chunk_name, 'w', encoding='utf-8') as f:
                json.dump(all_pages, f, indent=4, ensure_ascii=False)
            logging.info(f"✅ Chunk saved: {chunk_name}")
            all_pages = []
            chunk_number += 1

    logging.info(f"✅ Processing complete! Chunks saved in {output_dir}")

if __name__ == "__main__":
    process_images_to_json()
