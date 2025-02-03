import json
import shutil
import os
import cv2
import numpy as np
import logging
import re
from pathlib import Path
import argparse
from natsort import natsorted, ns

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def detect_image_presence(image):
    """Detects whether an image is present using adaptive thresholding and refined contour analysis."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2)
    
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    total_contour_area = sum(cv2.contourArea(c) for c in contours)
    page_area = gray.shape[0] * gray.shape[1]
    
    # Ignore very small contours (likely text artifacts)
    filtered_contours = [c for c in contours if cv2.contourArea(c) > 3000]
    large_contours = [c for c in filtered_contours if cv2.contourArea(c) > 10000]
    
    # Classify as image-present if images take up >10% of the page or if there are multiple large elements
    return total_contour_area / page_area > 0.10 or len(large_contours) > 2  

def classify_page(image):
    """Classifies a page as 'image-present' or 'image-absent' based on image detection."""
    if image is None or image.size == 0:
        logging.warning("⚠️ Error: Image not loaded correctly.")
        return "error"

    return "image-present" if detect_image_presence(image) else "image-absent"

def determine_page_number(index, intro_pages):
    """Determines the correct page number based on intro pages."""
    return index - intro_pages if index > intro_pages else None

def ensure_json_exists(json_file, image_dir, intro_pages=12):
    """Creates bookindex.json if it doesn't exist and populates it with initial image data."""
    json_file = Path(json_file)
    
    images = natsorted(
        [f for f in os.listdir(image_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg'))], 
        alg=ns.INT
    )
    
    if not images:
        logging.warning("⚠️ No images found in directory. Exiting process.")
        return
    
    if not json_file.exists():
        logging.warning(f"⚠️ {json_file} not found. Creating and populating bookindex.json.")
        bookindex = [{
            "file": img,
            "type": "pending",  # Placeholder until classification is performed
            "page_number": determine_page_number(i + 1, intro_pages),
            "page_type": "index" if i + 1 <= intro_pages else "main"
        } for i, img in enumerate(images)]
        
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(bookindex, f, indent=4)

def detect_black_lines(image_path):
    """Detects black separator lines in an image."""
    logging.info(f"🔍 Processing {image_path}")
    try:
        image = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if image is None:
            logging.error(f"❌ Skipping unreadable image: {image_path}")
            return None
        
        binary_image = cv2.adaptiveThreshold(image, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 10)
        kernel = np.ones((2, 25), np.uint8)
        filtered_image = cv2.morphologyEx(binary_image, cv2.MORPH_OPEN, kernel)
        edges = cv2.Canny(filtered_image, 40, 150)
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, 90, minLineLength=25, maxLineGap=6)
        
        detected_y = None
        image_height, image_width = image.shape
        
        if lines is not None:
            for line in lines:
                x1, y1, x2, y2 = line[0]
                if abs(y2 - y1) < 15 and (x2 - x1) < image_width * 0.4:
                    if detected_y is None or y1 > detected_y:
                        detected_y = y1
        
        if detected_y is not None:
            logging.info(f"✅ Detected separator at Y={detected_y}")
            return int(detected_y)
        
        logging.info("⚠️ No valid separator found.")
        return None
    except Exception as e:
        logging.exception("⚠️ Exception in black line detection:", exc_info=e)
        return None

def process_images(image_dir, bookindex_path, intro_pages=12):
    """Processes images, detecting black lines and updating bookindex.json."""
    logging.info("📖 Starting image processing...")
    
    ensure_json_exists(bookindex_path, image_dir, intro_pages)
    
    try:
        with open(bookindex_path, 'r', encoding='utf-8') as f:
            bookindex = json.load(f)
    except json.JSONDecodeError as e:
        logging.error(f"❌ ERROR: Invalid JSON format in {bookindex_path}: {e}")
        return
    
    for index, entry in enumerate(bookindex, start=1):
        image_path = os.path.join(image_dir, entry.get('file', ''))
        if not os.path.exists(image_path):
            logging.warning(f"⚠️ Image file not found: {image_path}")
            continue
        
        image = cv2.imread(image_path)
        entry['type'] = classify_page(image)  # Classify image presence
        entry['page_number'] = determine_page_number(index, intro_pages)  # Correct page number assignment
        
        black_line_y = detect_black_lines(image_path)
        if black_line_y is not None:
            entry['black_line_y'] = black_line_y
    
    with open(bookindex_path, 'w', encoding='utf-8') as f:
        json.dump(bookindex, f, indent=4)
    
    logging.info(f"✅ Processing complete. Results saved to {bookindex_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--images", required=True, help="Directory containing images")
    parser.add_argument("--json", help="Path to bookindex.json (optional, defaults to images folder)")
    parser.add_argument("--intro_pages", type=int, default=12, help="Number of introductory pages before main content")
    args = parser.parse_args()
    
    image_dir = args.images
    json_file = args.json if args.json else os.path.join(image_dir, "bookindex.json")
    
    process_images(image_dir, json_file, args.intro_pages)
