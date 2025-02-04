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

def save_debug_image(image: np.ndarray, debug_dir: str, filename: str) -> None:
    """Saves an image for debugging purposes in the debug directory."""
    try:
        os.makedirs(debug_dir, exist_ok=True)
        cv2.imwrite(os.path.join(debug_dir, filename), image)
    except Exception as e:
        logging.error(f"❌ Error saving debug image {filename}: {e}")

def ocr_below_separator(image: np.ndarray, y_coord: int) -> bool:
    """Performs OCR below the detected separator and checks if there is readable text."""
    height, width = image.shape[:2]
    roi_start = min(y_coord + 10, height)  # Start OCR region slightly below the separator
    roi = image[roi_start:min(roi_start + 40, height), :]
    
    text = pytesseract.image_to_string(roi, config='--psm 6')
    return bool(text.strip())

def detect_black_lines(image_path: str, debug_dir: str) -> Optional[dict]:
    """Detects black separator lines in an image using multiple strategies."""
    logging.info(f"🔍 Processing {image_path}")
    try:
        image = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if image is None:
            logging.error(f"❌ Skipping unreadable image: {image_path}")
            return None

        detection_results = {
            "adaptive": {"y": None, "confidence": 0.0},
            "otsu": {"y": None, "confidence": 0.0},
            "fallback": {"y": None, "confidence": 0.0}
        }

        debug_images = {}
        kernel = np.ones((2, 30), np.uint8)

        # Adaptive Thresholding
        binary_adaptive = cv2.adaptiveThreshold(image, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 10)
        morph_adaptive = cv2.morphologyEx(binary_adaptive, cv2.MORPH_OPEN, kernel)
        edges_adaptive = cv2.Canny(morph_adaptive, 50, 150)
        lines_adaptive = cv2.HoughLinesP(edges_adaptive, 1, np.pi/180, 80, minLineLength=30, maxLineGap=8)
        debug_images['adaptive'] = morph_adaptive

        # Otsu's Thresholding
        _, binary_otsu = cv2.threshold(image, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        morph_otsu = cv2.morphologyEx(binary_otsu, cv2.MORPH_OPEN, kernel)
        edges_otsu = cv2.Canny(morph_otsu, 50, 150)
        lines_otsu = cv2.HoughLinesP(edges_otsu, 1, np.pi/180, 80, minLineLength=30, maxLineGap=8)
        debug_images['otsu'] = morph_otsu

        # Fallback detection (Projection method)
        horizontal_projection = np.sum(image < 128, axis=1)  # Count black pixels per row
        fallback_y = np.argmax(horizontal_projection) if np.max(horizontal_projection) > width * 0.5 else None
        detection_results['fallback'] = {"y": fallback_y, "confidence": 0.5} if fallback_y is not None else {"y": None, "confidence": 0.0}

        for name, img in debug_images.items():
            save_debug_image(img, debug_dir, f"{os.path.basename(image_path)}_{name}.jpg")

        # Extract Y-coordinates
        for method, lines in zip(["adaptive", "otsu"], [lines_adaptive, lines_otsu]):
            if lines is not None:
                for line in lines:
                    x1, y1, x2, y2 = line[0]
                    if abs(y2 - y1) < 15:
                        detection_results[method] = {"y": y1, "confidence": 0.8}
                        if ocr_below_separator(image, y1):
                            detection_results[method]['confidence'] += 0.1  # OCR reinforcement

        best_method = max(detection_results, key=lambda k: detection_results[k]["confidence"])
        best_result = detection_results[best_method]
        
        return {
            "best_method": best_method,
            "detected_separator_y": best_result["y"],
            "confidence_score": best_result["confidence"],
            "alternative_detections": {k: v["y"] for k, v in detection_results.items() if v["y"] is not None}
        }
    except Exception as e:
        logging.exception("⚠️ Exception in black line detection:", exc_info=e)
        return None

def process_images(image_dir: str, bookindex_path: str):
    """Processes images, detecting black lines and storing results in a separate JSON report."""
    logging.info("📖 Starting image processing...")
    
    bookindex_path = Path(bookindex_path)
    debug_dir = os.path.join(image_dir, "debug")
    detection_report = {}

    images = natsorted(
        [f for f in os.listdir(image_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg'))],
        alg=ns.INT
    )
    
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
        
        detection = detect_black_lines(image_path, debug_dir)
        if detection:
            detection_report[entry['file']] = detection
    
    detection_report_path = os.path.join(image_dir, "detection_report.json")
    with open(detection_report_path, 'w', encoding='utf-8') as f:
        json.dump(detection_report, f, indent=4)
    
    logging.info(f"✅ Processing complete. Debug data saved to {detection_report_path} and {debug_dir}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--images", required=True, help="Directory containing images")
    parser.add_argument("--json", required=True, help="Path to bookindex.json")
    args = parser.parse_args()
    
    process_images(args.images, args.json)
