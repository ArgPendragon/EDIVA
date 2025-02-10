#!/usr/bin/env python3
import json
import os
import sys
import logging
import argparse
from typing import Any, List, Tuple, Union
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import simpleSplit

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def justify_text(pdf: canvas.Canvas, text: str, x: float, y: float, max_width: float, font_size: float) -> None:
    """
    Disegna il testo sul canvas PDF con una semplice giustificazione.
    Se il testo è troppo lungo o ha una sola parola, viene semplicemente disegnato.
    """
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

def draw_heading(pdf: canvas.Canvas, text: str, y_position: float, page_width: float) -> float:
    """
    Disegna l'intestazione centrata nella pagina e restituisce il nuovo y_position.
    """
    heading_font_size = 18
    vertical_padding = 80
    pdf.setFont("Times-Bold", heading_font_size)
    text_width = pdf.stringWidth(text, "Times-Bold", heading_font_size)
    x_position = (page_width - text_width) / 2
    y_position -= vertical_padding
    pdf.drawString(x_position, y_position, text)
    return y_position - 60  # ulteriore spazio dopo l'intestazione

def extract_content(json_file: str) -> List[Tuple[str, str, List[str], Union[int, float, None]]]:
    """
    Estrae le pagine di contenuto dal file JSON.
    Ogni pagina è una tupla: (heading, content, bibliography, page_number)
    """
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logging.error(f"Errore nell'apertura/lettura del file JSON: {e}")
        sys.exit(1)

    if not isinstance(data, (dict, list)):
        logging.error("Formato JSON non valido: ci si aspettava un dizionario o una lista.")
        sys.exit(1)

    pages: List[Tuple[str, str, List[str], Union[int, float, None]]] = []

    def find_pages(d: Any) -> None:
        if isinstance(d, dict):
            content = d.get("content", "").strip()
            bibliography = d.get("bibliography", [])
            page_number = d.get("page_number")
            heading = d.get("heading", "").strip()
            if content or bibliography or page_number is not None:
                pages.append((heading, content, bibliography, page_number))
            for value in d.values():
                find_pages(value)
        elif isinstance(d, list):
            for item in d:
                find_pages(item)

    find_pages(data)
    return sorted(pages, key=lambda x: x[3] if x[3] is not None else float('inf'))

def create_pdf(pages: List[Tuple[str, str, List[str], Union[int, float, None]]], input_json: str) -> None:
    """
    Crea il PDF a partire dalle pagine estratte.
    
    Il layout di ogni pagina prevede:
      - (Opzionale) intestazione centrata.
      - Il contenuto testuale, stampato nell'area disponibile.
      - Se presente, la bibliografia viene stampata in una sezione riservata nella parte inferiore.
      - Il numero di pagina (uguale a quello originale) viene visualizzato in fondo alla pagina.
    """
    if not pages:
        logging.warning("Nessun contenuto trovato. Generazione del PDF saltata.")
        return

    output_pdf = os.path.join(
        os.path.dirname(input_json),
        os.path.splitext(os.path.basename(input_json))[0] + ".pdf"
    )
    pdf = canvas.Canvas(output_pdf, pagesize=letter)
    page_width, page_height = letter

    # Margini generali
    margin_top = 50
    margin_side = 50
    margin_bottom = 50  # area minima per il footer (numero di pagina)
    max_width = page_width - 2 * margin_side

    for heading, content, bibliography, page_number in pages:
        y_position = page_height - margin_top

        # Eventuale intestazione
        if heading:
            y_position = draw_heading(pdf, heading, y_position, page_width)

        # Se è presente la bibliografia, la riserviamo nella parte inferiore
        if bibliography:
            # Utilizziamo un font leggermente più piccolo per la bibliografia
            bib_font_size = 10  # oppure, ad esempio: font_size_content - 2
            pdf.setFont("Times-Roman", bib_font_size)
            bib_text = "\n".join(bibliography)
            bib_lines = simpleSplit(bib_text, "Times-Roman", bib_font_size, max_width)
            line_spacing_bib = bib_font_size + 2
            bib_block_height = len(bib_lines) * line_spacing_bib + 10  # 10 punti di padding
        else:
            bib_block_height = 0

        # Riserviamo l'area inferiore per bibliografia (se presente) e per il numero di pagina
        reserved_bottom = margin_bottom + bib_block_height + 10  # 10 punti extra di spazio
        available_height = y_position - reserved_bottom

        # Stampa del contenuto
        font_size = 12
        pdf.setFont("Times-Roman", font_size)
        lines = simpleSplit(content, "Times-Roman", font_size, max_width)

        # Se il contenuto non rientra nell'area disponibile, riduciamo iterativamente il font
        while lines and (len(lines) * (font_size + 6) > available_height) and font_size > 8:
            font_size -= 1
            pdf.setFont("Times-Roman", font_size)
            lines = simpleSplit(content, "Times-Roman", font_size, max_width)

        for line in lines:
            if y_position < reserved_bottom:
                break
            justify_text(pdf, line, margin_side, y_position, max_width, font_size)
            y_position -= (font_size + 6)

        # Stampa della bibliografia (se presente) nella parte inferiore
        if bibliography:
            # La bibliografia viene stampata all'interno dell'area riservata,
            # partendo dalla parte alta del blocco riservato
            bib_y = margin_bottom + bib_block_height - line_spacing_bib + 5
            pdf.setFont("Times-Roman", bib_font_size)
            for bib_line in bib_lines:
                # Evitiamo di invadere l'area del numero di pagina
                if bib_y < margin_bottom + 20:
                    break
                justify_text(pdf, bib_line, margin_side, bib_y, max_width, bib_font_size)
                bib_y -= line_spacing_bib

        # Stampa del numero di pagina (come da JSON)
        pdf.setFont("Times-Roman", 10)
        page_number_text = f"{page_number}" if page_number is not None else ""
        pdf.drawCentredString(page_width / 2, 20, page_number_text)
        pdf.showPage()

    pdf.save()
    logging.info(f"PDF salvato con successo: {output_pdf}")

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Genera un PDF a partire da un file JSON ottenuto da OCR di pagine scannerizzate.")
    parser.add_argument("json_file", help="Percorso al file JSON di input")
    return parser.parse_args()

def main() -> None:
    args = parse_args()
    pages = extract_content(args.json_file)
    create_pdf(pages, args.json_file)

if __name__ == "__main__":
    main()
