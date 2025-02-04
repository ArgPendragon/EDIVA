import json
import os
import cv2
import numpy as np
import logging
from pathlib import Path
import argparse
from natsort import natsorted, ns

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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
        image_width = image.shape[1]
        
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

def process_images(image_dir, bookindex_path):
    """Processes images, detecting black lines and updating bookindex.json."""
    logging.info("📖 Starting image processing...")
    
    bookindex_path = Path(bookindex_path)
    images = natsorted([f for f in os.listdir(image_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg'))], alg=ns.INT)
    
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
    
    for entry in bookindex:
        image_path = os.path.join(image_dir, entry.get('file', ''))
        if not os.path.exists(image_path):
            logging.warning(f"⚠️ Image file not found: {image_path}")
            continue
        
        black_line_y = detect_black_lines(image_path)
        if black_line_y is not None:
            entry['black_line_y'] = black_line_y
    
    with open(bookindex_path, 'w', encoding='utf-8') as f:
        json.dump(bookindex, f, indent=4)
    
    logging.info(f"✅ Processing complete. Results saved to {bookindex_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--images", required=True, help="Directory containing images")
    parser.add_argument("--json", required=True, help="Path to bookindex.json")
    args = parser.parse_args()
    
    process_images(args.images, args.json)
