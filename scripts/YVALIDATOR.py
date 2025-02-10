#!/usr/bin/env python3
import os
import sys
import json
import cv2
import logging
import argparse

# Basic logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Target dimensions for image resizing
TARGET_WIDTH = 1200
TARGET_HEIGHT = 900

# Custom exception to abort the review process
class ExitReviewException(Exception):
    pass

def safe_destroy_window(win_name):
    """Destroys the given window if it exists."""
    try:
        if cv2.getWindowProperty(win_name, cv2.WND_PROP_VISIBLE) >= 1:
            cv2.destroyWindow(win_name)
    except Exception:
        pass

def manual_separator_selection(image, window_name="Separator Selection",
                               max_width=TARGET_WIDTH, max_height=TARGET_HEIGHT,
                               default_separator=None, display_img=None, scale=None):
    """
    Allows the manual selection/confirmation of a horizontal separator line (the y-coordinate).
    
    If a default_separator (in original image coordinates) is provided, it is drawn in blue.
    The user may click anywhere on the displayed image to update the separator line.
    
    Press 's' to save the selection (which returns the y-coordinate in original image space)
    or 'q' to exit the review process.
    """
    # Compute display_img and scale if not provided
    if display_img is None or scale is None:
        orig_h, orig_w = image.shape[:2]
        if orig_w > max_width or orig_h > max_height:
            scale = min(max_width / orig_w, max_height / orig_h)
            display_img = cv2.resize(image, (int(orig_w * scale), int(orig_h * scale)))
        else:
            scale = max(max_width / orig_w, max_height / orig_h)
            display_img = cv2.resize(image, (int(orig_w * scale), int(orig_h * scale)),
                                     interpolation=cv2.INTER_LINEAR)
    clone = display_img.copy()
    selected_y = None

    # If a default separator is provided, draw it in blue
    if default_separator is not None:
        default_y_disp = int(default_separator * scale)
        selected_y = default_y_disp
        cv2.line(display_img, (0, default_y_disp), (display_img.shape[1], default_y_disp), (255, 0, 0), 2)
        cv2.putText(display_img, "Default separator_y (s to accept, click to change)", 
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 2)
        clone = display_img.copy()
    
    # Draw instructions on the image
    instructions = "Click to set separator line, press 's' to save, 'q' to quit"
    cv2.putText(display_img, instructions, (10, display_img.shape[0] - 10), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 2)
    clone = display_img.copy()

    def mouse_callback(event, x, y, flags, param):
        nonlocal selected_y, clone, display_img
        if event == cv2.EVENT_LBUTTONDOWN:
            selected_y = y
            # Update the displayed image with a new green horizontal line
            display_img = clone.copy()
            cv2.line(display_img, (0, y), (display_img.shape[1], y), (0, 255, 0), 2)
            cv2.putText(display_img, instructions, (10, display_img.shape[0] - 10), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 2)
            cv2.imshow(window_name, display_img)

    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.moveWindow(window_name, 100, 100)
    cv2.imshow(window_name, display_img)
    cv2.setMouseCallback(window_name, mouse_callback)

    print(f"In the window '{window_name}', click to set the separator line and press 's' to save or 'q' to exit review.")
    while True:
        key = cv2.waitKey(1) & 0xFF
        if key == ord('s'):
            safe_destroy_window(window_name)
            if selected_y is None:
                # If no selection was made and a default exists, use the default
                if default_separator is not None:
                    return default_separator
                else:
                    return None
            # Convert the displayed y coordinate back to the original image coordinate
            original_y = int(selected_y / scale)
            return original_y
        elif key == ord('q'):
            safe_destroy_window(window_name)
            raise ExitReviewException

def review_separator_pages(json_path, images_dir):
    """
    Reads the JSON file and, for every page (regardless of type) that has not yet had its
    separator_y validated (i.e. the flag "separator_manual_confirmed" is not set), allows the user to
    manually confirm or adjust the separator_y coordinate.
    
    The updated coordinate (in pixels) and the flag "separator_manual_confirmed" are saved back into the JSON.
    """
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            pages = json.load(f)
    except Exception as e:
        logging.error(f"Error loading {json_path}: {e}")
        sys.exit(1)
    
    # Count all pages that require separator validation (regardless of type)
    total = sum(1 for p in pages if not p.get("separator_manual_confirmed", False))
    processed = 0

    try:
        for page in pages:
            if page.get("separator_manual_confirmed", False):
                logging.info(f"Page {page.get('file', 'unknown')} already validated for separator_y, skipping.")
                continue

            image_file = page.get("file")
            if not image_file:
                logging.warning("Page without an image file, skipping.")
                continue

            image_path = os.path.join(images_dir, image_file)
            image = cv2.imread(image_path)
            if image is None:
                logging.warning(f"Unable to read image: {image_path}")
                continue

            processed += 1
            remaining = total - processed
            print(f"\n--- Reviewing separator_y for page {processed}/{total}: {image_file} ---")
            print(f"Pages remaining: {remaining}")

            orig_h, orig_w = image.shape[:2]
            # Resize the image for display purposes
            if orig_w < TARGET_WIDTH or orig_h < TARGET_HEIGHT:
                scale = max(TARGET_WIDTH / orig_w, TARGET_HEIGHT / orig_h)
                display_img = cv2.resize(image, (int(orig_w * scale), int(orig_h * scale)),
                                         interpolation=cv2.INTER_LINEAR)
            elif orig_w > TARGET_WIDTH or orig_h > TARGET_HEIGHT:
                scale = min(TARGET_WIDTH / orig_w, TARGET_HEIGHT / orig_h)
                display_img = cv2.resize(image, (int(orig_w * scale), int(orig_h * scale)),
                                         interpolation=cv2.INTER_AREA)
            else:
                scale = 1.0
                display_img = image.copy()

            window_name = "Separator Review"
            cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
            cv2.moveWindow(window_name, 100, 100)
            cv2.imshow(window_name, display_img)

            # Use the page's current separator_y as the default (if available)
            default_separator = page.get("separator_y")
            print("Select separator_y. Click to set new position, press 's' to confirm, or 'q' to quit review.")
            selected_separator = manual_separator_selection(image, window_name=window_name,
                                                            display_img=display_img, scale=scale,
                                                            default_separator=default_separator)
            if selected_separator is None:
                print("No separator_y selected. Skipping this page.")
                safe_destroy_window(window_name)
                continue
            logging.info(f"separator_y for {image_file}: {selected_separator}")
            page["separator_y"] = selected_separator
            page["separator_manual_confirmed"] = True

            safe_destroy_window(window_name)
            print("Page separator_y validated. Proceeding to next...")
            cv2.waitKey(100)
    except ExitReviewException:
        print("Review interrupted by the user. Saving progress...")

    try:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(pages, f, indent=4)
        logging.info(f"JSON updated and saved to: {json_path}")
    except Exception as e:
        logging.error(f"Error saving JSON: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Interactive tool to manually validate the separator_y coordinate for pages in the JSON.\n"
                    "Pages already validated (flag 'separator_manual_confirmed' true) are skipped.\n"
                    "Click to set the separator line and press 's' to confirm, or 'q' to exit review."
    )
    parser.add_argument("--json", required=True, help="Path to the JSON file (e.g. bookindex.json)")
    parser.add_argument("--images", required=True, help="Directory containing images")
    args = parser.parse_args()

    review_separator_pages(args.json, args.images)
