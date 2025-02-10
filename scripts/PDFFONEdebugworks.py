#!/usr/bin/env python3
import os
import sys
import json
import logging
import argparse
from reportlab.pdfgen import canvas
from reportlab.lib.utils import simpleSplit

# Configurazione base del logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Costanti di conversione e dimensioni della pagina
DPI = 150
CONVERSION_FACTOR = 72 / DPI  # circa 0.48
FIXED_PAGE_SIZE = (576, 720)  # in punti (larghezza x altezza)
MIN_AREA_RATIO = 0.01  # 1% dell'area della pagina

##############################################################################
# FUNZIONI DI SUPPORTO PER OPERAZIONI GEOMETRICHE
##############################################################################

def subtract_rect(candidate, exclusion):
    """
    Sottrae il rettangolo 'exclusion' dal rettangolo 'candidate'.
    Entrambi sono tuple (x, y, w, h) in coordinate PDF (origine in basso a sinistra).
    Restituisce la lista (eventualmente vuota) dei rettangoli risultanti.
    """
    xA, yA, wA, hA = candidate
    xE, yE, wE, hE = exclusion

    inter_left = max(xA, xE)
    inter_right = min(xA + wA, xE + wE)
    inter_bottom = max(yA, yE)
    inter_top = min(yA + hA, yE + hE)
    if inter_right <= inter_left or inter_top <= inter_bottom:
        return [candidate]

    results = []
    # Parte superiore
    if inter_top < yA + hA:
        results.append((xA, inter_top, wA, (yA + hA) - inter_top))
    # Parte inferiore
    if inter_bottom > yA:
        results.append((xA, yA, wA, inter_bottom - yA))
    # Parte sinistra
    if inter_left > xA:
        results.append((xA, inter_bottom, inter_left - xA, inter_top - inter_bottom))
    # Parte destra
    if inter_right < xA + wA:
        results.append((inter_right, inter_bottom, (xA + wA) - inter_right, inter_top - inter_bottom))
    
    return [r for r in results if r[2] > 0 and r[3] > 0]

def subtract_rectangles(full_area, exclusions):
    """
    Dato un rettangolo 'full_area' e una lista di rettangoli da escludere,
    restituisce una lista di rettangoli risultanti.
    """
    candidates = [full_area]
    for ex in exclusions:
        new_candidates = []
        for cand in candidates:
            new_candidates.extend(subtract_rect(cand, ex))
        candidates = new_candidates
    return candidates

def select_primary_area(candidate_areas):
    """Seleziona l'area candidata con la superficie maggiore."""
    if not candidate_areas:
        return None
    return max(candidate_areas, key=lambda r: r[2]*r[3])

##############################################################################
# FUNZIONI DI CARICAMENTO E MERGE DEI DATI
##############################################################################

def load_pages(json_path: str) -> list:
    """Carica il file JSON e restituisce la lista delle pagine."""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            pages = json.load(f)
        return pages
    except Exception as e:
        logging.error(f"Errore durante il caricamento del JSON '{json_path}': {e}")
        sys.exit(1)

def merge_data(original: list, translation: list) -> list:
    """
    Unisce i dati dei due JSON.
    Se entrambi gli elenchi hanno il campo "file", il merge avviene per tale chiave;
    altrimenti, viene usato l’ordine degli elementi.
    """
    merged = []
    if translation and translation[0].get("file"):
        translation_dict = {entry["file"]: entry for entry in translation if "file" in entry}
        for orig in original:
            file_key = orig.get("file")
            if file_key and file_key in translation_dict:
                merged_entry = orig.copy()
                merged_entry.update(translation_dict[file_key])
                merged.append(merged_entry)
            else:
                merged.append(orig)
    else:
        for i, orig in enumerate(original):
            if i < len(translation):
                merged_entry = orig.copy()
                merged_entry.update(translation[i])
                merged.append(merged_entry)
            else:
                merged.append(orig)
    return merged

##############################################################################
# FUNZIONE PER DISEGNARE TESTO CON DIMENSIONE ADATTIVA
##############################################################################

def draw_adaptive_text(pdf, text, area, max_font_size=10, font_name="Times-Roman", line_spacing=2, min_font_size=6):
    """
    Disegna il testo 'text' nell'area (x, y, w, h) adattando la dimensione del font
    in modo che il testo entri nell'area, partendo da 'max_font_size' e riducendo fino a 'min_font_size'.
    Viene applicato un margine interno di 2 punti su sinistra e destra.
    """
    x, y, width, height = area
    chosen_font_size = max_font_size
    # Prova a trovare la dimensione del font adatta
    while chosen_font_size >= min_font_size:
        lines = simpleSplit(text, font_name, chosen_font_size, width - 4)
        line_height = chosen_font_size + line_spacing
        required_height = len(lines) * line_height
        if required_height <= height:
            break
        chosen_font_size -= 0.5
    pdf.setFont(font_name, chosen_font_size)
    current_y = y + height - chosen_font_size  # inizia dalla parte superiore dell'area
    for line in lines:
        pdf.drawString(x + 2, current_y, line)
        current_y -= (chosen_font_size + line_spacing)

##############################################################################
# FUNZIONE DI LAYOUT DELLA PAGINA
##############################################################################

def layout_page(pdf, page, images_dir, page_width, page_height):
    """
    Costruisce la pagina PDF secondo il seguente schema:
      1. Copia l'immagine originale intera.
      2. Disegna il separatore (basato su 'separator_y').
      3. Per le didascalie: controlla il campo "captions" (lista).
         Se sono presenti più elementi e le coordinate corrispondenti in forma multipla,
         itera su tutti; altrimenti usa il primo elemento.
         Se un elemento è un dizionario, estrae il testo dal campo "text".
      4. Determina l'area libera per il testo principale (solitamente sopra il separatore,
         escludendo eventuali aree immagine) e la copre (whitening) prima di scrivere il testo.
    """
    # 1. Disegna l'immagine originale come sfondo.
    image_file = page.get("file")
    if image_file:
        image_path = os.path.join(images_dir, image_file)
        if os.path.exists(image_path):
            pdf.drawImage(image_path, 0, 0, width=page_width, height=page_height,
                          preserveAspectRatio=True, mask='auto')
        else:
            logging.warning(f"Immagine non trovata: {image_path}")

    # 2. Disegna il separatore (convertendo separator_y in coordinate PDF)
    sep_y = page.get("separator_y") or 1350
    sep_y_pt = sep_y * CONVERSION_FACTOR
    new_sep_y = page_height - sep_y_pt
    pdf.setStrokeColorRGB(0, 0, 1)
    pdf.line(0, new_sep_y, page_width, new_sep_y)

    # 3. Gestione delle didascalie ("captions")
    # Cerca il campo "captions" (lista)
    captions = page.get("captions", [])
    caption_coords = page.get("caption_coordinates", None)
    if captions:
        if caption_coords:
            # Se caption_coords è una lista di coordinate (multipla) oppure singola
            if isinstance(caption_coords[0], (list, tuple)):
                # Itera su ogni didascalia e la rispettiva area
                for cap_text, cap_area in zip(captions, caption_coords):
                    # Se l'elemento è un dizionario, estrai il valore testuale dal campo "text"
                    if isinstance(cap_text, dict):
                        cap_text = cap_text.get('text', '')
                    # Conversione delle coordinate da unità originali a punti
                    x_cap = float(cap_area[0]) * CONVERSION_FACTOR
                    y_cap = float(cap_area[1]) * CONVERSION_FACTOR
                    w_cap = float(cap_area[2]) * CONVERSION_FACTOR
                    h_cap = float(cap_area[3]) * CONVERSION_FACTOR
                    new_y_cap = page_height - (y_cap + h_cap)
                    # Copri l'area della didascalia (whitening)
                    pdf.setFillColorRGB(1, 1, 1)
                    pdf.rect(x_cap, new_y_cap, w_cap, h_cap, stroke=0, fill=1)
                    # Scrivi il testo della didascalia con formato adattivo
                    caption_area = (x_cap, new_y_cap, w_cap, h_cap)
                    draw_adaptive_text(pdf, cap_text, caption_area, max_font_size=10)
            else:
                # Se le coordinate sono singole, usa la prima didascalia
                cap_area = caption_coords
                x_cap = float(cap_area[0]) * CONVERSION_FACTOR
                y_cap = float(cap_area[1]) * CONVERSION_FACTOR
                w_cap = float(cap_area[2]) * CONVERSION_FACTOR
                h_cap = float(cap_area[3]) * CONVERSION_FACTOR
                new_y_cap = page_height - (y_cap + h_cap)
                pdf.setFillColorRGB(1, 1, 1)
                pdf.rect(x_cap, new_y_cap, w_cap, h_cap, stroke=0, fill=1)
                caption_text = captions[0]
                if isinstance(caption_text, dict):
                    caption_text = caption_text.get('text', '')
                caption_area = (x_cap, new_y_cap, w_cap, h_cap)
                draw_adaptive_text(pdf, caption_text, caption_area, max_font_size=10)
        else:
            logging.warning("Didascalie fornite ma nessun 'caption_coordinates' trovato; salto l'elaborazione delle didascalie.")

    # 4. Determina l'area libera per il testo principale (solitamente sopra il separatore)
    # Utilizza margini più stretti: margin = 15, padding = 10
    margin = 15
    padding = 10
    free_area = (margin,
                 new_sep_y + padding,
                 page_width - 2 * margin,
                 (page_height - margin) - (new_sep_y + padding))
    
    # Se esistono aree immagine (image_coordinates) che invadono la free_area, escludile
    exclusions = []
    if page.get("image_coordinates"):
        ic = page.get("image_coordinates")
        x_img = float(ic.get("x", 0)) * CONVERSION_FACTOR
        y_img = float(ic.get("y", 0)) * CONVERSION_FACTOR
        w_img = float(ic.get("w", 0)) * CONVERSION_FACTOR
        h_img = float(ic.get("h", 0)) * CONVERSION_FACTOR
        new_y_img = page_height - (float(ic.get("y", 0)) * CONVERSION_FACTOR + h_img)
        if new_y_img + h_img > new_sep_y:
            exclusions.append((x_img, new_y_img, w_img, h_img))
    
    candidate_areas = subtract_rectangles(free_area, exclusions)
    text_area = select_primary_area(candidate_areas) or free_area

    # Copri l'area destinata al testo principale con un rettangolo bianco (whitening)
    pdf.setFillColorRGB(1, 1, 1)
    pdf.rect(text_area[0], text_area[1], text_area[2], text_area[3], stroke=0, fill=1)

    # Scrivi il testo tradotto (campo "content") in maniera adattiva
    content_text = page.get("content", "")
    draw_adaptive_text(pdf, content_text, text_area, max_font_size=10)

    # 5. Footer (facoltativo)
    pdf.setFont("Times-Roman", 10)
    pdf.drawCentredString(page_width / 2, 20, f"Page {page.get('page_number', '')}")
    pdf.showPage()

##############################################################################
# CREAZIONE DEL PDF FINALE E FUNZIONE PRINCIPALE
##############################################################################

def create_final_pdf(pages: list, images_dir: str, output_pdf: str) -> None:
    """
    Crea il PDF finale elaborando ogni pagina secondo la logica descritta.
    """
    c = canvas.Canvas(output_pdf)
    page_width, page_height = FIXED_PAGE_SIZE
    c.setPageSize((page_width, page_height))
    
    for page in pages:
        layout_page(c, page, images_dir, page_width, page_height)
    
    c.save()
    logging.info(f"Final PDF generato: {output_pdf}")

def main():
    parser = argparse.ArgumentParser(
        description="Genera il PDF finale copiando l'immagine originale, lasciando intatte le aree di immagini e bibliografia (sotto il separatore) e riscrivendo didascalie e testo principale in maniera adattiva."
    )
    parser.add_argument("--input", required=False, default=".", help="Cartella di input (default: cartella corrente)")
    parser.add_argument("--output", required=False, default="final.pdf", help="Nome del PDF di output (default: final.pdf)")
    args = parser.parse_args()

    input_folder = os.path.abspath(args.input)
    # Carica i due file JSON: il file originale e quello della traduzione
    bookindex_path = os.path.join(input_folder, "bookindex.json")
    translation_path = os.path.join(input_folder, "godstaritanobiblio.json")
    original_data = load_pages(bookindex_path)
    translation_data = load_pages(translation_path)
    
    # Unisce i dati: il file originale viene aggiornato con i campi tradotti
    merged_pages = merge_data(original_data, translation_data)
    
    if not merged_pages:
        logging.error("Nessuna pagina unita trovata dai JSON.")
        sys.exit(1)
    
    output_pdf_path = os.path.join(input_folder, args.output)
    create_final_pdf(merged_pages, input_folder, output_pdf_path)

if __name__ == "__main__":
    main()
