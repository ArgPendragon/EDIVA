#!/usr/bin/env python3
"""
This script generates new Italian index pages using translation data (from JSON files)
while mimicking the formatting of the original. It uses OCR on one or more reference pages
to detect the font sizes for normal headers and "Capitolo" headers.
- Regular header lines are drawn left-aligned.
- Each entry line (with a page number) is drawn so that the page number is right-aligned.
- Lines starting with "Capitolo" are interpreted as main headers: they are drawn centered,
  in bold, and using a larger font size (as detected via OCR).
- The effective left and right margins are doubled compared to the provided margin value.
"""

import os
import glob
import json
import argparse
import statistics
from PIL import Image, ImageDraw, ImageFont

# Import pytesseract for OCR detection.
try:
    import pytesseract
except ImportError:
    raise ImportError("Please install pytesseract (pip install pytesseract) to use OCR detection.")

def detect_font_details_from_ocr(reference_images, default_font_path, default_bold_font_path):
    """
    Uses OCR (via pytesseract) on one or more reference images to detect text height.
    Returns:
      - normal_font_path (unchanged),
      - bold_font_path (unchanged),
      - detected_normal_font_size: average height of text not containing "Capitolo",
      - detected_capitolo_font_size: average height of text lines containing "Capitolo".
    If no data is found, defaults are used (normal: 24, capitolo: normal+4).
    """
    normal_heights = []
    capitolo_heights = []
    
    for image_path in reference_images:
        try:
            with Image.open(image_path) as img:
                ocr_data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
                n_boxes = len(ocr_data['text'])
                for i in range(n_boxes):
                    text = ocr_data['text'][i].strip()
                    if not text:
                        continue
                    height = ocr_data['height'][i]
                    # Check if the text contains "Capitolo" (case-insensitive).
                    if "capitolo" in text.lower():
                        capitolo_heights.append(height)
                    else:
                        normal_heights.append(height)
        except Exception as e:
            print(f"Error processing reference image '{image_path}': {e}")
    
    # Compute average heights. Use defaults if no OCR data was found.
    detected_normal_font_size = round(statistics.mean(normal_heights)) if normal_heights else 24
    detected_capitolo_font_size = round(statistics.mean(capitolo_heights)) if capitolo_heights else detected_normal_font_size + 4

    print(f"Detected normal font size: {detected_normal_font_size}, "
          f"Detected Capitolo font size: {detected_capitolo_font_size}")
    
    return default_font_path, default_bold_font_path, detected_normal_font_size, detected_capitolo_font_size

def parse_translation_json(json_obj):
    """
    Given the JSON object containing Italian translation data,
    return a list of chapters where each chapter is a dict with:
      - chapter_number (e.g., "Capitolo I")
      - chapter_title
      - entries: list of { "text": ..., "page_number": ... }
    The JSON is expected to have a key 'translated_text' (or 'index') with a list.
    """
    if "translated_text" in json_obj:
        chapters = json_obj["translated_text"]
    elif "index" in json_obj:
        chapters = json_obj["index"]
    else:
        chapters = json_obj if isinstance(json_obj, list) else []
    return chapters

def compute_layout(chapters, canvas_width, canvas_height, top_margin, left_margin, line_spacing,
                   normal_font_size, capitolo_font_size):
    """
    Computes layout positions for all text lines.
    Returns a flat list of items. Each item includes:
       - text: text to draw
       - page_number: (if any) page number string
       - x, y: starting coordinates
       - width: available width for drawing text
       - font_size: font size to use
       - align: 'left' or 'center'
       - bold: True if text should be drawn in bold
    Lines starting with "Capitolo" use the detected capitolo_font_size, are bold, and centered.
    The effective horizontal margins are doubled compared to the provided left_margin value.
    """
    layout = []
    current_y = top_margin
    # Double the left_margin to restrict both left and right margins.
    effective_margin = left_margin * 5
    available_width = canvas_width - (2 * effective_margin)

    for chapter in chapters:
        chap_num = chapter.get("chapter_number", "").strip()
        # If the chapter number starts with "Capitolo", use the capitolo style.
        if chap_num.lower().startswith("capitolo"):
            layout.append({
                "text": chap_num,
                "page_number": "",
                "x": effective_margin,
                "y": current_y,
                "width": available_width,
                "font_size": capitolo_font_size,
                "align": "center",
                "bold": True
            })
            current_y += capitolo_font_size + line_spacing
        else:
            layout.append({
                "text": chap_num,
                "page_number": "",
                "x": effective_margin,
                "y": current_y,
                "width": available_width,
                "font_size": normal_font_size,
                "align": "left",
                "bold": False
            })
            current_y += normal_font_size + line_spacing

        # Chapter title (always left-aligned, not bold).
        chap_title = chapter.get("chapter_title", "").strip()
        layout.append({
            "text": chap_title,
            "page_number": "",
            "x": effective_margin,
            "y": current_y,
            "width": available_width,
            "font_size": normal_font_size,
            "align": "left",
            "bold": False
        })
        current_y += normal_font_size + line_spacing

        # Process each index entry.
        for item in chapter.get("entries", []):
            layout.append({
                "text": item.get("text", "").strip(),
                "page_number": item.get("page_number", "").strip(),
                "x": effective_margin,
                "y": current_y,
                "width": available_width,
                "font_size": normal_font_size,
                "align": "left",   # Main text always left-aligned.
                "bold": False
            })
            current_y += normal_font_size + line_spacing

    return layout

def draw_text(draw, text, position, font, align="left", fill="black"):
    """
    Draws text on the given drawing context.
    If 'center' alignment is requested, computes the x coordinate accordingly.
    Position is a tuple: (x, y, available_width)
    """
    x, y, available_width = position
    if align == "center":
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        x = x + (available_width - text_width) // 2
    draw.text((x, y), text, fill=fill, font=font)

def generate_page(layout, canvas_width, canvas_height, font_path, bold_font_path):
    """
    Generates a new page image (white background) and draws all text lines according to the layout.
    For each entry with a page number, the main text is drawn left-aligned and the page number is
    drawn right-aligned.
    """
    img = Image.new("RGB", (canvas_width, canvas_height), "white")
    draw = ImageDraw.Draw(img)
    reserved_margin = 10  # space between main text and page number

    for item in layout:
        x = item["x"]
        y = item["y"]
        available_width = item["width"]
        font_size = item["font_size"]

        # Select font: use bold if required and if a bold font is provided.
        if item["bold"] and bold_font_path:
            try:
                font = ImageFont.truetype(bold_font_path, font_size)
            except Exception as e:
                print(f"Could not load bold font '{bold_font_path}': {e}. Falling back to regular font.")
                font = ImageFont.truetype(font_path, font_size)
        else:
            try:
                font = ImageFont.truetype(font_path, font_size)
            except Exception as e:
                print(f"Could not load font '{font_path}': {e}. Using default font.")
                font = ImageFont.load_default()

        text = item["text"]
        page_number = item["page_number"]

        if page_number:
            # Draw the main text (left-aligned).
            draw.text((x, y), text, fill="black", font=font)
            # Compute the width of the page number.
            page_bbox = draw.textbbox((0, 0), page_number, font=font)
            page_num_width = page_bbox[2] - page_bbox[0]
            # Position page number so it is right-aligned.
            page_x = x + available_width - page_num_width - reserved_margin
            draw.text((page_x, y), page_number, fill="black", font=font)
        else:
            # Draw text using the specified alignment.
            if item["align"] == "center":
                draw_text(draw, text, (x, y, available_width), font, align="center")
            else:
                draw.text((x, y), text, fill="black", font=font)

    return img

def main():
    parser = argparse.ArgumentParser(
        description="Generate Italian index pages using OCR-detected formatting details with restricted horizontal margins."
    )
    parser.add_argument("--input", type=str, required=True,
                        help="Input directory containing JSON translation files.")
    parser.add_argument("--output", type=str, default="italianindex",
                        help="Output directory for generated Italian pages.")
    parser.add_argument("--canvas_width", type=int, default=1200,
                        help="Canvas width in pixels (default: 1200).")
    parser.add_argument("--canvas_height", type=int, default=1500,
                        help="Canvas height in pixels (default: 1500).")
    parser.add_argument("--reference_images", type=str, nargs="+", default=[],
                        help="Path(s) to reference image(s) to detect original font details.")
    parser.add_argument("--font_path", type=str, default="arial.ttf",
                        help="Path to the regular TTF font file (default: arial.ttf).")
    parser.add_argument("--bold_font_path", type=str, default="arialbd.ttf",
                        help="Path to the bold TTF font file (default: arialbd.ttf).")
    parser.add_argument("--top_margin", type=int, default=50,
                        help="Top margin in pixels (default: 50).")
    parser.add_argument("--left_margin", type=int, default=50,
                        help="Base left margin in pixels (default: 50); effective margins will be double this value.")
    parser.add_argument("--line_spacing", type=int, default=10,
                        help="Vertical spacing between lines in pixels (default: 10).")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    # Use OCR on the provided reference images to detect font sizes.
    if args.reference_images:
        font_path, bold_font_path, normal_font_size, capitolo_font_size = detect_font_details_from_ocr(
            args.reference_images, args.font_path, args.bold_font_path)
    else:
        # Use defaults if no reference images provided.
        normal_font_size = 24
        capitolo_font_size = normal_font_size + 4
        font_path = args.font_path
        bold_font_path = args.bold_font_path
        print(f"No reference images provided; using default font sizes: normal={normal_font_size}, capitolo={capitolo_font_size}")

    # Process every JSON file in the input folder.
    json_files = sorted(glob.glob(os.path.join(args.input, "*.json")))
    if not json_files:
        print("No JSON files found in the input directory.")
        return

    for json_file in json_files:
        base_name = os.path.splitext(os.path.basename(json_file))[0]
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                trans_json = json.load(f)
        except Exception as e:
            print(f"Error reading JSON file '{json_file}': {e}")
            continue

        chapters = parse_translation_json(trans_json)

        # Compute layout for all text items.
        layout = compute_layout(
            chapters,
            canvas_width=args.canvas_width,
            canvas_height=args.canvas_height,
            top_margin=args.top_margin,
            left_margin=args.left_margin,
            line_spacing=args.line_spacing,
            normal_font_size=normal_font_size,
            capitolo_font_size=capitolo_font_size
        )

        # Generate the new page image.
        result_img = generate_page(layout, args.canvas_width, args.canvas_height, font_path, bold_font_path)

        out_file = os.path.join(args.output, base_name + "_italian.jpg")
        try:
            result_img.save(out_file, "JPEG")
            print(f"Saved generated Italian page: {out_file}")
        except Exception as e:
            print(f"Error saving '{out_file}': {e}")

if __name__ == "__main__":
    main()
