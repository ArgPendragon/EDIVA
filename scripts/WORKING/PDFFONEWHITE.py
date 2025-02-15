#!/usr/bin/env python3
"""
Whitening Step Script

This script processes page definitions and image files, performs an intermediate
whitening (“bleaching”) step (i.e. it draws a white mask over parts of the page),
and saves the output images (PNG) in a subfolder called 'bleachedimages'.
It uses the JSON files "bookindex.json" and "godstarita.json" from the input folder,
merges them, and then processes each page.

Usage:
    python whiten_images.py --input ./input_folder --last-text-page 493
"""

import os
import sys
import json
import logging
import argparse

from reportlab.pdfgen import canvas
from shapely.geometry import box
from shapely.ops import unary_union
from pdf2image import convert_from_path

# ------------------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------------------
DPI = 150
CONVERSION_FACTOR = 72 / DPI  # convert pixels to points
FIXED_PAGE_SIZE = (576, 720)  # width x height in points

# ------------------------------------------------------------------------------
# JSON LOADING & MERGE FUNCTIONS
# ------------------------------------------------------------------------------

def load_pages(json_path: str) -> list:
    """Loads the JSON file and returns the list of pages."""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            pages = json.load(f)
        logging.info(f"Loaded {len(pages)} pages from {json_path}")
        return pages
    except Exception as e:
        logging.error(f"Error loading JSON '{json_path}': {e}")
        sys.exit(1)

def merge_data(original: list, translation: list, last_text_page: int) -> list:
    """
    Merges two JSON lists based on "page_number".
    Pages with page_number None or > last_text_page remain unchanged.
    Otherwise, if a matching translation exists, merge it.
    """
    merged = []
    translation_dict = {entry["page_number"]: entry for entry in translation if entry.get("page_number") is not None}
    for orig in original:
        page_num = orig.get("page_number")
        if page_num is None or (isinstance(page_num, int) and page_num > last_text_page):
            merged.append(orig)
        else:
            if page_num in translation_dict:
                merged_entry = orig.copy()
                merged_entry.update(translation_dict[page_num])
                merged.append(merged_entry)
            else:
                merged.append(orig)
    return merged

# ------------------------------------------------------------------------------
# GEOMETRIC HELPER FUNCTION
# ------------------------------------------------------------------------------

def fill_poly(pdf, poly):
    """
    Given a ReportLab canvas and a Shapely polygon,
    draws (fills) the polygon on the canvas.
    """
    if poly.is_empty:
        return
    path = pdf.beginPath()
    exterior_coords = list(poly.exterior.coords)
    path.moveTo(*exterior_coords[0])
    for coord in exterior_coords[1:]:
        path.lineTo(*coord)
    path.close()
    for interior in poly.interiors:
        interior_coords = list(interior.coords)
        path.moveTo(*interior_coords[0])
        for coord in interior_coords[1:]:
            path.lineTo(*coord)
        path.close()
    pdf.drawPath(path, fill=1, stroke=0)

# ------------------------------------------------------------------------------
# WHITENING PROCESS FOR A SINGLE PAGE
# ------------------------------------------------------------------------------

def process_page_whitening(page, images_dir, output_dir, page_width, page_height, last_text_page):
    """
    Processes one page by:
      - Drawing the original image as background.
      - If the page is within the text range (page_number ≤ last_text_page), applying
        the whitening mask over areas outside the "keep" regions (e.g. the bottom and
        any image or caption areas).
      - Converting the result from a PDF into a PNG file stored in output_dir.
    """
    page_num = page.get("page_number")
    image_file = page.get("file")
    if not image_file:
        logging.warning("No image file specified for page.")
        return

    # Determine output filenames (both PDF and PNG)
    if page_num is not None:
        pdf_filename = os.path.join(output_dir, f"whitened_page_{int(page_num):03d}.pdf")
        output_filename = os.path.join(output_dir, f"whitened_page_{int(page_num):03d}.png")
    else:
        pdf_filename = os.path.join(output_dir, "whitened_page_unknown.pdf")
        output_filename = os.path.join(output_dir, "whitened_page_unknown.png")

    # Create a canvas for the PDF page.
    c = canvas.Canvas(pdf_filename, pagesize=(page_width, page_height))

    # Draw the original image as background.
    image_path = os.path.join(images_dir, image_file)
    if os.path.exists(image_path):
        c.drawImage(image_path, 0, 0, width=page_width, height=page_height,
                    preserveAspectRatio=True, mask='auto')
    else:
        logging.error(f"Image not found: {image_path}")
        return

    # If the page should be processed (i.e. it’s a text page), apply whitening.
    if page_num is not None and isinstance(page_num, int) and page_num <= last_text_page:
        # Use a separator (defaulting to 1350) to determine the area to keep at the bottom.
        sep_y = page.get("separator_y") or 1350
        sep_y_pt = sep_y * CONVERSION_FACTOR
        y_cutoff = page_height - sep_y_pt

        # Define the bottom area to keep.
        bottom_poly = box(0, 0, page_width, y_cutoff)

        # Also keep any image areas (if specified).
        image_keep_boxes = []
        ic = page.get("image_coordinates")
        if ic:
            if isinstance(ic, list):
                for one_ic in ic:
                    x_img = float(one_ic.get("x", 0)) * CONVERSION_FACTOR
                    y_img_raw = float(one_ic.get("y", 0)) * CONVERSION_FACTOR
                    w_img = float(one_ic.get("w", 0)) * CONVERSION_FACTOR
                    h_img = float(one_ic.get("h", 0)) * CONVERSION_FACTOR
                    new_y_img = page_height - (y_img_raw + h_img)
                    image_keep_boxes.append(box(x_img, new_y_img, x_img + w_img, new_y_img + h_img))
            elif isinstance(ic, dict):
                x_img = float(ic.get("x", 0)) * CONVERSION_FACTOR
                y_img_raw = float(ic.get("y", 0)) * CONVERSION_FACTOR
                w_img = float(ic.get("w", 0)) * CONVERSION_FACTOR
                h_img = float(ic.get("h", 0)) * CONVERSION_FACTOR
                new_y_img = page_height - (y_img_raw + h_img)
                image_keep_boxes.append(box(x_img, new_y_img, x_img + w_img, new_y_img + h_img))

        # Also keep any caption areas.
        caption_coords_list = []
        cap_coords = page.get("caption_coordinates")
        if cap_coords:
            if not isinstance(cap_coords[0], (list, tuple)):
                x_cap = float(cap_coords[0]) * CONVERSION_FACTOR
                y_cap_raw = float(cap_coords[1]) * CONVERSION_FACTOR
                w_cap = float(cap_coords[2]) * CONVERSION_FACTOR
                h_cap = float(cap_coords[3]) * CONVERSION_FACTOR
                new_y_cap = page_height - (y_cap_raw + h_cap)
                # Draw a white rectangle over the caption area.
                c.setFillColorRGB(1, 1, 1)
                c.rect(x_cap, new_y_cap, w_cap, h_cap, stroke=0, fill=1)
                caption_coords_list.append((x_cap, new_y_cap, w_cap, h_cap))
            else:
                for cap_area in cap_coords:
                    x_cap = float(cap_area[0]) * CONVERSION_FACTOR
                    y_cap_raw = float(cap_area[1]) * CONVERSION_FACTOR
                    w_cap = float(cap_area[2]) * CONVERSION_FACTOR
                    h_cap = float(cap_area[3]) * CONVERSION_FACTOR
                    new_y_cap = page_height - (y_cap_raw + h_cap)
                    c.setFillColorRGB(1, 1, 1)
                    c.rect(x_cap, new_y_cap, w_cap, h_cap, stroke=0, fill=1)
                    caption_coords_list.append((x_cap, new_y_cap, w_cap, h_cap))

        # Determine which areas to “keep” (i.e. not white out) and then compute the white mask.
        keep_areas = [bottom_poly] + image_keep_boxes
        union_keep = unary_union(keep_areas)
        full_page_poly = box(0, 0, page_width, page_height)
        white_mask = full_page_poly.difference(union_keep)
        c.setFillColorRGB(1, 1, 1)  # white
        fill_poly(c, white_mask)

    c.showPage()
    c.save()

    # Convert the PDF page to a PNG image.
    try:
        images = convert_from_path(pdf_filename, dpi=DPI)
        if images:
            images[0].save(output_filename, "PNG")
            logging.info(f"Generated whitened image: {output_filename}")
        else:
            logging.error(f"No image generated from {pdf_filename}")
    except Exception as e:
        logging.error(f"Error converting {pdf_filename} to image: {e}")

# ------------------------------------------------------------------------------
# MAIN FUNCTION
# ------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Perform the whitening step and store output images in a subfolder 'bleachedimages'."
    )
    parser.add_argument("--input", required=False, default=".", help="Input folder containing images and JSON files")
    parser.add_argument("--last-text-page", type=int, default=493, help="Last page number containing text")
    args = parser.parse_args()

    input_folder = os.path.abspath(args.input)
    # Assume the JSON files are named "bookindex.json" and "godstarita.json".
    bookindex_path = os.path.join(input_folder, "bookindex.json")
    translation_path = os.path.join(input_folder, "godstarita.json")
    original_data = load_pages(bookindex_path)
    translation_data = load_pages(translation_path)
    merged_pages = merge_data(original_data, translation_data, args.last_text_page)

    if not merged_pages:
        logging.error("No pages found in JSON data.")
        sys.exit(1)

    page_width, page_height = FIXED_PAGE_SIZE

    # Create (or use) the output folder 'bleachedimages'
    output_dir = os.path.join(input_folder, "bleachedimages")
    os.makedirs(output_dir, exist_ok=True)

    # Process each page.
    for page in merged_pages:
        process_page_whitening(page, input_folder, output_dir, page_width, page_height, args.last_text_page)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
