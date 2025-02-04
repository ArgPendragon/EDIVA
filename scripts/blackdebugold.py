import json
import os
import cv2
import numpy as np
import logging
from pathlib import Path
import argparse
from natsort import natsorted, ns

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def save_debug_image(image, debug_dir, filename):
    """Saves an image for debugging purposes in the debug directory."""
    os.makedirs(debug_dir, exist_ok=True)
    cv2.imwrite(os.path.join(debug_dir, filename), image)

def detect_black_lines(image_path, page_type, debug_dir):
    """Detects black separator lines in an image with adaptive parameters."""
    logging.info(f"🔍 Processing {image_path} (Page Type: {page_type})")
    
    try:
        image = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if image is None:
            logging.error(f"❌ Skipping unreadable image: {image_path}")
            return None
        
        # Adaptive thresholding (primary method)
        binary_image = cv2.adaptiveThreshold(image, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 10)
        
        kernel = np.ones((2, 25), np.uint8)
        filtered_image = cv2.morphologyEx(binary_image, cv2.MORPH_OPEN, kernel)
        
        edges = cv2.Canny(filtered_image, 30 if page_type == "image-present" else 40, 150)
        
        # Line detection
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, 90, minLineLength=25, maxLineGap=6)
        detected_separator_y = None
        image_width = image.shape[1]
        max_width_ratio = 0.4 if page_type == "image-absent" else 0.7
        angle_tolerance = 15 if page_type == "image-absent" else 20
        
        debug_image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        
        if lines is not None:
            for line in lines:
                x1, y1, x2, y2 = line[0]
                if abs(y2 - y1) < angle_tolerance and (x2 - x1) < image_width * max_width_ratio:
                    if detected_separator_y is None or y1 > detected_separator_y:
                        detected_separator_y = y1
                    cv2.line(debug_image, (x1, y1), (x2, y2), (0, 255, 0), 2)
        
        # If a separator is confidently detected, remove debug images
        if detected_separator_y is not None:
            logging.info(f"✅ Detected separator at Y={detected_separator_y}")
            return int(detected_separator_y)
        
        # If detection is uncertain, save debug images
        logging.info("⚠️ No valid separator found. Keeping debug images.")
        save_debug_image(binary_image, debug_dir, Path(image_path).stem + '_binarized.png')
        save_debug_image(filtered_image, debug_dir, Path(image_path).stem + '_filtered.png')
        save_debug_image(edges, debug_dir, Path(image_path).stem + '_edges.png')
        save_debug_image(debug_image, debug_dir, Path(image_path).stem + '_failure.png')
        
        return None
    except Exception as e:
        logging.exception("⚠️ Exception in black line detection:", exc_info=e)
        return None

def process_images(input_dir):
    """Processes images, detecting black lines and saving results in bookindabag.json."""
    logging.info("📖 Starting image processing...")
    
    bookindex_path = Path(input_dir) / "bookindex.json"
    bookindabag_path = Path(input_dir) / "bookindabag.json"
    debug_dir = Path(input_dir) / "debug"
    
    images = natsorted([f for f in os.listdir(input_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg'))], alg=ns.INT)
    
    if not images:
        logging.warning("⚠️ No images found in directory. Exiting process.")
        return
    
    bookindex = []
    if bookindex_path.exists():
        try:
            with open(bookindex_path, 'r', encoding='utf-8') as f:
                bookindex = json.load(f)
        except json.JSONDecodeError as e:
            logging.error(f"❌ ERROR: Invalid JSON format in {bookindex_path}: {e}")
            return
    
    debug_bookindex = []
    for entry in bookindex:
        new_entry = entry.copy()
        image_path = os.path.join(input_dir, entry.get('file', ''))
        page_type = entry.get('type', 'unknown')
        
        if not os.path.exists(image_path):
            logging.warning(f"⚠️ Image file not found: {image_path}")
            continue
        
        if page_type == "index":
            logging.info(f"⏭️ Skipping index page: {entry.get('file', '')}")
            new_entry['detected_separator_y'] = None
        else:
            new_entry['detected_separator_y'] = detect_black_lines(image_path, page_type, debug_dir)
        
        debug_bookindex.append(new_entry)
    
    with open(bookindabag_path, 'w', encoding='utf-8') as f:
        json.dump(debug_bookindex, f, indent=4)
    
    logging.info(f"✅ Debugging complete. Results saved to {bookindabag_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Directory containing images and JSON files")
    args = parser.parse_args()
    
    process_images(args.input)