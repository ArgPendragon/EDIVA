#!/usr/bin/env python3
"""
Debug Version of the Full Layout Script

This script processes JSON page definitions and image files exactly like the original,
including the intermediate whitening step and candidate-area calculation. In debug mode
(activated with --debug) the script overlays colored outlines on each page that show:
  - The “free” text area (dashed black outline)
  - The exclusion areas (red outlines)
  - Each candidate text area produced by subtracting the exclusions (green outlines, labeled "Candidate N")
  - The final chosen candidate areas (blue outlines, labeled "Chosen N")

Usage example:
    python debug_full_layout.py --input ./input_folder --output final_debug.pdf --last-text-page 493 --debug
"""

import os
import sys
import json
import logging
import argparse
import tempfile
import re

from reportlab.pdfgen import canvas
from reportlab.lib.colors import red, green, blue, black
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase.pdfmetrics import stringWidth

# For PDF -> image conversion (requires pdf2image and Poppler)
from pdf2image import convert_from_path

# For optimized geometric operations using shapely
from shapely.geometry import box
from shapely.ops import unary_union

# ------------------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------------------
DPI = 150
CONVERSION_FACTOR = 72 / DPI  # Convert pixels to points
FIXED_PAGE_SIZE = (576, 720)  # width x height in points

# ==============================================================================
# 1. TEXT DRAWING FUNCTIONS (Mostly Unmodified)
# ==============================================================================

def draw_adaptive_text(pdf, text, area, max_font_size=10, font_name="Times-Roman",
                       line_spacing=2, min_font_size=6, alignment="left", headers=None, capitolo=None):
    pdf.setFillColorRGB(0, 0, 0)
    x, y, width, height = area

    # --- Spacing constants ---
    BLANK_LINE = min_font_size
    HEADER_FONT_INCREMENT = 2
    CAP_TOP_SPACE = 15
    CAP_INTER_SPACE = 5
    CAP_BOTTOM_SPACE = 15

    header_set = set()
    if headers:
        for h in headers:
            if isinstance(h, dict):
                header_set.add(h.get("text", "").strip().lower())
            else:
                header_set.add(h.strip().lower())

    def required_height(font_size):
        total = 0
        if capitolo:
            cap_num_font = font_size + 4
            total += CAP_TOP_SPACE + cap_num_font + CAP_INTER_SPACE
            cap_title_font = font_size + 2
            cap_title = capitolo.get("titolo", "")
            cap_title_lines = simpleSplit(cap_title, "Times-Bold", cap_title_font, width - 4)
            total += len(cap_title_lines) * (cap_title_font + line_spacing) + CAP_BOTTOM_SPACE
            total += BLANK_LINE
        for line in text.split("\n"):
            sline = line.strip()
            if sline == "":
                total += font_size
            elif headers and sline.lower() in header_set:
                header_font = font_size + HEADER_FONT_INCREMENT
                total += font_size + header_font + font_size + line_spacing
            else:
                wrapped_lines = simpleSplit(sline, font_name, font_size, width - 4)
                total += len(wrapped_lines) * (font_size + line_spacing)
        return total

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
    overflow_lines = []

    if capitolo:
        cap_num_font = chosen_font_size + 4
        if current_y - CAP_TOP_SPACE - cap_num_font < y:
            return text
        current_y -= CAP_TOP_SPACE
        pdf.setFont("Times-Bold", cap_num_font)
        cap_num_text = capitolo.get("numero", "")
        pdf.drawCentredString(x + width/2, current_y - cap_num_font, cap_num_text)
        current_y -= (cap_num_font + CAP_INTER_SPACE)
        cap_title_font = chosen_font_size + 2
        pdf.setFont("Times-Bold", cap_title_font)
        cap_title = capitolo.get("titolo", "")
        cap_title_lines = simpleSplit(cap_title, "Times-Bold", cap_title_font, width - 4)
        for line in cap_title_lines:
            if current_y - cap_title_font < y:
                return text
            pdf.drawCentredString(x + width/2, current_y - cap_title_font, line)
            current_y -= (cap_title_font + line_spacing)
        current_y -= CAP_BOTTOM_SPACE
        if current_y - chosen_font_size < y:
            return text
        current_y -= chosen_font_size
        pdf.setFont(font_name, chosen_font_size)

    text_lines = text.split("\n")
    i_line = 0
    while i_line < len(text_lines):
        line = text_lines[i_line]
        sline = line.strip()
        if sline == "":
            if current_y - chosen_font_size < y:
                overflow_lines.extend(text_lines[i_line:])
                return "\n".join(overflow_lines)
            current_y -= chosen_font_size
            i_line += 1
            continue
        if headers and sline.lower() in header_set:
            header_font = chosen_font_size + HEADER_FONT_INCREMENT
            if current_y - (chosen_font_size + header_font + chosen_font_size + line_spacing) < y:
                overflow_lines.extend(text_lines[i_line:])
                return "\n".join(overflow_lines)
            current_y -= chosen_font_size
            pdf.setFont("Times-Bold", header_font)
            pdf.drawCentredString(x + width/2, current_y - header_font, sline)
            current_y -= (header_font + chosen_font_size + line_spacing)
            pdf.setFont(font_name, chosen_font_size)
        else:
            wrapped_lines = simpleSplit(sline, font_name, chosen_font_size, width - 4)
            for j, wline in enumerate(wrapped_lines):
                if current_y - (chosen_font_size + line_spacing) < y:
                    remaining_wrapped = wrapped_lines[j:]
                    overflow_lines.append(" ".join(remaining_wrapped))
                    for k in range(i_line+1, len(text_lines)):
                        overflow_lines.append(text_lines[k])
                    return "\n".join(overflow_lines)
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
        i_line += 1
    return ""

from reportlab.platypus import Paragraph, Frame, KeepInFrame
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY

def draw_formatted_text(pdf, html, area, base_font_size=10, min_font_size=6, alignment="justify"):
    available_width, available_height = area[2], area[3]
    if available_width <= 0 or available_height <= 0:
        return

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        raise ImportError("BeautifulSoup is required for formatted text. Install it with: pip install beautifulsoup4")
    
    # Choose alignment based solely on the parameter, not any JSON "position"
    if alignment == "justify":
        normal_align = TA_JUSTIFY
    elif alignment == "center":
        normal_align = TA_CENTER
    else:
        normal_align = TA_LEFT

    normal_style = ParagraphStyle(
        name="Normal",
        fontName="Times-Roman",
        fontSize=base_font_size,
        leading=base_font_size * 1.2,
        spaceBefore=base_font_size / 2,
        spaceAfter=base_font_size / 2,
        alignment=normal_align
    )
    header_style = ParagraphStyle(
        name="Header",
        fontName="Times-Bold",
        fontSize=base_font_size + 2,
        leading=(base_font_size + 2) * 1.2,
        spaceBefore=base_font_size / 2,
        spaceAfter=base_font_size / 2,
        alignment=TA_CENTER
    )

    soup = BeautifulSoup(html, "html.parser")
    paragraphs = []
    # For each paragraph in the HTML, decide on the style solely based on the tags.
    for p_tag in soup.find_all("p"):
        content = p_tag.decode_contents().strip()
        if p_tag.find("center"):
            # The presence of a center tag makes it a header.
            for center_tag in p_tag.find_all("center"):
                center_tag.unwrap()
            content = p_tag.decode_contents().strip()
            paragraphs.append((content, header_style))
        else:
            paragraphs.append((content, normal_style))
    if not paragraphs:
        for part in html.strip().split("\n\n"):
            part = part.strip()
            if part:
                paragraphs.append((part, normal_style))
    
    flowables = [Paragraph(text, style) for text, style in paragraphs]
    total_height = sum(flowable.wrap(available_width, available_height)[1] for flowable in flowables)
    
    current_size = base_font_size
    while total_height > available_height and current_size > min_font_size:
        current_size -= 0.5
        normal_style.fontSize = current_size
        normal_style.leading = current_size * 1.2
        header_style.fontSize = current_size + 2
        header_style.leading = (current_size + 2) * 1.2
        flowables = []
        for text, style in paragraphs:
            if style.name == "Header":
                flowables.append(Paragraph(text, header_style))
            else:
                flowables.append(Paragraph(text, normal_style))
        total_height = sum(flowable.wrap(available_width, available_height)[1] for flowable in flowables)
    
    if total_height <= available_height:
        frame = Frame(area[0], area[1], available_width, available_height, showBoundary=0)
        frame.addFromList(flowables, pdf)
    else:
        kif = KeepInFrame(available_width, available_height, flowables, mode='shrink')
        kif.wrapOn(pdf, available_width, available_height)
        kif.drawOn(pdf, area[0], area[1])

# ==============================================================================
# 2. GEOMETRIC HELPER FUNCTIONS
# ==============================================================================

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
    Iteratively subtracts a list of exclusion rectangles from full_area.
    Returns candidate rectangles (x, y, w, h) that do not overlap any exclusion.
    After subtraction, small pieces are filtered out.
    (Note: lowered min height from 30 to 25 points.)
    """
    candidates = [full_area]
    for ex in exclusions:
        new_candidates = []
        for cand in candidates:
            new_candidates.extend(subtract_rect(cand, ex))
        candidates = new_candidates
    page_width = full_area[2]
    candidates = [r for r in candidates if r[2] >= page_width/4 and r[3] >= 25]
    return candidates

def subtract_rectangles_optimized(full_area, exclusions):
    free_poly = box(full_area[0], full_area[1],
                    full_area[0] + full_area[2], full_area[1] + full_area[3])
    exclusion_polys = []
    for ex in exclusions:
        ex_poly = box(ex[0], ex[1], ex[0] + ex[2], ex[1] + ex[3])
        ex_poly = ex_poly.intersection(free_poly)
        if not ex_poly.is_empty:
            exclusion_polys.append(ex_poly)
    if exclusion_polys:
        union_exclusions = unary_union(exclusion_polys)
        diff = free_poly.difference(union_exclusions)
    else:
        diff = free_poly

    candidate_areas = []
    if diff.is_empty:
        return candidate_areas
    if diff.geom_type == 'Polygon':
        minx, miny, maxx, maxy = diff.bounds
        candidate_areas.append((minx, miny, maxx - minx, maxy - miny))
    elif diff.geom_type == 'MultiPolygon':
        for poly in diff.geoms:
            minx, miny, maxx, maxy = poly.bounds
            candidate_areas.append((minx, miny, maxx - minx, maxy - miny))
    return candidate_areas

# ==============================================================================
# 3. DATA LOADING AND MERGE FUNCTIONS
# ==============================================================================

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

# ==============================================================================
# 4. SHAPELY POLYGON DRAWING FUNCTIONS
# ==============================================================================

def fill_shapely_poly(pdf, poly):
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
    if poly.is_empty:
        return
    if poly.geom_type == 'Polygon':
        fill_shapely_poly(pdf, poly)
    elif poly.geom_type == 'MultiPolygon':
        for subpoly in poly.geoms:
            fill_shapely_poly(pdf, subpoly)

# ==============================================================================
# 5. PAGE LAYOUT FUNCTION WITH DEBUG OVERLAYS
# ==============================================================================

def layout_page(pdf, page, images_dir, page_width, page_height, last_text_page, temp_dir, initial_overflow="", debug=False):
    """
    Processes a page in two steps:
      STEP 1: Intermediate whitening – draws the background image and whited-out areas,
              preserving image areas and the bottom.
      STEP 2: Candidate area calculation, text overlay, and caption handling.
    
    In debug mode, the free text area, exclusion areas, candidate areas and chosen areas
    are drawn with colored outlines for visual inspection.
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
        return ""

    # ----- STEP 1: INTERMEDIATE WHITENING -----
    whitened_pdf_path = os.path.join(temp_dir, f"whitened_page_{page_num:03d}.pdf")
    c_whiten = canvas.Canvas(whitened_pdf_path, pagesize=(page_width, page_height))
    
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
    
    sep_y = page.get("separator_y") or 1350
    sep_y_pt = sep_y * CONVERSION_FACTOR
    y_cutoff = page_height - sep_y_pt

    bottom_poly = box(0, 0, page_width, y_cutoff)
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
    
    keep_areas = [bottom_poly] + image_keep_boxes
    union_keep = unary_union(keep_areas)
    full_page_poly = box(0, 0, page_width, page_height)
    white_mask = full_page_poly.difference(union_keep)
    fill_poly(c_whiten, white_mask)
    
    c_whiten.showPage()
    c_whiten.save()

    try:
        whitened_img_path = os.path.join(temp_dir, f"whitened_page_{page_num:03d}.png")
        images = convert_from_path(whitened_pdf_path, dpi=DPI)
        if images:
            images[0].save(whitened_img_path, "PNG")
            logging.debug(f"Generated whitened image: {whitened_img_path}")
        else:
            logging.error(f"No image generated from {whitened_pdf_path}")
            whitened_img_path = None
    except Exception as e:
        logging.error(f"Error converting {whitened_pdf_path} to image: {e}")
        whitened_img_path = None

    # ----- STEP 2: TEXT AREA CALCULATION & TEXT OVERLAY -----
    if whitened_img_path and os.path.exists(whitened_img_path):
        pdf.drawImage(whitened_img_path, 0, 0, width=page_width, height=page_height, preserveAspectRatio=True)
    else:
        logging.warning("Whitened image not available; drawing text over current background.")

    # Define the free text area (above the separator so as not to cover the bottom area)
    margin = 70
    padding = 10
    free_area_text = (
        margin,
        y_cutoff + padding,
        page_width - 2 * margin,
        (page_height - margin) - (y_cutoff + padding)
    )
    logging.debug(f"Free text area: {free_area_text}")

    # In debug mode, draw the free area outline (dashed black)
    pdf.setDash(3, 3)
    pdf.setStrokeColor(black)
    pdf.rect(free_area_text[0], free_area_text[1], free_area_text[2], free_area_text[3], fill=0)
    pdf.setDash()

    # Compute exclusion areas around images and captions.
    exclusion_margin = 5
    exclusions_text = []
    for poly in image_keep_boxes:
        minx, miny, maxx, maxy = poly.bounds
        exclusions_text.append((
            minx - exclusion_margin,
            miny - exclusion_margin,
            (maxx - minx) + 2 * exclusion_margin,
            (maxy - miny) + 2 * exclusion_margin
        ))
    for cap in caption_coords_list:
        x_cap, new_y_cap, w_cap, h_cap = cap
        exclusions_text.append((
            x_cap - exclusion_margin,
            new_y_cap - exclusion_margin,
            w_cap + 2 * exclusion_margin,
            h_cap + 2 * exclusion_margin
        ))
    logging.debug(f"Exclusion areas: {exclusions_text}")
    
    # In debug mode, draw each exclusion area in red.
    for ex in exclusions_text:
        pdf.setStrokeColor(red)
        pdf.rect(ex[0], ex[1], ex[2], ex[3], fill=0)

    # Determine candidate text areas by subtracting exclusions from the free area.
    candidate_areas = subtract_rectangles_strict(free_area_text, exclusions_text)
    logging.debug(f"Candidate text areas after filtering: {candidate_areas}")

    # In debug mode, draw candidate areas (green) with labels.
    for i, cand in enumerate(candidate_areas, start=1):
        pdf.setStrokeColor(green)
        pdf.setLineWidth(1)
        pdf.rect(cand[0], cand[1], cand[2], cand[3], fill=0)
        pdf.drawString(cand[0] + 2, cand[1] + cand[3] - 10, f"Candidate {i}")

    # --- NEW LAYOUT LOGIC ---
    if len(candidate_areas) == 1:
        # If only one candidate is found, use it as the chosen area.
        chosen_areas = candidate_areas
    elif image_keep_boxes:
        free_area_width = free_area_text[2]
        full_threshold = free_area_width * 0.9  # candidate is "full width" if its width is ≥90% of free area
        full_candidates = []
        short_candidates = []
        for area in candidate_areas:
            if area[2] >= full_threshold:
                full_candidates.append(area)
            else:
                short_candidates.append(area)
        if full_candidates and short_candidates:
            full_candidate = max(full_candidates, key=lambda a: a[3])
            short_candidate = max(short_candidates, key=lambda a: a[3])
            full_bottom = full_candidate[1]
            full_top = full_candidate[1] + full_candidate[3]
            short_bottom = short_candidate[1]
            short_top = short_candidate[1] + short_candidate[3]
            # Updated merging logic: make the short candidate "snap" to the full candidate's boundary.
            if full_top <= short_bottom:
                # Full candidate is entirely below short: adjust short so its lower boundary equals full_top.
                extended_short_candidate = (short_candidate[0], full_top, short_candidate[2], short_top - full_top)
            elif short_top <= full_bottom:
                # Full candidate is entirely above short: adjust short so its top equals full_bottom.
                extended_short_candidate = (short_candidate[0], short_bottom, short_candidate[2], full_bottom - short_bottom)
            else:
                # If they overlap, take the union of their vertical extents.
                unified_bottom = min(full_bottom, short_bottom)
                unified_top = max(full_top, short_top)
                extended_short_candidate = (short_candidate[0], unified_bottom, short_candidate[2], unified_top - unified_bottom)
            chosen_areas = [full_candidate, extended_short_candidate]
        elif full_candidates:
            chosen_areas = [max(full_candidates, key=lambda a: a[3])]
        elif short_candidates:
            chosen_areas = [max(short_candidates, key=lambda a: a[3])]
        else:
            chosen_areas = [free_area_text]
    else:
        chosen_areas = candidate_areas if candidate_areas else [free_area_text]

    logging.debug(f"Chosen candidate areas for text: {chosen_areas}")

    # In debug mode, overlay chosen candidate areas in blue.
    pdf.setLineWidth(3)
    for i, area in enumerate(chosen_areas, start=1):
        pdf.setStrokeColor(blue)
        pdf.rect(area[0], area[1], area[2], area[3], fill=0)
        pdf.drawString(area[0] + 2, area[1] + area[3] - 10, f"Chosen {i}")

    # Draw text into the chosen candidate areas.
    text_content = (initial_overflow + " " + page.get("content", "")).strip()
    overflow = ""
    if page.get("new_formatting_applied", False):
        draw_formatted_text(pdf, text_content, chosen_areas[0], base_font_size=10, alignment="justify")
    else:
        if len(chosen_areas) == 1:
            overflow = draw_adaptive_text(pdf, text_content, chosen_areas[0],
                                          max_font_size=10, alignment="justify",
                                          headers=page.get("headers", None),
                                          capitolo=page.get("capitolo", None))
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
                    draw_adaptive_text(pdf, col_text, area, max_font_size=12, alignment="justify",
                                       headers=page.get("headers", None),
                                       capitolo=page.get("capitolo", None))
    
    # ----- CAPTION HANDLING -----
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
                caption_area = (x_cap, new_y_cap, w_cap, h_cap)
                if page.get("new_formatting_applied", False):
                    draw_formatted_text(pdf, cap_text_str, caption_area, base_font_size=10, alignment="center")
                else:
                    draw_adaptive_text(pdf, cap_text_str, caption_area, max_font_size=10, alignment="center",
                                       headers=page.get("headers", None))
        else:
            x_cap = float(cap_coords[0]) * CONVERSION_FACTOR
            y_cap_raw = float(cap_coords[1]) * CONVERSION_FACTOR
            w_cap = float(cap_coords[2]) * CONVERSION_FACTOR
            h_cap = float(cap_coords[3]) * CONVERSION_FACTOR
            new_y_cap = page_height - (y_cap_raw + h_cap)
            caption_text = captions[0]
            if isinstance(caption_text, dict):
                caption_text = caption_text.get('text', '')
            caption_area = (x_cap, new_y_cap, w_cap, h_cap)
            if page.get("new_formatting_applied", False):
                draw_formatted_text(pdf, caption_text, caption_area, base_font_size=10, alignment="center")
            else:
                draw_adaptive_text(pdf, caption_text, caption_area, max_font_size=10, alignment="center",
                                   headers=page.get("headers", None))

    pdf.showPage()
    return overflow

# ==============================================================================
# 6. PDF AND IMAGE GENERATION FUNCTIONS
# ==============================================================================

def create_temp_page_pdf(page, images_dir, output_filename, page_width, page_height, last_text_page, temp_dir, initial_overflow="", debug=False):
    c = canvas.Canvas(output_filename, pagesize=(page_width, page_height))
    overflow = layout_page(c, page, images_dir, page_width, page_height, last_text_page, temp_dir, initial_overflow=initial_overflow, debug=debug)
    c.save()
    logging.debug(f"Created temporary PDF: {output_filename}")
    return overflow

def generate_preparatory_images(pages, images_dir, temp_dir, page_width, page_height, last_text_page, debug=False):
    temp_image_files = []
    overflow_text = ""
    for i, page in enumerate(pages):
        temp_pdf_path = os.path.join(temp_dir, f"page_{i:03d}.pdf")
        overflow_text = create_temp_page_pdf(page, images_dir, temp_pdf_path, page_width, page_height, last_text_page, temp_dir, initial_overflow=overflow_text, debug=debug)
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
    c = canvas.Canvas(output_pdf, pagesize=(page_width, page_height))
    for img in image_files:
        c.drawImage(img, 0, 0, width=page_width, height=page_height, preserveAspectRatio=True)
        c.showPage()
    c.save()
    logging.info(f"Final PDF generated: {output_pdf}")

# ==============================================================================
# 7. MAIN FUNCTION
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Generates the final PDF from page images. In debug mode, candidate text areas are overlayed for inspection."
    )
    parser.add_argument("--input", required=False, default=".", help="Input folder (default: current directory)")
    parser.add_argument("--output", required=False, default="final.pdf", help="Output PDF filename (default: final.pdf)")
    parser.add_argument("--last-text-page", type=int, default=493, help="Last page number containing text (pages after this are unchanged)")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode to overlay candidate rectangles")
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
        temp_image_files = generate_preparatory_images(merged_pages, input_folder, temp_dir, page_width, page_height, args.last_text_page, debug=args.debug)
        create_final_pdf_from_images(temp_image_files, output_pdf_path, page_width, page_height)

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    main()
