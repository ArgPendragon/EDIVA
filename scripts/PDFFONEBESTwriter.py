#!/usr/bin/env python3
"""
Final PDF Preparation Script

Important Variables:
    DPI: Resolution used to convert pixels to points.
    CONVERSION_FACTOR: Converts pixels (from images/JSON) to PDF points.
    FIXED_PAGE_SIZE: Tuple representing the fixed (width, height) of each PDF page in points.
    bleached_dir: The directory where bleached (background) images are stored.
    last_text_page: The page number cutoff; pages with text after this page number are treated as full-image pages.

This script reads page definitions (from bookindex.json and godstarita.json) and
uses the pre-generated bleached images from the "bleachedimages" subfolder. For
each page, it overlays text onto the bleached image using candidate text area calculations.
In debug mode, colored outlines are drawn for the free text area (dashed black),
candidate areas (green), and the chosen areas (blue).

Usage:
    python PDFFONEWRITER.py --input ./input_folder --output final.pdf --last-text-page 493 [--debug]
"""

import os
import sys
import json
import logging
import argparse
import re

from reportlab.pdfgen import canvas
from reportlab.lib.colors import red, green, blue, black
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase.pdfmetrics import stringWidth

# -------------------------------------------------------------------------------
# Constants
# -------------------------------------------------------------------------------
DPI = 150
CONVERSION_FACTOR = 72 / DPI  # converts pixels to points
FIXED_PAGE_SIZE = (576, 720)  # (width, height) in points

# -------------------------------------------------------------------------------
# HELPER FUNCTION FOR SPLITTING LONG PARAGRAPHS (with Sentence Completion)
# -------------------------------------------------------------------------------
def split_long_paragraphs(text, font_name, font_size, width, max_lines=9):
    """
    Splits overly long paragraphs into shorter ones by finishing sentences.
    It ensures that the wrapped text for a paragraph does not exceed `max_lines`
    by splitting the paragraph into sentences and accumulating them until the
    next sentence would cause the text to exceed the limit. If a single sentence
    is still too long, it falls back to an arbitrary split.
    """
    new_text = []
    for paragraph in text.split("\n"):
        wrapped_lines = simpleSplit(paragraph, font_name, font_size, width)
        if len(wrapped_lines) <= max_lines:
            new_text.append(paragraph)
        else:
            sentences = re.split(r'(?<=[.!?])\s+', paragraph)
            chunk = ""
            for sentence in sentences:
                candidate = sentence if not chunk else chunk + " " + sentence
                candidate_lines = simpleSplit(candidate, font_name, font_size, width)
                if len(candidate_lines) <= max_lines:
                    chunk = candidate
                else:
                    if chunk:
                        new_text.append(chunk)
                    sentence_lines = simpleSplit(sentence, font_name, font_size, width)
                    if len(sentence_lines) > max_lines:
                        for i in range(0, len(sentence_lines), max_lines):
                            new_text.append(" ".join(sentence_lines[i:i+max_lines]))
                        chunk = ""
                    else:
                        chunk = sentence
            if chunk:
                new_text.append(chunk)
    return "\n".join(new_text)

# -------------------------------------------------------------------------------
# HELPER FUNCTION FOR HTML PROCESSING
# -------------------------------------------------------------------------------
def process_html_content(html):
    """
    Processes HTML content to extract plain text and headers.
    Returns a tuple of (plain_text, headers_list).
    Here we consider text within <h1>, <h2>, <h3> tags or containing a <center> tag as headers.
    """
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    headers = []
    paragraphs = []
    for elem in soup.find_all(['h1', 'h2', 'h3', 'p', 'div']):
        if elem.name in ['h1', 'h2', 'h3'] or elem.find("center"):
            header_text = elem.get_text(strip=True)
            if header_text:
                headers.append(header_text.lower())
                paragraphs.append(header_text)
        else:
            text = elem.get_text(strip=True)
            if text:
                paragraphs.append(text)
    plain_text = "\n".join(paragraphs)
    return plain_text, headers

# -------------------------------------------------------------------------------
# TEXT DRAWING FUNCTION
# -------------------------------------------------------------------------------
def draw_adaptive_text(pdf, text, area, max_font_size=11, min_font_size=10, font_name="Times-Roman",
                       line_spacing=2, alignment="justify", headers=None, capitolo=None):
    """
    Draws text into a given area, automatically adjusting font size.
    Returns any overflow text that did not fit.
    
    For main text we force font size 10 by passing min_font_size==max_font_size==10.
    If alignment=="center", non-header lines are drawn centered.
    
    **New:** Long paragraphs are pre-split into smaller chunks (finishing sentences where possible)
    to avoid abrupt cuts.
    """
    pdf.setFillColorRGB(0, 0, 0)
    x, y, width, height = area

    text = split_long_paragraphs(text, font_name, max_font_size, width)

    BLANK_LINE = min_font_size * 2
    HEADER_FONT_INCREMENT = 2
    HEADER_EXTRA_SPACE = 6
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
            cap_num_font = font_size + 8
            total += CAP_TOP_SPACE + cap_num_font + CAP_INTER_SPACE
            cap_title_font = font_size + 4
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
                total += header_font + line_spacing
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
        cap_num_font = chosen_font_size + 10
        if current_y - HEADER_EXTRA_SPACE - cap_num_font < y:
            return text
        current_y -= HEADER_EXTRA_SPACE
        pdf.setFont("Times-Bold", cap_num_font)
        cap_num_text = capitolo.get("numero", "")
        pdf.drawCentredString(x + width/2, current_y - cap_num_font, cap_num_text)
        current_y -= (cap_num_font + CAP_INTER_SPACE)
        cap_title_font = chosen_font_size + 8
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
            if current_y - HEADER_EXTRA_SPACE - (header_font + line_spacing) < y:
                overflow_lines.extend(text_lines[i_line:])
                return "\n".join(overflow_lines)
            current_y -= HEADER_EXTRA_SPACE
            pdf.setFont("Times-Bold", header_font)
            pdf.drawCentredString(x + width/2, current_y - header_font, sline)
            current_y -= (header_font + line_spacing)
            pdf.setFont(font_name, chosen_font_size)
        else:
            available_width = width - 4
            wrapped_lines = simpleSplit(sline, font_name, chosen_font_size, available_width)
            def draw_fully_justified_line(text_line, x_start, y_position):
                words = text_line.split()
                if len(words) == 1:
                    pdf.drawString(x_start, y_position, text_line)
                    return
                total_words_width = sum(stringWidth(word, font_name, chosen_font_size) for word in words)
                normal_space_width = stringWidth(" ", font_name, chosen_font_size)
                gaps = len(words) - 1
                extra_space = (available_width - total_words_width - gaps * normal_space_width) / gaps
                current_x = x_start
                for idx, word in enumerate(words):
                    pdf.drawString(current_x, y_position, word)
                    current_x += stringWidth(word, font_name, chosen_font_size)
                    if idx < len(words) - 1:
                        current_x += normal_space_width + extra_space

            for j, wline in enumerate(wrapped_lines):
                if current_y - (chosen_font_size + line_spacing) < y:
                    remaining_wrapped = wrapped_lines[j:]
                    overflow_lines.append(" ".join(remaining_wrapped))
                    for k in range(i_line + 1, len(text_lines)):
                        overflow_lines.append(text_lines[k])
                    return "\n".join(overflow_lines)
                if alignment == "center":
                    pdf.drawCentredString(x + width/2, current_y - chosen_font_size, wline)
                elif alignment == "justify":
                    if j < len(wrapped_lines) - 1 and len(wline.split()) > 1:
                        draw_fully_justified_line(wline, x + 2, current_y - chosen_font_size)
                    else:
                        pdf.drawString(x + 2, current_y - chosen_font_size, wline)
                else:
                    pdf.drawString(x + 2, current_y - chosen_font_size, wline)
                current_y -= (chosen_font_size + line_spacing)
        i_line += 1
    return ""

# -------------------------------------------------------------------------------
# GEOMETRIC HELPER FUNCTIONS
# -------------------------------------------------------------------------------
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
    Filters out candidates that are too small.
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

# -------------------------------------------------------------------------------
# INDEX PAGES LOGIC (MODULAR)
# -------------------------------------------------------------------------------
def get_sorted_index_images(bleached_dir):
    """
    Scans the specified directory for images matching the pattern
    'image_<number>.jpg' and returns a sorted list of tuples (number, full_image_path).
    Uses a dictionary to deduplicate images by number.
    """
    pattern = re.compile(r'^image_(\d+)\.jpg$', re.IGNORECASE)
    index_images = {}  # key: number, value: full file path
    
    for file in os.listdir(bleached_dir):
        full_path = os.path.join(bleached_dir, file)
        if not os.path.isfile(full_path):
            continue
        match = pattern.match(file.strip())
        if match:
            num = int(match.group(1))
            if num in index_images:
                logging.warning("Duplicate image for number %d: %s (already using %s)", num, file, index_images[num])
            else:
                index_images[num] = full_path
        else:
            logging.debug("File %s did not match the index image pattern.", file)
    
    sorted_images = sorted(index_images.items(), key=lambda x: x[0])
    logging.info("Found %d index images.", len(sorted_images))
    return sorted_images

def add_index_pages(pdf, bleached_dir, page_width, page_height):
    """
    Adds index pages to the PDF from images in the bleached_dir.
    Each image is drawn on its own page.
    """
    index_images = get_sorted_index_images(bleached_dir)
    for num, image_path in index_images:
        logging.info("Adding index page for image number %d: %s", num, image_path)
        pdf.drawImage(image_path, 0, 0, width=page_width, height=page_height, preserveAspectRatio=True)
        pdf.showPage()

# -------------------------------------------------------------------------------
# FINAL PAGE LAYOUT FUNCTION (Using Bleached Images)
# -------------------------------------------------------------------------------
def layout_page(pdf, page, bleached_dir, page_width, page_height, last_text_page, initial_overflow="", debug=False):
    """
    Processes a page by loading its bleached image from bleached_dir, then overlaying text.
    Main text is drawn only if the page has non-empty content and is within the text range.
    Full-image pages (or pages beyond last_text_page) skip main text (preserving overflow)
    but captions are always processed.
    """
    page_num = page.get("page_number")
    logging.info("Processing page: %s", page_num)
    
    if page_num is not None and isinstance(page_num, int):
        bleached_filename = os.path.join(bleached_dir, f"whitened_page_{int(page_num):03d}.png")
    else:
        bleached_filename = os.path.join(bleached_dir, "whitened_page_unknown.png")
    logging.debug("Using bleached image file: %s", bleached_filename)

    if os.path.exists(bleached_filename):
        pdf.drawImage(bleached_filename, 0, 0, width=page_width, height=page_height, preserveAspectRatio=True)
    else:
        logging.warning("Bleached image not found: %s", bleached_filename)
    
    main_text = page.get("content", "").strip()
    if main_text and (page_num is not None and isinstance(page_num, int) and page_num <= last_text_page):
        margin = 70
        padding = 3
        sep_y = page.get("separator_y") or 1350
        sep_y_pt = sep_y * CONVERSION_FACTOR
        y_cutoff = page_height - sep_y_pt
        free_area_text = (
            margin,
            y_cutoff + padding,
            page_width - 2 * margin,
            (page_height - margin) - (y_cutoff + padding)
        )
        logging.debug("Free text area calculated as: %s", free_area_text)

        if debug:
            pdf.setDash(3, 3)
            pdf.setStrokeColor(black)
            pdf.rect(free_area_text[0], free_area_text[1], free_area_text[2], free_area_text[3], fill=0)
            pdf.setDash()

        exclusion_margin = 5
        exclusions_text = []
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
                    image_keep_boxes.append((x_img, new_y_img, w_img, h_img))
            elif isinstance(ic, dict):
                x_img = float(ic.get("x", 0)) * CONVERSION_FACTOR
                y_img_raw = float(ic.get("y", 0)) * CONVERSION_FACTOR
                w_img = float(ic.get("w", 0)) * CONVERSION_FACTOR
                h_img = float(ic.get("h", 0)) * CONVERSION_FACTOR
                new_y_img = page_height - (y_img_raw + h_img)
                image_keep_boxes.append((x_img, new_y_img, w_img, h_img))
        for ex in image_keep_boxes:
            exclusions_text.append((
                ex[0] - exclusion_margin,
                ex[1] - exclusion_margin,
                ex[2] + 2 * exclusion_margin,
                ex[3] + 2 * exclusion_margin
            ))
        caption_coords_list = []
        cap_coords = page.get("caption_coordinates")
        if cap_coords:
            if not isinstance(cap_coords[0], (list, tuple)):
                x_cap = float(cap_coords[0]) * CONVERSION_FACTOR
                y_cap_raw = float(cap_coords[1]) * CONVERSION_FACTOR
                w_cap = float(cap_coords[2]) * CONVERSION_FACTOR
                h_cap = float(cap_coords[3]) * CONVERSION_FACTOR
                new_y_cap = page_height - (y_cap_raw + h_cap)
                exclusions_text.append((
                    x_cap - exclusion_margin,
                    new_y_cap - exclusion_margin,
                    w_cap + 2 * exclusion_margin,
                    h_cap + 2 * exclusion_margin
                ))
                caption_coords_list.append((x_cap, new_y_cap, w_cap, h_cap))
            else:
                for cap_area in cap_coords:
                    x_cap = float(cap_area[0]) * CONVERSION_FACTOR
                    y_cap_raw = float(cap_area[1]) * CONVERSION_FACTOR
                    w_cap = float(cap_area[2]) * CONVERSION_FACTOR
                    h_cap = float(cap_area[3]) * CONVERSION_FACTOR
                    new_y_cap = page_height - (y_cap_raw + h_cap)
                    exclusions_text.append((
                        x_cap - exclusion_margin,
                        new_y_cap - exclusion_margin,
                        w_cap + 2 * exclusion_margin,
                        h_cap + 2 * exclusion_margin
                    ))
                    caption_coords_list.append((x_cap, new_y_cap, w_cap, h_cap))
        logging.debug("Exclusion areas: %s", exclusions_text)
        if debug:
            for ex in exclusions_text:
                pdf.setStrokeColor(red)
                pdf.rect(ex[0], ex[1], ex[2], ex[3], fill=0)

        candidate_areas = subtract_rectangles_strict(free_area_text, exclusions_text)
        logging.debug("Found %d candidate area(s)", len(candidate_areas))
        if debug:
            for i, cand in enumerate(candidate_areas, start=1):
                pdf.setStrokeColor(green)
                pdf.setLineWidth(1)
                pdf.rect(cand[0], cand[1], cand[2], cand[3], fill=0)
                pdf.drawString(cand[0] + 2, cand[1] + cand[3] - 10, f"Candidate {i}")

        if not candidate_areas:
            chosen_areas = [free_area_text]
        elif len(candidate_areas) == 1:
            chosen_areas = candidate_areas
        elif image_keep_boxes:
            free_area_width = free_area_text[2]
            full_threshold = free_area_width * 0.9
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
                if full_top <= short_bottom:
                    extended_short_candidate = (short_candidate[0], full_top, short_candidate[2], short_top - full_top)
                elif short_top <= full_bottom:
                    extended_short_candidate = (short_candidate[0], short_bottom, short_candidate[2], full_bottom - short_bottom)
                else:
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
        
        if len(chosen_areas) == 2:
            chosen_areas = sorted(chosen_areas, key=lambda a: a[1], reverse=True)

        text_content = (initial_overflow + " " + main_text).strip()
        if page.get("new_formatting_applied", False):
            text_content, html_headers = process_html_content(text_content)
            headers = html_headers
        else:
            headers = page.get("headers", None)

        if len(chosen_areas) == 1:
            overflow = draw_adaptive_text(pdf, text_content, chosen_areas[0],
                                          max_font_size=11, min_font_size=10, alignment="justify",
                                          headers=headers,
                                          capitolo=page.get("capitolo", None))
        else:
            overflow = draw_adaptive_text(pdf, text_content, chosen_areas[0],
                                          max_font_size=11, min_font_size=10, alignment="justify",
                                          headers=headers,
                                          capitolo=page.get("capitolo", None))
            overflow = draw_adaptive_text(pdf, overflow, chosen_areas[1],
                                          max_font_size=11, min_font_size=10, alignment="justify",
                                          headers=headers,
                                          capitolo=page.get("capitolo", None))
    else:
        logging.info("Page %s: no main text overlay (non-text page or full-image).", page_num)
        overflow = initial_overflow

    cap_coords = page.get("caption_coordinates")
    captions = page.get("captions", [])
    if cap_coords and captions:
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
                draw_adaptive_text(pdf, cap_text_str, caption_area,
                                   max_font_size=11, min_font_size=10, font_name="Times-Bold",
                                   alignment="center", headers=None)
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
            draw_adaptive_text(pdf, caption_text, caption_area,
                               max_font_size=10, min_font_size=10, font_name="Times-Bold",
                               alignment="center", headers=None)
    logging.debug("Completed processing page: %s", page_num)
    return overflow

# -------------------------------------------------------------------------------
# MAIN FUNCTION
# -------------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Prepares the final PDF by overlaying text onto bleached images from 'bleachedimages'."
    )
    parser.add_argument("--input", required=False, default=".", help="Input folder containing JSON files and bleachedimages subfolder")
    parser.add_argument("--output", required=False, default="final.pdf", help="Output PDF filename (default: final.pdf)")
    parser.add_argument("--last-text-page", type=int, default=493, help="Last page number containing text (pages after this are unchanged)")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode to overlay candidate area outlines")
    args = parser.parse_args()

    input_folder = os.path.abspath(args.input)
    logging.info("Input folder: %s", input_folder)
    
    bookindex_path = os.path.join(input_folder, "bookindex.json")
    translation_path = os.path.join(input_folder, "godstarita.json")
    try:
        with open(bookindex_path, 'r', encoding='utf-8') as f:
            original_data = json.load(f)
        logging.info("Loaded bookindex.json with %d pages", len(original_data))
    except Exception as e:
        logging.error("Error loading %s: %s", bookindex_path, e)
        sys.exit(1)
    try:
        with open(translation_path, 'r', encoding='utf-8') as f:
            translation_data = json.load(f)
        logging.info("Loaded translation file with %d pages", len(translation_data))
    except Exception as e:
        logging.error("Error loading %s: %s", translation_path, e)
        sys.exit(1)

    merged_pages = []
    translation_dict = {entry["page_number"]: entry for entry in translation_data if entry.get("page_number") is not None}
    for orig in original_data:
        page_num = orig.get("page_number")
        if page_num is None or (isinstance(page_num, int) and page_num > args.last_text_page):
            merged_pages.append(orig)
        else:
            if page_num in translation_dict:
                merged_entry = orig.copy()
                merged_entry.update(translation_dict[page_num])
                merged_pages.append(merged_entry)
            else:
                merged_pages.append(orig)
    
    # Filter out JSON pages with null page_number since those are the index pages,
    # and they are already added separately via the index image logic.
    merged_pages = [page for page in merged_pages if page.get("page_number") is not None]
    
    logging.info("Merged total pages (after filtering index pages): %d", len(merged_pages))
    if not merged_pages:
        logging.error("No pages found after merging JSON data.")
        sys.exit(1)

    page_width, page_height = FIXED_PAGE_SIZE
    bleached_dir = os.path.join(input_folder, "bleachedimages")
    if not os.path.exists(bleached_dir):
        logging.error("Bleached images folder not found: %s", bleached_dir)
        sys.exit(1)

    output_pdf_path = os.path.join(input_folder, args.output)
    c = canvas.Canvas(output_pdf_path, pagesize=(page_width, page_height))
    
    # --- ADD INDEX PAGES ---
    add_index_pages(c, bleached_dir, page_width, page_height)
    
    # --- PROCESS MERGED PAGES ---
    overflow_text = ""
    for i, page in enumerate(merged_pages):
        logging.info("Processing page %d/%d", i+1, len(merged_pages))
        overflow_text = layout_page(c, page, bleached_dir, page_width, page_height, args.last_text_page, initial_overflow=overflow_text, debug=args.debug)
        c.showPage()
    c.save()
    logging.info("Final PDF generated: %s", output_pdf_path)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
