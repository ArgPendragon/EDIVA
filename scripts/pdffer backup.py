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
            if not isinstance(data, (dict, list)):
                logging.error("Invalid JSON format: Expected a dictionary or a list.")
                sys.exit(1)
            
            pages = []
            def find_pages(d):
                if isinstance(d, dict):
                    content = d.get("content", "").strip()
                    bibliography = d.get("bibliography", [])
                    page_number = d.get("page_number")
                    if content or bibliography or page_number is not None:
                        pages.append((content, bibliography, page_number))
                    for v in d.values():
                        find_pages(v)
                elif isinstance(d, list):
                    for item in d:
                        find_pages(item)
            
            find_pages(data)
            return sorted(pages, key=lambda x: x[2] if x[2] is not None else float('inf'))
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logging.error(f"Error processing JSON file: {e}")
        sys.exit(1)

def create_pdf(pages, input_json):
    """Creates a formatted PDF with justified content, bibliography, and correct page numbering."""
    if not pages:
        logging.warning("No content provided. Skipping PDF generation.")
        return
    
    output_pdf = os.path.join(os.path.dirname(input_json), os.path.splitext(os.path.basename(input_json))[0] + ".pdf")
    pdf = canvas.Canvas(output_pdf, pagesize=letter)
    width, height = letter
    margin = 50
    max_width = width - 2 * margin
    
    for content, bibliography, page_number in pages:
        pdf.setFont("Times-Roman", 12)
        y_position = height - margin
        
        text_object = pdf.beginText(margin, y_position)
        text_object.setFont("Times-Roman", 12)
        
        # Justify content
        lines = simpleSplit(content, "Times-Roman", 12, max_width)
        for line in lines:
            text_object.textLine(line)
            y_position -= 14  # Line spacing
            if y_position < 100:  # Prevents overlapping bibliography
                pdf.drawText(text_object)
                pdf.showPage()
                text_object = pdf.beginText(margin, height - margin)
                text_object.setFont("Times-Roman", 12)
                y_position = height - margin
        
        pdf.drawText(text_object)
        
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
