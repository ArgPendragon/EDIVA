import json
import sys
import logging
import os
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import simpleSplit

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def extract_content(json_file):
    """Extracts all occurrences of 'content', 'bibliography', and 'page_number' from the JSON file."""
    try:
        with open(json_file, 'r', encoding='utf-8') as file:
            data = json.load(file)
            if not isinstance(data, dict) and not isinstance(data, list):
                logging.error("Invalid JSON format: Expected a dictionary or a list.")
                sys.exit(1)
            
            # Search for all content, bibliography, and page_number fields
            pages = []
            def find_pages(d):
                if isinstance(d, dict):
                    content = d.get("content", "")
                    bibliography = d.get("bibliography", [])
                    page_number = d.get("page_number", "Unknown")
                    if content or bibliography or page_number != "Unknown":
                        pages.append((content, bibliography, page_number))
                    for v in d.values():
                        find_pages(v)
                elif isinstance(d, list):
                    for item in d:
                        find_pages(item)
            
            find_pages(data)
            return pages
    except FileNotFoundError:
        logging.error(f"File not found: {json_file}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        logging.error(f"JSON decoding error: {e}")
        sys.exit(1)

def create_pdf(pages, input_json):
    """Creates a formatted PDF where each page contains justified content at the top, bibliography at the bottom, and page number centered at the bottom."""
    if not pages:
        logging.warning("No content provided. Skipping PDF generation.")
        return
    
    output_pdf = os.path.join(os.path.dirname(input_json), os.path.splitext(os.path.basename(input_json))[0] + ".pdf")
    
    try:
        pdf = canvas.Canvas(output_pdf, pagesize=letter)
        width, height = letter
        margin = 50
        max_width = width - 2 * margin
        
        for content, bibliography, page_number in pages:
            pdf.showPage()
            y_position = height - margin
            pdf.setFont("Times-Roman", 12)
            
            # Print justified content with dynamic font scaling
            font_size = 12
            while font_size >= 10:
                lines = simpleSplit(content, "Times-Roman", font_size, max_width)
                if len(lines) * (font_size + 2) <= (height - 2 * margin):
                    break
                font_size -= 1
            pdf.setFont("Times-Roman", font_size)
            
            for line in lines:
                pdf.drawString(margin, y_position, line)
                y_position -= font_size + 2
                if y_position < margin + 50:
                    pdf.showPage()
                    y_position = height - margin
                    pdf.setFont("Times-Roman", font_size)
            
            # Print bibliography at the bottom
            if bibliography:
                pdf.setFont("Times-Roman", 10)
                y_bib_position = margin + 30
                wrapped_bibliography = simpleSplit("\n".join(bibliography), "Times-Roman", 10, max_width)
                for bib_line in wrapped_bibliography:
                    pdf.drawString(margin, y_bib_position, bib_line)
                    y_bib_position += 12
            
            # Print page number centered at the bottom
            pdf.setFont("Times-Roman", 10)
            pdf.drawCentredString(width / 2, 20, f"Page {page_number}")
        
        pdf.save()
        logging.info(f"PDF successfully saved as {output_pdf}")
    except Exception as e:
        logging.error(f"Error generating PDF: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        logging.error("Usage: python script.py <json_file>")
        sys.exit(1)
    
    json_file = sys.argv[1]
    pages = extract_content(json_file)
    create_pdf(pages, json_file)
