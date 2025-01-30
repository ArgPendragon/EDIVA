import cv2
import pytesseract
import os
from pathlib import Path
import re
import json
import numpy as np
import logging

# Ensure Tesseract is installed and set its path
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def preprocess_image(image_path):
    """Preprocess the image to improve OCR accuracy while preserving faint text."""
    image = cv2.imread(str(image_path))
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)  # Convert to grayscale
    
    # Reduce contrast adjustment to avoid text loss
    processed = cv2.convertScaleAbs(gray, alpha=1.2, beta=10)
    
    return processed

def extract_text_from_image(image_path):
    """Extract text from an image using Tesseract OCR with optimized settings and save raw output."""
    processed_image = preprocess_image(image_path)
    
    # Use --psm 6, best for dense text recognition
    custom_config = r'--oem 3 --psm 6 -c preserve_interword_spaces=1'
    text = pytesseract.image_to_string(processed_image, config=custom_config, lang='eng')
    
    # Save raw OCR output for debugging
    raw_text_path = Path("D:/cardotest/ExtractedImages/1God/raw_text")
    raw_text_path.mkdir(parents=True, exist_ok=True)
    
    with open(raw_text_path / f"{image_path.stem}.txt", "w", encoding="utf-8") as f:
        f.write(text)
    
    return text.strip()

def extract_sections(text):
    """Extract structured sections, citations, and bibliography from OCR text without truncation."""
    sections = []
    bibliography = []
    
    # Adjust section detection to prevent cutting off content
    section_pattern = re.compile(r'(?m)^(CHAPTER\s+\d+|[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*|\b[A-Z]{3,}\b)(?:\n|\s{2,})')

    citation_pattern = re.compile(r'\([^)]*\d+[^)]*\)')  # Matches (Author, Year)
    bibliography_pattern = re.compile(r'^\d+\.\s+[A-Z][a-z]+.*', re.MULTILINE)  # Matches numbered references

    parts = section_pattern.split(text)
    extracted_bibliography = []
    parsed_sections = []

    for i in range(1, len(parts), 2):
        title = parts[i].strip() if parts[i] else "Unknown Section"
        content = parts[i + 1].strip() if (i + 1 < len(parts) and parts[i + 1]) else ""

        # If content is too short, merge with previous section to avoid fragmentation
        if len(content.split()) < 10:
            if parsed_sections:
                parsed_sections[-1]["content"] += " " + content
            continue

        # Detect bibliography and separate it from normal content
        bib_matches = bibliography_pattern.findall(content)
        if len(bib_matches) > 3:
            extracted_bibliography.extend(bib_matches)
            content = re.sub(bibliography_pattern, '', content).strip()

        citations = citation_pattern.findall(content)
        parsed_sections.append({
            "title": title,
            "content": content,
            "citations": citations
        })
        bibliography.extend(citations)

    bibliography.extend(extracted_bibliography)

    return parsed_sections, list(set(bibliography))

def process_images_to_json(directory, chunk_output_dir):
    """Process images in a directory and save structured JSON in 10-image chunks."""
    directory = Path(directory)
    chunk_output_dir = Path(chunk_output_dir)
    chunk_output_dir.mkdir(parents=True, exist_ok=True)  # Ensure chunk directory exists
    
    if not directory.exists():
        logging.error(f"Error: Directory {directory} does not exist!")
        return
    
    image_files = sorted(directory.glob("*.png")) + sorted(directory.glob("*.jpg")) + sorted(directory.glob("*.jpeg"))
    image_files.sort(key=lambda x: int(re.search(r'\d+', x.stem).group()) if re.search(r'\d+', x.stem) else float('inf'))
    
    logging.info(f"Found {len(image_files)} images")
    
    all_pages = []
    chunk_count = 1
    
    for index, img_path in enumerate(image_files, start=1):
        logging.info(f"Processing image {index}/{len(image_files)}: {img_path.name}")
        text = extract_text_from_image(img_path)
        sections, bibliography = extract_sections(text)
        
        page_json = {
            "type": "main" if index > 12 else "index",
            "page_number": index - 12 if index > 12 else None,
            "subsections": sections,
            "bibliography": bibliography
        }
        
        all_pages.append(page_json)
        
        # Save chunk every 10 images
        if index % 10 == 0 or index == len(image_files):
            chunk_file = chunk_output_dir / f"chunk_{chunk_count:03}.json"
            with open(chunk_file, 'w', encoding='utf-8') as f:
                json.dump(all_pages, f, indent=4, ensure_ascii=False)
            logging.info(f"Chunk {chunk_count} saved to {chunk_file}")
            all_pages = []  # Reset list for next chunk
            chunk_count += 1

if __name__ == "__main__":
    process_images_to_json("D:/cardotest/ExtractedImages/1God", "D:/cardotest/ExtractedImages/1God/chunks")
