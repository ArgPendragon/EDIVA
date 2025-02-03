import json
import sys
import logging
import os
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import simpleSplit

def justify_text(pdf, text, x, y, max_width, font_size):
    words = text.split()
    space_count = len(words) - 1
    text_width = pdf.stringWidth(text, "Times-Roman", font_size)
    
    if space_count <= 0 or text_width > max_width * 0.85:
        pdf.drawString(x, y, text)
        return
    
    total_text_width = sum(pdf.stringWidth(word, "Times-Roman", font_size) for word in words)
    extra_space = (max_width - total_text_width) / space_count if space_count > 0 else 0
    extra_space = min(extra_space, 4)
    
    current_x = x
    for i, word in enumerate(words):
        pdf.drawString(current_x, y, word)
        if i < space_count:
            current_x += pdf.stringWidth(word, "Times-Roman", font_size) + extra_space

def draw_heading(pdf, text, y_position, width):
    y_position -= 80
    pdf.setFont("Times-Bold", 18)
    text_width = pdf.stringWidth(text, "Times-Bold", 18)
    x_position = (width - text_width) / 2
    pdf.drawString(x_position, y_position, text)
    return y_position - 60

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def extract_content(json_file):
    try:
        with open(json_file, 'r', encoding='utf-8') as file:
            data = json.load(file)
            if not isinstance(data, (dict, list)):
                logging.error("Invalid JSON format: Expected a dictionary or a list.")
                sys.exit(1)
            
            pages = []
            def find_pages(d):
                if isinstance(d, dict):
                    content = d.get("content", "").strip()
                    bibliography = d.get("bibliography", [])
                    page_number = d.get("page_number")
                    heading = d.get("heading", "").strip()
                    if content or bibliography or page_number is not None:
                        pages.append((heading, content, bibliography, page_number))
                    for v in d.values():
                        find_pages(v)
                elif isinstance(d, list):
                    for item in d:
                        find_pages(item)
            
            find_pages(data)
            return sorted(pages, key=lambda x: x[3] if x[3] is not None else float('inf'))
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logging.error(f"Error processing JSON file: {e}")
        sys.exit(1)

def create_pdf(pages, input_json):
    if not pages:
        logging.warning("No content provided. Skipping PDF generation.")
        return
    
    output_pdf = os.path.join(os.path.dirname(input_json), os.path.splitext(os.path.basename(input_json))[0] + ".pdf")
    pdf = canvas.Canvas(output_pdf, pagesize=letter)
    width, height = letter
    margin = 50
    max_width = width - 2 * margin
    
    for heading, content, bibliography, page_number in pages:
        y_position = height - margin
        
        if heading:
            y_position = draw_heading(pdf, heading, y_position, width)
        
        font_size = 12
        pdf.setFont("Times-Roman", font_size)
        lines = simpleSplit(content, "Times-Roman", font_size, max_width)
        
        if len(lines) * (font_size + 6) > y_position - 120:
            while len(lines) * (font_size + 6) > y_position - 120 and font_size > 8:
                font_size -= 1
                pdf.setFont("Times-Roman", font_size)
                lines = simpleSplit(content, "Times-Roman", font_size, max_width)
        
        for line in lines:
            if y_position < 100:
                break
            justify_text(pdf, line, margin, y_position, max_width, font_size)
            y_position -= (font_size + 6)
        
        if bibliography:
            pdf.setFont("Times-Roman", font_size - 2)
            wrapped_bibliography = simpleSplit("\n".join(bibliography), "Times-Roman", font_size - 2, max_width)
            
            if len(wrapped_bibliography) * (font_size + 2) > y_position - 50:
                while len(wrapped_bibliography) * (font_size + 2) > y_position - 50 and font_size > 8:
                    font_size -= 1
                    pdf.setFont("Times-Roman", font_size)
                    wrapped_bibliography = simpleSplit("\n".join(bibliography), "Times-Roman", font_size - 2, max_width)
            
            for bib_line in wrapped_bibliography:
                if y_position < 50:
                    break
                justify_text(pdf, bib_line, margin, y_position, max_width, font_size - 2)
                y_position -= (font_size + 2)
        
        pdf.setFont("Times-Roman", 10)
        pdf.drawCentredString(width / 2, 20, f"Page {page_number}")
        pdf.showPage()
    
    pdf.save()
    logging.info(f"PDF successfully saved as {output_pdf}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        logging.error("Usage: python script.py <json_file>")
        sys.exit(1)
    
    json_file = sys.argv[1]
    pages = extract_content(json_file)
    create_pdf(pages, json_file)
