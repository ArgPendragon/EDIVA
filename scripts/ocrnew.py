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

def preprocess_image(image_path):
    """Preprocess image for OCR (handles noise, low contrast, and blurring)."""
    logging.info(f"📷 Preprocessing image: {image_path}")
    image = cv2.imread(str(image_path))
    
    if image is None:
        logging.error(f"🚨 ERROR: Image not found or unreadable: {image_path}")
        return None
    
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, None, 30, 7, 21)
    thresh = cv2.adaptiveThreshold(denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
    
    logging.info(f"✅ Image preprocessing complete for: {image_path}")
    return thresh

def run_ocr(image_path, psm_mode=6):
    """Run OCR and return extracted text."""
    logging.info(f"📄 Running OCR on: {image_path} (PSM {psm_mode})")
    try:
        preprocessed_image = preprocess_image(image_path)
        if preprocessed_image is None:
            return ""
        custom_config = f'--oem 3 --psm {psm_mode} -c preserve_interword_spaces=1'
        text = pytesseract.image_to_string(preprocessed_image, config=custom_config, lang='eng').strip()
        return text
    except Exception as e:
        logging.error(f"🚨 OCR failed for {image_path}: {e}", exc_info=True)
        return ""

def adaptive_ocr(image_path):
    """Run OCR adaptively, trying different modes only if needed."""
    logging.info(f"🛠 Adaptive OCR started for {image_path}")
    
    text_psm6 = run_ocr(image_path, 6)
    if len(text_psm6) > 50:
        return text_psm6
    
    text_psm4 = run_ocr(image_path, 4)
    text_psm11 = run_ocr(image_path, 11)
    
    results = {"psm6": text_psm6, "psm4": text_psm4, "psm11": text_psm11}
    best_psm = max(results, key=lambda k: len(results[k]), default="psm6")
    best_text = results[best_psm]
    
    logging.info(f"✅ Best OCR mode for {image_path}: {best_psm} (Extracted {len(best_text)} chars)")
    return best_text

def process_images_to_json(directory, output_dir):
    """Process images and save structured JSON in 10-image chunks."""
    logging.info(f"🗂 Processing images from: {directory}")
    
    directory = Path(directory)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    image_files = natsorted(directory.glob("*.png") + directory.glob("*.jpg") + directory.glob("*.jpeg"))
    logging.info(f"📂 Found {len(image_files)} images.")
    
    all_pages = []
    for index, img_path in enumerate(image_files, start=1):
        logging.info(f"📄 Processing image {index}/{len(image_files)}: {img_path.name}")
        
        text = adaptive_ocr(img_path)
        page_json = {"page_number": index, "text": text}
        all_pages.append(page_json)
        
        if index % 10 == 0:
            with open(output_dir / f"output_{index//10}.json", 'w', encoding='utf-8') as f:
                json.dump(all_pages, f, indent=4, ensure_ascii=False)
            logging.info(f"✅ Chunk saved: output_{index//10}.json")
            all_pages = []
    
    if all_pages:
        with open(output_dir / "output_final.json", 'w', encoding='utf-8') as f:
            json.dump(all_pages, f, indent=4, ensure_ascii=False)
        logging.info(f"✅ Final chunk saved: output_final.json")
    
    logging.info(f"✅ Processing complete!")
