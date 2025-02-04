import json
import os
import cv2
import numpy as np
import logging
import pytesseract
from pathlib import Path
import argparse
from natsort import natsorted, ns
from typing import Optional

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def save_debug_image(image: np.ndarray, debug_dir: str, filename: str) -> None:
    """Saves an image for debugging purposes in the debug directory."""
    try:
        os.makedirs(debug_dir, exist_ok=True)
        cv2.imwrite(os.path.join(debug_dir, filename), image)
    except Exception as e:
        logging.error(f"❌ Error saving debug image {filename}: {e}")

def detect_text_below(image: np.ndarray, y_coord: int) -> bool:
    """Detects if there is text below the given Y coordinate in the image."""
    height = image.shape[0]
    text_region = image[y_coord + 10: height]  # Extract region below separator
    
    if text_region.shape[0] < 20:
        return False  # Not enough space for text detection
    
    text = pytesseract.image_to_string(text_region, config='--psm 6')
    return bool(text.strip())

def detect_black_lines(image_path: str, page_type: str, debug_dir: str) -> Optional[int]:
    """Detects black separator lines in an image using multiple strategies, preferring the lowest candidate match."""
    logging.info(f"🔍 Processing {image_path} (Page Type: {page_type})")
    try:
        image = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if image is None:
            logging.error(f"❌ Skipping unreadable image: {image_path}")
            return None

        debug_images = {}
        detected_lines = []

        # Strategy 1: Adaptive Thresholding + Morphological Transformations
        binary_adaptive = cv2.adaptiveThreshold(image, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 10)
        kernel = np.ones((2, 30), np.uint8)  # Adjusted kernel for better line detection
        morph_adaptive = cv2.morphologyEx(binary_adaptive, cv2.MORPH_OPEN, kernel)
        edges_adaptive = cv2.Canny(morph_adaptive, 50, 150)
        lines_adaptive = cv2.HoughLinesP(edges_adaptive, 1, np.pi/180, 80, minLineLength=30, maxLineGap=8)
        debug_images['adaptive'] = morph_adaptive

        # Strategy 2: Otsu's Thresholding
        _, binary_otsu = cv2.threshold(image, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        morph_otsu = cv2.morphologyEx(binary_otsu, cv2.MORPH_OPEN, kernel)
        edges_otsu = cv2.Canny(morph_otsu, 50, 150)
        lines_otsu = cv2.HoughLinesP(edges_otsu, 1, np.pi/180, 80, minLineLength=30, maxLineGap=8)
        debug_images['otsu'] = morph_otsu

        # Save debug images
        for name, img in debug_images.items():
            save_debug_image(img, debug_dir, f"{os.path.basename(image_path)}_{name}.jpg")

        # Choose the best detected line (preferring the lowest valid candidate)
        best_y = None
        confidence_score = 0.0
        for lines in [lines_adaptive, lines_otsu]:
            if lines is not None:
                for line in lines:
                    x1, y1, x2, y2 = line[0]
                    if abs(y2 - y1) < 15:  # Ensures horizontal line
                        text_below = detect_text_below(image, y1)
                        score = 1.0 if text_below else 0.7  # Higher confidence if text exists below
                        if best_y is None or y1 < best_y:
                            best_y = y1
                            confidence_score = score

        if best_y is not None:
            logging.info(f"✅ Best detected separator at Y={best_y} (Confidence: {confidence_score:.2f})")
            return int(best_y)
        
        logging.info("⚠️ No valid separator found.")
        return None
    except Exception as e:
        logging.error(f"❌ Error processing {image_path}: {e}")
        return None

def process_images(input_dir: str) -> None:
    """Processes images based on bookindex.json structure, skipping index pages."""
    bookindex_path = os.path.join(input_dir, "bookindex.json")
    debug_bookindex = []
    debug_dir = os.path.join(input_dir, "debug")
    
    if not os.path.exists(bookindex_path):
        logging.error(f"❌ bookindex.json not found in {input_dir}. Exiting.")
        return

    try:
        with open(bookindex_path, 'r', encoding='utf-8') as f:
            bookindex = json.load(f)
    except json.JSONDecodeError as e:
        logging.error(f"❌ Invalid JSON format in bookindex.json: {e}")
        return

    for entry in bookindex:
        image_path = os.path.join(input_dir, entry.get('file', ''))
        page_type = entry.get('page_type', 'main')
        
        if page_type == "index":
            logging.info(f"⏭️ Skipping index page: {image_path}")
            continue

        if not os.path.exists(image_path):
            logging.warning(f"⚠️ Image file not found: {image_path}")
            continue

        detection = detect_black_lines(image_path, page_type, debug_dir)
        
        debug_bookindex.append({
            "image_path": image_path,
            "page_type": page_type,
            "detected_separator": detection
        })
    
    debug_results_path = os.path.join(input_dir, "debug_results.json")
    try:
        with open(debug_results_path, 'w', encoding='utf-8') as f:
            json.dump(debug_bookindex, f, indent=4)
        logging.info(f"✅ Debugging complete. Results saved to {debug_results_path}")
    except Exception as e:
        logging.error(f"❌ Error writing debug JSON file: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Directory containing images and bookindex.json")
    args = parser.parse_args()
    
    process_images(args.input)
