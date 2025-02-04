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

def score_detection(y_positions, image_height, text_density):
    """Scores detection confidence based on line consistency, position, and text density."""
    if not y_positions:
        return 0
    mid_y = image_height // 2
    closest_to_mid = min(y_positions, key=lambda y: abs(y - mid_y))
    base_score = max(100 - abs(closest_to_mid - mid_y), 50)  # Higher confidence near center
    return min(base_score + text_density * 10, 100)  # Boost confidence if text is detected

def detect_text_below(image, separator_y):
    """Detects potential text regions below a given separator line."""
    height, width = image.shape
    roi = image[separator_y + 5: height - 10, :]
    binary_roi = cv2.adaptiveThreshold(roi, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 10)
    contours, _ = cv2.findContours(binary_roi, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    text_regions = [c for c in contours if 5 < cv2.boundingRect(c)[3] < 50]  # Filter small and large objects
    return len(text_regions)

def detect_black_lines(image_path, page_type, debug_dir):
    """Detects black separator lines using multiple strategies and self-evaluation."""
    logging.info(f"🔍 Processing {image_path} (Page Type: {page_type})")
    
    try:
        image = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if image is None:
            logging.error(f"❌ Skipping unreadable image: {image_path}")
            return None
        
        image_height, image_width = image.shape
        y_positions = []
        debug_images = {}
        
        # Strategy 1: Adaptive Thresholding + Morphology
        binary_adaptive = cv2.adaptiveThreshold(image, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 10)
        kernel = np.ones((2, 25), np.uint8)
        filtered_adaptive = cv2.morphologyEx(binary_adaptive, cv2.MORPH_OPEN, kernel)
        edges_adaptive = cv2.Canny(filtered_adaptive, 30 if page_type == "image-present" else 40, 150)
        debug_images['adaptive_edges'] = edges_adaptive
        
        # Strategy 2: Otsu’s Thresholding
        _, binary_otsu = cv2.threshold(image, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        edges_otsu = cv2.Canny(binary_otsu, 40, 150)
        debug_images['otsu_edges'] = edges_otsu
        
        # Detect lines using Hough Transform
        def find_lines(edges):
            lines = cv2.HoughLinesP(edges, 1, np.pi/180, 90, minLineLength=25, maxLineGap=6)
            detected_y = []
            if lines is not None:
                for line in lines:
                    x1, y1, x2, y2 = line[0]
                    if abs(y2 - y1) < 15 and (x2 - x1) < image_width * 0.6:
                        detected_y.append(y1)
            return detected_y
        
        y_positions.extend(find_lines(edges_adaptive))
        y_positions.extend(find_lines(edges_otsu))
        
        # Select the most confident Y position
        best_y = max(y_positions, key=y_positions.count, default=None)
        text_density = detect_text_below(image, best_y) if best_y else 0
        confidence = score_detection(y_positions, image_height, text_density)
        
        debug_image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        if best_y is not None:
            cv2.line(debug_image, (0, best_y), (image_width, best_y), (0, 255, 0), 2)
        
        for key, img in debug_images.items():
            save_debug_image(img, debug_dir, Path(image_path).stem + f'_{key}.png')
        save_debug_image(debug_image, debug_dir, Path(image_path).stem + '_final.png')
        
        return {"y": best_y, "confidence": confidence, "text_density": text_density}
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
            new_entry['detected_separator'] = None
        else:
            detection = detect_black_lines(image_path, page_type, debug_dir)
            new_entry['detected_separator'] = detection
        
        debug_bookindex.append(new_entry)
    
    with open(bookindabag_path, 'w', encoding='utf-8') as f:
        json.dump(debug_bookindex, f, indent=4)
    
    logging.info(f"✅ Debugging complete. Results saved to {bookindabag_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Directory containing images and JSON files")
    args = parser.parse_args()
    
    process_images(args.input)
