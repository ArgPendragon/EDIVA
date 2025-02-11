#!/usr/bin/env python3
import os
import sys
import json
import logging
import argparse
import tempfile
import re

from reportlab.pdfgen import canvas
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase.pdfmetrics import stringWidth

# For PDF -> image conversion (requires pdf2image and Poppler)
from pdf2image import convert_from_path

# For optimized geometric operations
from shapely.geometry import box
from shapely.ops import unary_union

# ------------------------------------------------------------------------------
# Logging configuration
# ------------------------------------------------------------------------------
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# ------------------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------------------
DPI = 150
CONVERSION_FACTOR = 72 / DPI  # conversion factor (assumes JSON coords are in pixels)
FIXED_PAGE_SIZE = (576, 720)  # width x height in points

# ------------------------------------------------------------------------------
# 1. FUNCTION: draw_adaptive_text
# ------------------------------------------------------------------------------
def draw_adaptive_text(pdf, text, area, max_font_size=10, font_name="Times-Roman",
                       line_spacing=2, min_font_size=6, alignment="left", headers=None, capitolo=None):
    """
    Draws text within the given area (x, y, w, h) on the canvas using dynamic font sizing.

    Special formatting:
      - If a 'capitolo' dict is provided, then the chapter header block is drawn first:
            * A centered, bold line (font size = chosen_font_size + 4) for the chapter number.
            * A centered, bold line (font size = chosen_font_size + 2) for the chapter title.
            * A blank line is added after the capitolo block.
      - Then the main text is processed line by line.
        Only lines that are fully capitalized (i.e. equal to their own upper-case version)
        and that (when compared case‑insensitively) match one of the header phrases from the "headers" field
        are treated as headers. In that case, the line is drawn in bold (with font size increased by 2) and centered,
        with a blank line inserted immediately above and below.
      - All other lines are wrapped and rendered normally (with justification if requested).

    The text color is reset to black at the start.
    """
    pdf.setFillColorRGB(0, 0, 0)
    x, y, width, height = area

    # --- Spacing constants ---
    BLANK_LINE = max_font_size  # height for a blank line
    HEADER_FONT_INCREMENT = 2
    CAP_TOP_SPACE = 15
    CAP_INTER_SPACE = 5
    CAP_BOTTOM_SPACE = 15

    # Build a set of header texts from the headers field (if provided)
    header_set = set()
    if headers:
        for h in headers:
            if isinstance(h, dict):
                header_set.add(h.get("text", "").strip())
            else:
                header_set.add(h.strip())

    # --- Function to compute the required total height ---
    def required_height(font_size):
        total = 0
        # Account for capitolo header block if provided.
        if capitolo:
            cap_num_font = font_size + 4
            total += CAP_TOP_SPACE + cap_num_font + CAP_INTER_SPACE
            cap_title_font = font_size + 2
            cap_title = capitolo.get("titolo", "")
            cap_title_lines = simpleSplit(cap_title, "Times-Bold", cap_title_font, width - 4)
            total += len(cap_title_lines) * (cap_title_font + line_spacing) + CAP_BOTTOM_SPACE
            total += BLANK_LINE  # blank line after capitolo header
        # Process each line of the main text.
        for line in text.split("\n"):
            sline = line.strip()
            if sline == "":
                total += font_size
            # Only treat fully capitalized lines that match one of the headers as header lines.
            elif headers and sline == sline.upper() and sline.lower() in {h.lower() for h in header_set}:
                header_font = font_size + HEADER_FONT_INCREMENT
                total += font_size      # blank line above header
                total += header_font + line_spacing  # header line height
                total += font_size      # blank line below header
            else:
                wrapped_lines = simpleSplit(sline, font_name, font_size, width - 4)
                total += len(wrapped_lines) * (font_size + line_spacing)
        return total

    # --- Binary search for the optimal font size ---
    lo = min_font_size
    hi = max_font_size
    tolerance = 0.1
    best = lo
    if required_height(hi) <= height:
        best = hi
    else:
        while hi - lo > tolerance:
            mid = (hi + lo) / 2.0
            if required_height(mid) <= height:
                best = mid
                lo = mid
            else:
                hi = mid
    chosen_font_size = best

    current_y = y + height
    pdf.setFont(font_name, chosen_font_size)

    # Draw the Capitolo header block, if provided.
    if capitolo:
        current_y -= CAP_TOP_SPACE
        cap_num_font = chosen_font_size + 4
        pdf.setFont("Times-Bold", cap_num_font)
        cap_num_text = capitolo.get("numero", "")
        pdf.drawCentredString(x + width/2, current_y - cap_num_font, cap_num_text)
        current_y -= (cap_num_font + CAP_INTER_SPACE)
        cap_title_font = chosen_font_size + 2
        pdf.setFont("Times-Bold", cap_title_font)
        cap_title = capitolo.get("titolo", "")
        for line in simpleSplit(cap_title, "Times-Bold", cap_title_font, width - 4):
            pdf.drawCentredString(x + width/2, current_y - cap_title_font, line)
            current_y -= (cap_title_font + line_spacing)
        current_y -= CAP_BOTTOM_SPACE
        # Add one blank line after the capitolo header.
        current_y -= chosen_font_size
        pdf.setFont(font_name, chosen_font_size)

    # Process the main text, line by line.
    for line in text.split("\n"):
        sline = line.strip()
        if sline == "":
            current_y -= chosen_font_size
            continue
        # Only treat a line as a header if it is fully capitalized and matches one of the header phrases.
        if headers and sline == sline.upper() and sline.lower() in {h.lower() for h in header_set}:
            # Insert a blank line above the header.
            current_y -= chosen_font_size
            header_font = chosen_font_size + HEADER_FONT_INCREMENT
            pdf.setFont("Times-Bold", header_font)
            pdf.drawCentredString(x + width/2, current_y - header_font, sline)
            # Insert a blank line below the header.
            current_y -= (header_font + chosen_font_size)
            pdf.setFont(font_name, chosen_font_size)
        else:
            wrapped_lines = simpleSplit(sline, font_name, chosen_font_size, width - 4)
            for j, wline in enumerate(wrapped_lines):
                if alignment == "justify" and j < len(wrapped_lines) - 1 and wline.strip():
                    words = wline.split()
                    if len(words) > 1:
                        total_words_width = sum(stringWidth(word, font_name, chosen_font_size) for word in words)
                        available_space = width - 4
                        extra_space = (available_space - total_words_width) / (len(words) - 1)
                        cur_x = x + 2
                        for k, word in enumerate(words):
                            pdf.drawString(cur_x, current_y - chosen_font_size, word)
                            cur_x += stringWidth(word, font_name, chosen_font_size)
                            if k < len(words) - 1:
                                cur_x += extra_space
                    else:
                        pdf.drawString(x + 2, current_y - chosen_font_size, wline)
                elif alignment == "center":
                    pdf.drawCentredString(x + width/2, current_y - chosen_font_size, wline)
                else:
                    pdf.drawString(x + 2, current_y - chosen_font_size, wline)
                current_y -= (chosen_font_size + line_spacing)

# ------------------------------------------------------------------------------
# 2. GEOMETRIC HELPER FUNCTIONS (unchanged)
# ------------------------------------------------------------------------------
def subtract_rect(cand, ex):
    """
    Subtracts rectangle 'ex' from rectangle 'cand'.
    Both are tuples (x, y, w, h). Returns a list of remaining rectangles.
    """
    cx, cy, cw, ch = cand
    ex_x, ex_y, ex_w, ex_h = ex

    inter_x = max(cx, ex_x)
    inter_y = max(cy, ex_y)
    inter_right = min(cx + cw, ex_x + ex_w)
    inter_top = min(cy + ch, ex_y + ex_h)

    if inter_x >= inter_right or inter_y >= inter_top:
        return [cand]

    remainders = []
    if inter_y > cy:
        remainders.append((cx, cy, cw, inter_y - cy))
    if inter_top < cy + ch:
        remainders.append((cx, inter_top, cw, (cy + ch) - inter_top))
    if inter_x > cx:
        remainders.append((cx, inter_y, inter_x - cx, inter_top - inter_y))
    if inter_right < cx + cw:
        remainders.append((inter_right, inter_y, (cx + cw) - inter_right, inter_top - inter_y))
    return remainders

def subtract_rectangles_strict(full_area, exclusions):
    """
    Iteratively subtracts a list of exclusion rectangles from the full_area rectangle.
    Returns a list of candidate rectangles (x, y, w, h) that are parts of full_area
    and do not overlap any exclusion rectangle.
    """
    candidates = [full_area]
    for ex in exclusions:
        new_candidates = []
        for cand in candidates:
            new_candidates.extend(subtract_rect(cand, ex))
        candidates = new_candidates
    # Filter out tiny pieces.
    candidates = [r for r in candidates if r[2] > 1 and r[3] > 1]
    return candidates

# ------------------------------------------------------------------------------
# 3. DATA LOADING AND MERGE FUNCTIONS (unchanged)
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
    Merges two JSON data lists based on "page_number":
      - Pages with page_number None or > last_text_page remain unchanged.
      - Otherwise, if a matching translation entry exists, merge it.
    """
    merged = []
    translation_dict = {entry["page_number"]: entry for entry in translation if entry.get("page_number") is not None}
    for orig in original:
        page_num = orig.get("page_number")
        if page_num is None or (isinstance(page_num, int) and page_num > last_text_page):
            logging.debug(f"Leaving page with page_number {page_num} unchanged")
            merged.append(orig)
        else:
            if page_num in translation_dict:
                merged_entry = orig.copy()
                merged_entry.update(translation_dict[page_num])
                logging.debug(f"Merged page {page_num}")
                merged.append(merged_entry)
            else:
                logging.debug(f"No translation found for page {page_num}")
                merged.append(orig)
    return merged

# ------------------------------------------------------------------------------
# 4. SHAPELY POLYGON DRAWING FUNCTIONS (unchanged)
# ------------------------------------------------------------------------------
def fill_shapely_poly(pdf, poly):
    """
    Draws a Shapely polygon 'poly' on the canvas filled in white,
    respecting any interior holes.
    """
    pdf.setFillColorRGB(1, 1, 1)
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

def fill_poly(pdf, poly):
    """
    Draws a Polygon or MultiPolygon on the canvas.
    """
    if poly.is_empty:
        return
    if poly.geom_type == 'Polygon':
        fill_shapely_poly(pdf, poly)
    elif poly.geom_type == 'MultiPolygon':
        for subpoly in poly.geoms:
            fill_shapely_poly(pdf, subpoly)

# ------------------------------------------------------------------------------
# 5. PAGE LAYOUT FUNCTION WITH INTERMEDIATE WHITENING, TEXT, AND CAPTION HANDLING
# ------------------------------------------------------------------------------
def layout_page(pdf, page, images_dir, page_width, page_height, last_text_page, temp_dir):
    """
    Processes a page in two steps.
    
    STEP 1: INTERMEDIATE WHITENING
      - Draws the background image.
      - Whitens everything EXCEPT:
          * the area below the separator, and
          * the image areas (which are preserved).
      - Caption areas (from "caption_coordinates") are always cleared.
      - The result is saved as a temporary PDF and converted to a PNG.
    
    STEP 2: CANDIDATE AREA CALCULATION, TEXT OVERLAY, AND CAPTION HANDLING
      - Uses the whitened image as the background.
      - Defines a free area (full page within margins, above the separator) and then subtracts:
          * the image areas, and
          * the caption areas.
      - The remaining area is used to place the main text.
      - Finally, caption text is drawn over cleared caption areas.
      
    Pages with page_number None or > last_text_page are left unchanged.
    """
    page_num = page.get("page_number")
    if page_num is None or (isinstance(page_num, int) and page_num > last_text_page):
        image_file = page.get("file")
        if image_file:
            image_path = os.path.join(images_dir, image_file)
            if os.path.exists(image_path):
                pdf.drawImage(image_path, 0, 0, width=page_width, height=page_height,
                              preserveAspectRatio=True, mask='auto')
            else:
                logging.warning(f"Image not found: {image_path}")
        else:
            logging.warning("No image file specified for unchanged page")
        pdf.showPage()
        return

    # ---------------------------
    # STEP 1: INTERMEDIATE WHITENING
    # ---------------------------
    whitened_pdf_path = os.path.join(temp_dir, f"whitened_page_{page_num:03d}.pdf")
    c_whiten = canvas.Canvas(whitened_pdf_path, pagesize=(page_width, page_height))
    
    # Draw the background image.
    image_file = page.get("file")
    if image_file:
        image_path = os.path.join(images_dir, image_file)
        if os.path.exists(image_path):
            c_whiten.drawImage(image_path, 0, 0, width=page_width, height=page_height,
                               preserveAspectRatio=True, mask='auto')
        else:
            logging.warning(f"Image not found: {image_path}")
    else:
        logging.warning("No image file specified for modified page")
    
    # Determine the separator in points.
    sep_y = page.get("separator_y") or 1350
    sep_y_pt = sep_y * CONVERSION_FACTOR
    # Keep everything BELOW the separator.
    y_cutoff = page_height - sep_y_pt

    # a) Define bottom area.
    bottom_poly = box(0, 0, page_width, y_cutoff)
    # b) Define image areas to preserve.
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
    
    # Combine bottom area and image areas as the regions to preserve.
    keep_areas = [bottom_poly] + image_keep_boxes
    union_keep = unary_union(keep_areas)
    full_page_poly = box(0, 0, page_width, page_height)
    # White out everything except the keep areas.
    white_mask = full_page_poly.difference(union_keep)
    fill_poly(c_whiten, white_mask)
    
    # Always clear (whiten) caption areas (from "caption_coordinates").
    caption_coords_list = []
    cap_coords = page.get("caption_coordinates")
    if cap_coords:
        if not isinstance(cap_coords[0], (list, tuple)):
            x_cap = float(cap_coords[0]) * CONVERSION_FACTOR
            y_cap_raw = float(cap_coords[1]) * CONVERSION_FACTOR
            w_cap = float(cap_coords[2]) * CONVERSION_FACTOR
            h_cap = float(cap_coords[3]) * CONVERSION_FACTOR
            new_y_cap = page_height - (y_cap_raw + h_cap)
            c_whiten.setFillColorRGB(1, 1, 1)
            c_whiten.rect(x_cap, new_y_cap, w_cap, h_cap, stroke=0, fill=1)
            caption_coords_list.append((x_cap, new_y_cap, w_cap, h_cap))
        else:
            for cap_area in cap_coords:
                x_cap = float(cap_area[0]) * CONVERSION_FACTOR
                y_cap_raw = float(cap_area[1]) * CONVERSION_FACTOR
                w_cap = float(cap_area[2]) * CONVERSION_FACTOR
                h_cap = float(cap_area[3]) * CONVERSION_FACTOR
                new_y_cap = page_height - (y_cap_raw + h_cap)
                c_whiten.setFillColorRGB(1, 1, 1)
                c_whiten.rect(x_cap, new_y_cap, w_cap, h_cap, stroke=0, fill=1)
                caption_coords_list.append((x_cap, new_y_cap, w_cap, h_cap))
    
    c_whiten.showPage()
    c_whiten.save()

    # Convert the whitened PDF to a PNG image.
    whitened_img_path = os.path.join(temp_dir, f"whitened_page_{page_num:03d}.png")
    try:
        images = convert_from_path(whitened_pdf_path, dpi=DPI)
        if images:
            images[0].save(whitened_img_path, "PNG")
            logging.debug(f"Generated whitened image: {whitened_img_path}")
        else:
            logging.error(f"No image generated from {whitened_pdf_path}")
    except Exception as e:
        logging.error(f"Error converting {whitened_pdf_path} to image: {e}")
        whitened_img_path = None

    # ---------------------------
    # STEP 2: CANDIDATE AREA CALCULATION & TEXT OVERLAY
    # ---------------------------
    if whitened_img_path and os.path.exists(whitened_img_path):
        pdf.drawImage(whitened_img_path, 0, 0, width=page_width, height=page_height, preserveAspectRatio=True)
    else:
        logging.warning("Whitened image not available; drawing text over current background.")

    # Define the free text area: full page within margins but above the preserved bottom.
    margin = 70
    padding = 10
    free_area_text = (margin,
                      y_cutoff + padding,
                      page_width - 2 * margin,
                      (page_height - margin) - (y_cutoff + padding))
    logging.debug(f"Free text area: {free_area_text}")

    # Add a margin around image and caption areas.
    exclusion_margin = 5  # 5 points margin

    # Exclusions for candidate text area: image areas with margin.
    exclusions_text = []
    for poly in image_keep_boxes:
        minx, miny, maxx, maxy = poly.bounds
        exclusions_text.append((
            minx - exclusion_margin,
            miny - exclusion_margin,
            (maxx - minx) + 2 * exclusion_margin,
            (maxy - miny) + 2 * exclusion_margin
        ))
    # Exclusions for candidate text area: caption areas with margin.
    for cap in caption_coords_list:
        x_cap, new_y_cap, w_cap, h_cap = cap
        exclusions_text.append((
            x_cap - exclusion_margin,
            new_y_cap - exclusion_margin,
            w_cap + 2 * exclusion_margin,
            h_cap + 2 * exclusion_margin
        ))

    logging.debug(f"Exclusion areas: {exclusions_text}")

    # Use strict iterative subtraction to get candidate text areas.
    candidate_areas = subtract_rectangles_strict(free_area_text, exclusions_text)
    logging.debug(f"Candidate text areas (strict subtraction): {candidate_areas}")

    # --- New: Filter out candidate areas that are too slim (minimum width is 1/3 of page width) ---
    candidate_areas = [area for area in candidate_areas if area[2] >= page_width / 3]
    logging.debug(f"Candidate text areas (after width filtering): {candidate_areas}")

    # --- Limit candidate areas to a maximum of 2 per page:
    #      - Prefer one candidate that spans nearly the full width of the free area.
    #      - Also choose one candidate with maximum area (if available). ---
    if candidate_areas:
        free_width = free_area_text[2]
        selected_candidates = []
        # Look for a candidate that spans at least 95% of the free area width.
        full_width_candidate = None
        for area in candidate_areas:
            if area[2] >= 0.95 * free_width:
                full_width_candidate = area
                break
        if full_width_candidate:
            selected_candidates.append(full_width_candidate)
        else:
            selected_candidates.append(max(candidate_areas, key=lambda a: a[2]))
        # From remaining candidates, choose one with maximum area.
        remaining_candidates = [area for area in candidate_areas if area not in selected_candidates]
        if remaining_candidates:
            second_candidate = max(remaining_candidates, key=lambda a: a[2]*a[3])
            selected_candidates.append(second_candidate)
        chosen_areas = selected_candidates[:2]
        # Optionally, clear the chosen candidate areas.
        for area in chosen_areas:
            pdf.setFillColorRGB(1, 1, 1)
            pdf.rect(area[0], area[1], area[2], area[3], stroke=0, fill=1)
    else:
        chosen_areas = [free_area_text]

    # Draw the main text in the candidate area(s).
    text_content = page.get("content", "")
    if len(chosen_areas) == 1:
        draw_adaptive_text(pdf, text_content, chosen_areas[0], min_font_size=10, max_font_size=12, alignment="justify",
                           headers=page.get("headers", None), capitolo=page.get("capitolo", None))
    else:
        words = text_content.split()
        ncols = len(chosen_areas)
        if ncols > 0:
            chunk_size = len(words) // ncols
            split_texts = []
            for i in range(ncols):
                if i == ncols - 1:
                    chunk_words = words[i * chunk_size:]
                else:
                    chunk_words = words[i * chunk_size:(i + 1) * chunk_size]
                split_texts.append(" ".join(chunk_words))
            for col_text, area in zip(split_texts, chosen_areas):
                draw_adaptive_text(pdf, col_text, area, min_font_size=8, max_font_size=12, alignment="justify",
                                   headers=page.get("headers", None), capitolo=page.get("capitolo", None))

    # ------------------------------------------------------------------------------
    # 2. Caption handling: clear caption areas and draw caption text.
    captions = page.get("captions", [])
    cap_coords = page.get("caption_coordinates")
    if captions and cap_coords:
        if isinstance(cap_coords[0], (list, tuple)):
            for cap_text, cap_area in zip(captions, cap_coords):
                if isinstance(cap_text, dict):
                    cap_text_str = cap_text.get('text', '')
                else:
                    cap_text_str = cap_text
                x_cap = float(cap_area[0]) * CONVERSION_FACTOR
                y_cap_raw = float(cap_area[1]) * CONVERSION_FACTOR
                w_cap = float(cap_area[2]) * CONVERSION_FACTOR
                h_cap = float(cap_area[3]) * CONVERSION_FACTOR
                new_y_cap = page_height - (y_cap_raw + h_cap)
                pdf.setFillColorRGB(1, 1, 1)
                pdf.rect(x_cap, new_y_cap, w_cap, h_cap, stroke=0, fill=1)
                caption_area = (x_cap, new_y_cap, w_cap, h_cap)
                draw_adaptive_text(pdf, cap_text_str, caption_area, max_font_size=10, alignment="center", headers=page.get("headers", None))
        else:
            x_cap = float(cap_coords[0]) * CONVERSION_FACTOR
            y_cap_raw = float(cap_coords[1]) * CONVERSION_FACTOR
            w_cap = float(cap_coords[2]) * CONVERSION_FACTOR
            h_cap = float(cap_coords[3]) * CONVERSION_FACTOR
            new_y_cap = page_height - (y_cap_raw + h_cap)
            pdf.setFillColorRGB(1, 1, 1)
            pdf.rect(x_cap, new_y_cap, w_cap, h_cap, stroke=0, fill=1)
            caption_text = captions[0]
            if isinstance(caption_text, dict):
                caption_text = caption_text.get('text', '')
            caption_area = (x_cap, new_y_cap, w_cap, h_cap)
            draw_adaptive_text(pdf, caption_text, caption_area, max_font_size=10, alignment="center", headers=page.get("headers", None))

    pdf.showPage()

# ------------------------------------------------------------------------------
# 6. PDF AND IMAGE GENERATION FUNCTIONS (unchanged)
# ------------------------------------------------------------------------------
def create_temp_page_pdf(page, images_dir, output_filename, page_width, page_height, last_text_page, temp_dir):
    """
    Creates a temporary PDF for a single page using the defined layout.
    """
    c = canvas.Canvas(output_filename, pagesize=(page_width, page_height))
    layout_page(c, page, images_dir, page_width, page_height, last_text_page, temp_dir)
    c.save()
    logging.debug(f"Created temporary PDF: {output_filename}")

def generate_preparatory_images(pages, images_dir, temp_dir, page_width, page_height, last_text_page):
    """
    For each page, creates a temporary PDF (using the two‐step layout) and converts it to a PNG.
    Returns a list of paths to the generated images.
    """
    temp_image_files = []
    for i, page in enumerate(pages):
        temp_pdf_path = os.path.join(temp_dir, f"page_{i:03d}.pdf")
        create_temp_page_pdf(page, images_dir, temp_pdf_path, page_width, page_height, last_text_page, temp_dir)
        try:
            images = convert_from_path(temp_pdf_path, dpi=DPI)
            if images:
                temp_img_path = os.path.join(temp_dir, f"page_{i:03d}.png")
                images[0].save(temp_img_path, "PNG")
                temp_image_files.append(temp_img_path)
                logging.debug(f"Generated preparatory image: {temp_img_path}")
            else:
                logging.error(f"No image generated from {temp_pdf_path}")
        except Exception as e:
            logging.error(f"Error converting {temp_pdf_path} to image: {e}")
    return temp_image_files

def create_final_pdf_from_images(image_files, output_pdf, page_width, page_height):
    """
    Creates the final PDF by inserting each preparatory image into a page.
    """
    c = canvas.Canvas(output_pdf, pagesize=(page_width, page_height))
    for img in image_files:
        c.drawImage(img, 0, 0, width=page_width, height=page_height, preserveAspectRatio=True)
        c.showPage()
    c.save()
    logging.info(f"Final PDF generated: {output_pdf}")

# ------------------------------------------------------------------------------
# 7. MAIN FUNCTION
# ------------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Generates the final PDF from page images. Pages with page_number None or > --last-text-page remain unchanged; others are processed in two steps: whitening then text and caption overlay."
    )
    parser.add_argument("--input", required=False, default=".", help="Input folder (default: current directory)")
    parser.add_argument("--output", required=False, default="final.pdf", help="Output PDF filename (default: final.pdf)")
    parser.add_argument("--last-text-page", type=int, default=493, help="Last page number containing text (pages after this are unchanged)")
    args = parser.parse_args()

    input_folder = os.path.abspath(args.input)
    bookindex_path = os.path.join(input_folder, "bookindex.json")
    translation_path = os.path.join(input_folder, "godstarita.json")
    original_data = load_pages(bookindex_path)
    translation_data = load_pages(translation_path)
    
    merged_pages = merge_data(original_data, translation_data, args.last_text_page)
    if not merged_pages:
        logging.error("No merged pages found from JSON data.")
        sys.exit(1)
    
    output_pdf_path = os.path.join(input_folder, args.output)
    page_width, page_height = FIXED_PAGE_SIZE

    with tempfile.TemporaryDirectory() as temp_dir:
        logging.info(f"Using temporary folder: {temp_dir}")
        temp_image_files = generate_preparatory_images(merged_pages, input_folder, temp_dir, page_width, page_height, args.last_text_page)
        create_final_pdf_from_images(temp_image_files, output_pdf_path, page_width, page_height)

if __name__ == "__main__":
    main()
