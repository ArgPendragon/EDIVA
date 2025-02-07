import json
import os
import cv2
import numpy as np
import logging
import re
import argparse
import shutil
from pathlib import Path
from natsort import natsorted, ns

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# =============================================================================
# 1️⃣ Core Image Processing (Main Flow First)
# =============================================================================

def classify_page(image):
    """
    Classify a page based on whether an image is present.
    """
    if image is None or image.size == 0:
        logging.warning("Image not loaded correctly.")
        return "error"
    return "image-present" if detect_image_presence(image) else "image-absent"

def detect_image_configuration(image):
    """
    Determine the configuration (position) of the main image object on the page.
    Returns an English description.
    """
    bbox = get_largest_contour_bbox(image)
    if bbox is None:
        return None
    x, y, w, h = bbox
    img_h, img_w = image.shape[:2]
    
    left = x
    right = img_w - (x + w)
    top = y
    bottom = img_h - (y + h)

    if left < img_w * 0.1:
        config = "image on left"
    elif right < img_w * 0.1:
        config = "image on right"
    elif top < img_h * 0.1:
        config = "image at top"
    elif bottom < img_h * 0.1:
        config = "image at bottom"
    else:
        config = "centered image"

    logging.info(f"Detected configuration: {config} (x={x}, y={y}, w={w}, h={h})")
    return config

def get_largest_contour_bbox(image):
    """
    Return the bounding box of the largest contour in the image.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    largest = max(contours, key=cv2.contourArea)
    return cv2.boundingRect(largest)

def detect_caption_text(image, image_bbox, image_configuration):
    """
    Detect captions based on image position.
    - Runs internal caption detection (focused on the lower quarter of the image box).
    - If that region appears very dark/dense, it runs external detection as a backup.
    """
    logging.info(f"Running caption detection with image configuration: {image_configuration}")

    # Check if the lower region of the image box is dense (using updated parameters)
    dense_region = is_caption_region_dense(image, image_bbox, dark_threshold=160, density_cutoff=0.35)

    # Run internal caption detection first (scanning only the lower quarter)
    internal_candidate = detect_internal_caption_text(image, image_bbox, density_threshold=0.05, dark_threshold=50, density_boost=3)

    # If the region is dense or no internal caption was found, try external detection
    if dense_region or internal_candidate is None:
        external_candidate = detect_external_caption_text(image, image_bbox)
    else:
        external_candidate = None

    # Prepare results accordingly
    results = {}
    if internal_candidate is not None:
        results["internal_caption"] = enlarge_box(internal_candidate, image.shape, factor=0.05)
    if external_candidate is not None:
        results["external_caption"] = external_candidate

    # If both are detected, log a warning for manual validation
    if internal_candidate and external_candidate:
        logging.warning("Both internal and external captions detected. Cross-check required.")

    return results if results else None

# =============================================================================
# 2️⃣ Caption Detection Sub-functions
# =============================================================================

def detect_internal_caption_text(image, image_bbox, density_threshold=0.05, dark_threshold=50, density_boost=3):
    """
    Detect caption text within the lower part of the image bounding box.
    Only the bottom quarter is scanned to focus on potential captions.
    """
    x, y, w, h = image_bbox
    lower_region_start = y + int(0.75 * h)  # Bottom 25% of the image box
    region = image[lower_region_start: y + h, x: x + w]

    if region.size == 0:
        return None

    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    local_dark_density = compute_region_dark_density(region, dark_threshold=dark_threshold)

    # Adjust detection threshold based on darkness.
    effective_threshold = density_threshold if local_dark_density < 0.8 else density_threshold * density_boost
    logging.info(f"Internal region mean intensity: {np.mean(gray):.1f}, Effective threshold: {effective_threshold:.3f}")

    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    dilated = cv2.dilate(binary, kernel, iterations=1)

    text_area = np.sum(dilated == 255)
    density = text_area / (dilated.shape[0] * dilated.shape[1])
    logging.info(f"Internal text density: {density:.3f}")

    if density >= effective_threshold:
        contours, _ = cv2.findContours(dilated.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            candidate_box_local = merge_boxes([cv2.boundingRect(cnt) for cnt in contours])
            if candidate_box_local:
                candidate_box = (candidate_box_local[0] + x,
                                 candidate_box_local[1] + lower_region_start,
                                 candidate_box_local[2],
                                 candidate_box_local[3])
                logging.info(f"Internal caption candidate: {candidate_box}")
                return candidate_box

    logging.info("No robust internal caption detected.")
    return None

def detect_external_caption_text(image, image_bbox, initial_fraction=0.05, max_fraction=0.07, step_fraction=0.015):
    """
    Scans below the detected image for external caption text.
    Gradually expands the search region (starting small) until text boxes are found.
    """
    x, y, w, h = image_bbox
    base_y = y + h  # Start scanning immediately below the image

    region_height = int(initial_fraction * image.shape[0])
    max_region_height = int(max_fraction * image.shape[0])
    step = int(step_fraction * image.shape[0])

    candidate_box = None
    while region_height <= max_region_height:
        region = image[base_y: base_y + region_height, x: x + w]
        candidate_boxes = find_text_boxes(region, offset=(x, base_y))
        if candidate_boxes:
            candidate_box = merge_boxes(candidate_boxes)
        else:
            break
        region_height += step  # Expand the search downward

    if candidate_box:
        return {"caption_position": "below", "caption_box": enlarge_box(candidate_box, image.shape, factor=0.025)}

    return None  # No external caption detected

# =============================================================================
# 3️⃣ Image Analysis Utilities
# =============================================================================

def detect_image_presence(image):
    """
    Determine if an image contains sufficient content (non-empty).
    Uses adaptive thresholding and contour area checks.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY_INV, 11, 2)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    total_area = sum(cv2.contourArea(c) for c in contours)
    page_area = gray.shape[0] * gray.shape[1]
    filtered = [c for c in contours if cv2.contourArea(c) > 3000]
    large = [c for c in filtered if cv2.contourArea(c) > 10000]
    return (total_area / page_area > 0.10) or (len(large) > 0)

def is_caption_region_dense(image, image_bbox, dark_threshold=100, density_cutoff=0.3):
    """
    Check if the lower part of the detected image box is dense enough based on dark pixel density.
    Here we focus on the bottom 25% of the image bounding box.
    """
    x, y, w, h = image_bbox
    lower_region_start = y + int(0.75 * h)
    lower_region = image[lower_region_start: y + h, x: x + w]

    if lower_region.size == 0:
        return False

    density = compute_region_dark_density(lower_region, dark_threshold=dark_threshold)
    logging.info(f"Caption region density: {density:.3f} (cutoff: {density_cutoff})")
    return density > density_cutoff

def detect_black_lines(image_path):
    """
    Detect horizontal black lines (for example, page separators)
    by processing the image at the given path.
    (The original logic is preserved here.)
    """
    logging.info(f"Processing {image_path} for separator line detection")
    try:
        image = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if image is None:
            logging.error(f"Skipping unreadable image: {image_path}")
            return None
        binary_image = cv2.adaptiveThreshold(image, 255,
                                             cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                             cv2.THRESH_BINARY_INV, 15, 10)
        kernel = np.ones((2, 25), np.uint8)
        filtered = cv2.morphologyEx(binary_image, cv2.MORPH_OPEN, kernel)
        edges = cv2.Canny(filtered, 20, 100)
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, 70,
                                minLineLength=20, maxLineGap=5)
        detected_y = None
        if lines is not None:
            for line in lines:
                x1, y1, x2, y2 = line[0]
                if abs(y2 - y1) < 15 and (x2 - x1) < image.shape[1] * 0.4:
                    if detected_y is None or y1 > detected_y:
                        detected_y = y1
        return int(detected_y) if detected_y is not None else None
    except Exception as e:
        logging.exception("Exception in black line detection:", exc_info=e)
        return None

def save_debug_reticle(image_path, debug_dir, image_bbox, image_configuration, caption_data=None):
    """
    Save a debug image with drawn bounding boxes for the main image,
    caption regions, and any detected separators.
    """
    image = cv2.imread(image_path)
    if image is None:
        return
    if image_bbox is not None:
        x, y, w, h = image_bbox
        cv2.rectangle(image, (x, y), (x + w, y + h), (0, 0, 255), 2)
        cv2.putText(image, f"Image: {x},{y},{w},{h}", (x, max(y - 10, 10)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
    sep_y = detect_black_lines(image_path)
    if sep_y is not None:
        cv2.line(image, (0, sep_y), (image.shape[1], sep_y), (255, 0, 0), 2)
    cv2.putText(image, f"Classification: {image_configuration}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)
    if caption_data is not None:
        if "caption_box" in caption_data:
            cx, cy, cw, ch = caption_data["caption_box"]
            cv2.rectangle(image, (cx, cy), (cx + cw, cy + ch), (0, 255, 0), 2)
            cv2.putText(image, "Caption: within", (cx, cy - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        elif "internal_caption" in caption_data or "external_caption" in caption_data:
            internal = caption_data.get("internal_caption")
            external = caption_data.get("external_caption")
            if internal is not None:
                ix, iy, iw, ih = internal
                cv2.rectangle(image, (ix, iy), (ix + iw, iy + ih), (0, 255, 0), 2)
                cv2.putText(image, "Internal", (ix, iy - 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            if external is not None and "caption_box" in external:
                ex, ey, ew, eh = external["caption_box"]
                cv2.rectangle(image, (ex, ey), (ex + ew, ey + eh), (0, 200, 200), 2)
                cv2.putText(image, "External", (ex, ey - 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 200), 1)
    cv2.imwrite(os.path.join(debug_dir, os.path.basename(image_path)), image)
    logging.info(f"Debug image saved to: {os.path.join(debug_dir, os.path.basename(image_path))}")

# =============================================================================
# 4️⃣ Data Handling
# =============================================================================

def determine_page_number(index, intro_pages):
    """
    Determine the page number based on the index and number of introductory pages.
    """
    return index - intro_pages if index > intro_pages else None

def ensure_json_exists(json_file, image_dir, intro_pages=12):
    """
    Ensure that the JSON index file exists.
    If not, create it using the images in the provided directory.
    """
    json_file = Path(json_file)
    images = natsorted([f for f in os.listdir(image_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg'))], alg=ns.INT)
    if not images:
        logging.warning("No images found in the directory.")
        return
    if not json_file.exists():
        logging.warning(f"{json_file} not found. Creating bookindex.json.")
        bookindex = [{
            "file": img,
            "type": "pending",
            "page_number": determine_page_number(i + 1, intro_pages),
            "page_type": "index" if i + 1 <= intro_pages else "main"
        } for i, img in enumerate(images)]
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(bookindex, f, indent=4)

def process_images(image_dir, bookindex_path, intro_pages=12):
    """
    High-level function that wraps the processing of all images.
    """
    logging.info("Starting image processing...")

    ensure_json_exists(bookindex_path, image_dir, intro_pages)
    debug_dir = os.path.join(image_dir, "debug")
    if os.path.exists(debug_dir):
        shutil.rmtree(debug_dir)
    os.makedirs(debug_dir)

    try:
        with open(bookindex_path, 'r', encoding='utf-8') as f:
            bookindex = json.load(f)
    except json.JSONDecodeError as e:
        logging.error(f"Invalid JSON format in {bookindex_path}: {e}")
        return

    for index, entry in enumerate(bookindex, start=1):
        image_path = os.path.join(image_dir, entry.get('file', ''))
        if not os.path.exists(image_path):
            logging.warning(f"Image file not found: {image_path}")
            continue

        image = cv2.imread(image_path)
        entry['type'] = classify_page(image)
        entry['page_number'] = determine_page_number(index, intro_pages)

        # Always detect and store the separator y-coordinate regardless of page type.
        sep_y = detect_black_lines(image_path)
        entry['separator_y'] = sep_y  # This will be an integer or None.

        if entry['type'] == "image-present":
            image_config = detect_image_configuration(image)
            entry['image_configuration'] = image_config

            bbox = get_largest_contour_bbox(image)
            if bbox:
                # Store image coordinates as a dictionary.
                entry['image_coordinates'] = {"x": bbox[0], "y": bbox[1], "w": bbox[2], "h": bbox[3]}
                
                # Pass the image configuration to caption detection.
                caption_data = detect_caption_text(image, bbox, image_config)

                if caption_data:
                    if "internal_caption" in caption_data or "external_caption" in caption_data:
                        entry['internal_caption_coordinates'] = caption_data.get("internal_caption")
                        external_caption = caption_data.get("external_caption")
                        entry['external_caption_coordinates'] = external_caption.get("caption_box") if external_caption else None
                    else:
                        entry['caption_coordinates'] = caption_data.get("caption_box")
                        entry['caption_position'] = caption_data.get("caption_position")
                else:
                    entry['caption_coordinates'] = None
                    entry['caption_position'] = None

                save_debug_reticle(image_path, debug_dir, bbox, image_config, caption_data)
            else:
                logging.info(f"No bounding box detected for image: {image_path}")

    with open(bookindex_path, 'w', encoding='utf-8') as f:
        json.dump(bookindex, f, indent=4)

    logging.info(f"Processing completed. Results saved in {bookindex_path}")

# =============================================================================
# 5️⃣ Helper Functions (Support Logic)
# =============================================================================

def compute_region_dark_density(region, dark_threshold=50):
    """
    Compute local dark density within a given region.
    Pixels with intensity below `dark_threshold` are considered dark.
    """
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    dark_pixels = np.sum(gray < dark_threshold)
    density = dark_pixels / gray.size
    logging.info(f"Local dark density: {density:.3f}")
    return density

def merge_boxes(boxes):
    """
    Merge a list of bounding boxes into one bounding box.
    """
    if not boxes:
        return None
    x_min = min(b[0] for b in boxes)
    y_min = min(b[1] for b in boxes)
    x_max = max(b[0] + b[2] for b in boxes)
    y_max = max(b[1] + b[3] for b in boxes)
    return (x_min, y_min, x_max - x_min, y_max - y_min)

def enlarge_box(box, image_shape, factor=0.05):
    """
    Enlarge a bounding box by a given factor, ensuring the box remains within image bounds.
    """
    x, y, w, h = box
    img_h, img_w = image_shape[:2]
    dx = int(w * factor)
    dy = int(h * factor)
    new_x = max(x - dx, 0)
    new_y = max(y - dy, 0)
    new_w = min(w + 2 * dx, img_w - new_x)
    new_h = min(h + 2 * dy, img_h - new_y)
    return (new_x, new_y, new_w, new_h)

def validate_caption_box_quick(image, box, min_components=2, area_ratio_threshold=0.001):
    """
    Quickly validate a caption box by checking contour components and aspect ratio.
    """
    x, y, w, h = box
    roi = image[y:y + h, x:x + w]
    if roi.size == 0:
        return False
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    valid = [cnt for cnt in contours if cv2.contourArea(cnt) > (w * h * area_ratio_threshold)]
    aspect_ratio = w / float(h)
    return (2 <= aspect_ratio <= 15) and (len(valid) >= min_components)

def find_text_boxes(region, offset=(0, 0)):
    """
    Find text boxes within a region by detecting contours in an adaptive thresholded image.
    The offset is added to the detected coordinates.
    """
    boxes = []
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY_INV, 11, 2)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    dilated = cv2.dilate(binary, kernel, iterations=1)
    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for cnt in contours:
        bx, by, bw, bh = cv2.boundingRect(cnt)
        if bw > 10 and bh > 5 and bh < region.shape[0] * 0.5:
            boxes.append((bx + offset[0], by + offset[1], bw, bh))
    return boxes if boxes else None

# =============================================================================
# 6️⃣ Script Execution
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--images", required=True, help="Directory containing the images")
    parser.add_argument("--json", help="Path to bookindex.json (optional, default: images directory)")
    parser.add_argument("--intro_pages", type=int, default=12, help="Number of introductory pages before main content")
    args = parser.parse_args()
    image_dir = args.images
    json_file = args.json if args.json else os.path.join(image_dir, "bookindex.json")
    process_images(image_dir, json_file, args.intro_pages)
