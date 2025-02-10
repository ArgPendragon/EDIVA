#!/usr/bin/env python3
import os
import sys
import json
import logging
import argparse
import tempfile

from reportlab.pdfgen import canvas
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase.pdfmetrics import stringWidth

# Per la conversione PDF -> immagine (richiede pdf2image e Poppler)
from pdf2image import convert_from_path

# Configurazione del logging
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Costanti
DPI = 150
CONVERSION_FACTOR = 72 / DPI  # circa 0.48
FIXED_PAGE_SIZE = (576, 720)  # (larghezza, altezza) in punti
MIN_AREA_RATIO = 0.01        # 1% dell'area della pagina

##############################################################################
# FUNZIONI DI SUPPORTO PER OPERAZIONI GEOMETRICHE
##############################################################################

def subtract_rect(candidate, exclusion):
    """
    Sottrae il rettangolo 'exclusion' dal rettangolo 'candidate'.
    Entrambi sono tuple (x, y, w, h) in coordinate PDF (origine in basso a sinistra).
    Restituisce una lista (eventualmente vuota) dei rettangoli risultanti.
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
    if inter_top < yA + hA:
        results.append((xA, inter_top, wA, (yA + hA) - inter_top))
    if inter_bottom > yA:
        results.append((xA, yA, wA, inter_bottom - yA))
    if inter_left > xA:
        results.append((xA, inter_bottom, inter_left - xA, inter_top - inter_bottom))
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
    best = max(candidate_areas, key=lambda r: r[2] * r[3])
    logging.debug(f"Selezionata area migliore per il testo: {best} (area = {best[2]*best[3]:.2f} punti²)")
    return best

##############################################################################
# FUNZIONI DI CARICAMENTO E MERGE DEI DATI
##############################################################################

def load_pages(json_path: str) -> list:
    """Carica il file JSON e restituisce la lista delle pagine."""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            pages = json.load(f)
        logging.info(f"Caricate {len(pages)} pagine da {json_path}")
        return pages
    except Exception as e:
        logging.error(f"Errore durante il caricamento del JSON '{json_path}': {e}")
        sys.exit(1)

def merge_data(original: list, translation: list, last_text_page: int) -> list:
    """
    Unisce i dati dei due JSON basandosi sulla chiave "page_number".
    - Se una pagina ha "page_number" nullo o maggiore di last_text_page, la lascia inalterata.
    - Altrimenti, se esiste una corrispondenza in translation (per page_number), esegue il merge.
    """
    merged = []
    translation_dict = { entry["page_number"]: entry for entry in translation if entry.get("page_number") is not None }
    for orig in original:
        page_num = orig.get("page_number")
        if page_num is None or (isinstance(page_num, int) and page_num > last_text_page):
            logging.debug(f"Lasciata inalterata pagina con page_number {page_num}")
            merged.append(orig)
        else:
            if page_num in translation_dict:
                merged_entry = orig.copy()
                merged_entry.update(translation_dict[page_num])
                logging.debug(f"Merge eseguito per pagina {page_num}")
                merged.append(merged_entry)
            else:
                logging.debug(f"Nessuna traduzione trovata per pagina {page_num}")
                merged.append(orig)
    return merged

##############################################################################
# FUNZIONE PER DISEGNARE TESTO (ADATTIVO)
##############################################################################

def draw_adaptive_text(pdf, text, area, max_font_size=10, font_name="Times-Roman",
                       line_spacing=2, min_font_size=6, alignment="left", headers=None):
    """
    Disegna il testo 'text' nell'area (x, y, w, h) adattando la dimensione del font affinché
    il testo entri nell'area, partendo da 'max_font_size' e riducendo fino a 'min_font_size'.
    Viene applicato un margine interno di 2 punti su sinistra e destra.
    """
    pdf.setFillColorRGB(0, 0, 0)
    x, y, width, height = area
    chosen_font_size = max_font_size
    while chosen_font_size >= min_font_size:
        lines = simpleSplit(text, font_name, chosen_font_size, width - 4)
        line_height = chosen_font_size + line_spacing
        extra = 0
        if headers:
            for line in lines:
                for header in headers:
                    if header.strip().lower() in line.strip().lower():
                        extra += 4
                        break
        required_height = len(lines) * line_height + extra
        if required_height <= height:
            break
        chosen_font_size -= 0.5
    pdf.setFont(font_name, chosen_font_size)
    current_y = y + height - chosen_font_size
    for i, line in enumerate(lines):
        is_header = False
        if headers:
            for header in headers:
                if header.strip().lower() in line.strip().lower():
                    is_header = True
                    break
        if is_header:
            pdf.setFont("Times-Bold", chosen_font_size)
            pdf.drawCentredString(x + width/2, current_y, line)
            current_y -= (chosen_font_size + line_spacing + 4)
            pdf.setFont(font_name, chosen_font_size)
        else:
            if alignment == "center":
                pdf.drawCentredString(x + width/2, current_y, line)
            elif alignment == "justify" and i < len(lines) - 1:
                words = line.split()
                if len(words) > 1:
                    total_words_width = sum(stringWidth(word, font_name, chosen_font_size) for word in words)
                    available_space = (width - 4)
                    extra_space = (available_space - total_words_width) / (len(words) - 1)
                    cur_x = x + 2
                    for j, word in enumerate(words):
                        pdf.drawString(cur_x, current_y, word)
                        cur_x += stringWidth(word, font_name, chosen_font_size)
                        if j < len(words) - 1:
                            cur_x += extra_space
                else:
                    pdf.drawString(x + 2, current_y, line)
            else:
                pdf.drawString(x + 2, current_y, line)
            current_y -= (chosen_font_size + line_spacing)

##############################################################################
# FUNZIONE DI LAYOUT DELLA PAGINA
##############################################################################

def layout_page(pdf, page, images_dir, page_width, page_height, last_text_page):
    """
    Costruisce la pagina:
      - Se la pagina è da lasciare inalterata (page_number è None oppure maggiore di last_text_page)
        inserisce semplicemente l’immagine JPG originale.
      - Altrimenti, disegna l’immagine originale come sfondo e sovrascrive didascalie e testo
        secondo le specifiche (sostituendo il testo in inglese con quello italiano).
    """
    page_num = page.get("page_number")
    if page_num is None or (isinstance(page_num, int) and page_num > last_text_page):
        # Pagina non modificata: inserisce l'immagine originale così com'è.
        image_file = page.get("file")
        if image_file:
            image_path = os.path.join(images_dir, image_file)
            if os.path.exists(image_path):
                pdf.drawImage(image_path, 0, 0, width=page_width, height=page_height,
                              preserveAspectRatio=True, mask='auto')
            else:
                logging.warning(f"Immagine non trovata: {image_path}")
        else:
            logging.warning("Nessun file immagine specificato per la pagina non modificata")
        pdf.showPage()
        return

    # Per le pagine modificate: disegna lo sfondo (l'immagine originale)
    image_file = page.get("file")
    if image_file:
        image_path = os.path.join(images_dir, image_file)
        if os.path.exists(image_path):
            pdf.drawImage(image_path, 0, 0, width=page_width, height=page_height,
                          preserveAspectRatio=True, mask='auto')
        else:
            logging.warning(f"Immagine non trovata: {image_path}")
    else:
        logging.warning("Nessun file immagine specificato per la pagina modificata")
    
    # Gestione delle didascalie ("captions")
    captions = page.get("captions", [])
    caption_coords = page.get("caption_coordinates", None)
    if captions:
        if caption_coords:
            if isinstance(caption_coords[0], (list, tuple)):
                for cap_text, cap_area in zip(captions, caption_coords):
                    if isinstance(cap_text, dict):
                        cap_text = cap_text.get('text', '')
                    x_cap = float(cap_area[0]) * CONVERSION_FACTOR
                    y_cap = float(cap_area[1]) * CONVERSION_FACTOR
                    w_cap = float(cap_area[2]) * CONVERSION_FACTOR
                    h_cap = float(cap_area[3]) * CONVERSION_FACTOR
                    new_y_cap = page_height - (y_cap + h_cap)
                    logging.debug(f"Elaboro didascalia (center): '{cap_text[:30]}...' a coordinate {x_cap, new_y_cap, w_cap, h_cap}")
                    pdf.setFillColorRGB(1, 1, 1)
                    pdf.rect(x_cap, new_y_cap, w_cap, h_cap, stroke=0, fill=1)
                    caption_area = (x_cap, new_y_cap, w_cap, h_cap)
                    draw_adaptive_text(pdf, cap_text, caption_area, max_font_size=10, alignment="center")
            else:
                cap_area = caption_coords
                x_cap = float(cap_area[0]) * CONVERSION_FACTOR
                y_cap = float(cap_area[1]) * CONVERSION_FACTOR
                w_cap = float(cap_area[2]) * CONVERSION_FACTOR
                h_cap = float(cap_area[3]) * CONVERSION_FACTOR
                new_y_cap = page_height - (y_cap + h_cap)
                logging.debug(f"Elaboro didascalia singola (center) a coordinate {x_cap, new_y_cap, w_cap, h_cap}")
                pdf.setFillColorRGB(1, 1, 1)
                pdf.rect(x_cap, new_y_cap, w_cap, h_cap, stroke=0, fill=1)
                caption_text = captions[0]
                if isinstance(caption_text, dict):
                    caption_text = caption_text.get('text', '')
                caption_area = (x_cap, new_y_cap, w_cap, h_cap)
                draw_adaptive_text(pdf, caption_text, caption_area, max_font_size=10, alignment="center")
        else:
            logging.warning("Didascalie fornite ma nessun 'caption_coordinates' trovato; uso coordinate predefinite.")
            default_coords = [50, 100, 200, 50]  # coordinate predefinite
            x_cap = float(default_coords[0]) * CONVERSION_FACTOR
            y_cap = float(default_coords[1]) * CONVERSION_FACTOR
            w_cap = float(default_coords[2]) * CONVERSION_FACTOR
            h_cap = float(default_coords[3]) * CONVERSION_FACTOR
            new_y_cap = page_height - (y_cap + h_cap)
            pdf.setFillColorRGB(1, 1, 1)
            pdf.rect(x_cap, new_y_cap, w_cap, h_cap, stroke=0, fill=1)
            caption_text = captions[0]
            if isinstance(caption_text, dict):
                caption_text = caption_text.get('text', '')
            caption_area = (x_cap, new_y_cap, w_cap, h_cap)
            draw_adaptive_text(pdf, caption_text, caption_area, max_font_size=10, alignment="center")
    
    # Gestione del testo principale
    margin = 70
    padding = 5
    sep_y = page.get("separator_y") or 1350
    sep_y_pt = sep_y * CONVERSION_FACTOR
    new_sep_y = page_height - sep_y_pt
    free_area = (margin,
                 new_sep_y + padding,
                 page_width - 2 * margin,
                 (page_height - margin) - (new_sep_y + padding))
    logging.debug(f"Area free iniziale: {free_area}")

    exclusions = []
    ic = page.get("image_coordinates")
    if ic:
        if isinstance(ic, list):
            for one_ic in ic:
                x_img = float(one_ic.get("x", 0)) * CONVERSION_FACTOR
                y_img = float(one_ic.get("y", 0)) * CONVERSION_FACTOR
                w_img = float(one_ic.get("w", 0)) * CONVERSION_FACTOR
                h_img = float(one_ic.get("h", 0)) * CONVERSION_FACTOR
                new_y_img = page_height - (float(one_ic.get("y", 0)) * CONVERSION_FACTOR + h_img)
                if new_y_img + h_img > free_area[1]:
                    exclusions.append((x_img, new_y_img, w_img, h_img))
                    logging.debug(f"Escludo immagine: {x_img, new_y_img, w_img, h_img}")
        elif isinstance(ic, dict):
            x_img = float(ic.get("x", 0)) * CONVERSION_FACTOR
            y_img = float(ic.get("y", 0)) * CONVERSION_FACTOR
            w_img = float(ic.get("w", 0)) * CONVERSION_FACTOR
            h_img = float(ic.get("h", 0)) * CONVERSION_FACTOR
            new_y_img = page_height - (float(ic.get("y", 0)) * CONVERSION_FACTOR + h_img)
            if new_y_img + h_img > free_area[1]:
                exclusions.append((x_img, new_y_img, w_img, h_img))
                logging.debug(f"Escludo immagine: {x_img, new_y_img, w_img, h_img}")

    candidate_areas = subtract_rectangles(free_area, exclusions)
    logging.debug(f"Candidate areas: {candidate_areas}")
    if candidate_areas:
        for area in candidate_areas:
            pdf.setFillColorRGB(1, 1, 1)
            pdf.rect(area[0], area[1], area[2], area[3], stroke=0, fill=1)
        best_area = select_primary_area(candidate_areas)
    else:
        best_area = free_area
        logging.warning("Nessuna area candidata ottenuta, uso free_area completa.")
        pdf.setFillColorRGB(1, 1, 1)
        pdf.rect(free_area[0], free_area[1], free_area[2], free_area[3], stroke=0, fill=1)
    logging.debug(f"Utilizzo area migliore per il testo: {best_area}")
    draw_adaptive_text(pdf, page.get("content", ""), best_area, max_font_size=10, alignment="justify", headers=page.get("headers", []))
    pdf.showPage()

##############################################################################
# FUNZIONI PER LA CREAZIONE DEI FILE INTERMEDI E DEL PDF FINALE
##############################################################################

def create_temp_page_pdf(page, images_dir, output_filename, page_width, page_height, last_text_page):
    """
    Crea un PDF temporaneo per una singola pagina usando il layout definito in layout_page.
    """
    c = canvas.Canvas(output_filename, pagesize=(page_width, page_height))
    layout_page(c, page, images_dir, page_width, page_height, last_text_page)
    c.save()
    logging.debug(f"Creato PDF temporaneo: {output_filename}")

def generate_preparatory_images(pages, images_dir, temp_dir, page_width, page_height, last_text_page):
    """
    Per ogni pagina crea un PDF temporaneo e lo converte in un'immagine PNG.
    Restituisce la lista dei percorsi delle immagini generate.
    """
    temp_image_files = []
    for i, page in enumerate(pages):
        temp_pdf_path = os.path.join(temp_dir, f"page_{i:03d}.pdf")
        create_temp_page_pdf(page, images_dir, temp_pdf_path, page_width, page_height, last_text_page)
        
        try:
            # Converte il PDF in immagine (la lista restituita contiene una sola immagine)
            images = convert_from_path(temp_pdf_path, dpi=DPI)
            if images:
                temp_img_path = os.path.join(temp_dir, f"page_{i:03d}.png")
                images[0].save(temp_img_path, "PNG")
                temp_image_files.append(temp_img_path)
                logging.debug(f"Generata immagine preparatoria: {temp_img_path}")
            else:
                logging.error(f"Nessuna immagine generata da {temp_pdf_path}")
        except Exception as e:
            logging.error(f"Errore nella conversione di {temp_pdf_path} a immagine: {e}")
    return temp_image_files

def create_final_pdf_from_images(image_files, output_pdf, page_width, page_height):
    """
    Crea il PDF finale inserendo in ogni pagina le immagini preparatorie generate.
    """
    c = canvas.Canvas(output_pdf, pagesize=(page_width, page_height))
    for img in image_files:
        c.drawImage(img, 0, 0, width=page_width, height=page_height, preserveAspectRatio=True)
        c.showPage()
    c.save()
    logging.info(f"Final PDF generato: {output_pdf}")

##############################################################################
# FUNZIONE PRINCIPALE
##############################################################################

def main():
    parser = argparse.ArgumentParser(
        description="Genera il PDF finale a partire dalle immagini JPG delle pagine del libro. "
                    "Le pagine di indice e bibliografia (page_number nullo o > --last-text-page) vengono inserite inalterate, "
                    "mentre le altre pagine vengono modificate (sovrascrivendo testo e didascalie) secondo il file godstaritanobiblio."
    )
    parser.add_argument("--input", required=False, default=".", help="Cartella di input (default: cartella corrente)")
    parser.add_argument("--output", required=False, default="final.pdf", help="Nome del PDF di output (default: final.pdf)")
    parser.add_argument("--last-text-page", type=int, default=493, help="Ultimo numero di pagina contenente testo (le pagine successive verranno trattate come indice/bibliografia)")
    args = parser.parse_args()

    input_folder = os.path.abspath(args.input)
    bookindex_path = os.path.join(input_folder, "bookindex.json")
    translation_path = os.path.join(input_folder, "godstaritanobiblio.json")
    original_data = load_pages(bookindex_path)
    translation_data = load_pages(translation_path)
    
    merged_pages = merge_data(original_data, translation_data, args.last_text_page)
    
    if not merged_pages:
        logging.error("Nessuna pagina unita trovata dai JSON.")
        sys.exit(1)
    
    output_pdf_path = os.path.join(input_folder, args.output)
    page_width, page_height = FIXED_PAGE_SIZE

    # Creazione di una cartella temporanea per i file intermedi
    with tempfile.TemporaryDirectory() as temp_dir:
        logging.info(f"Utilizzo cartella temporanea: {temp_dir}")
        temp_image_files = generate_preparatory_images(merged_pages, input_folder, temp_dir, page_width, page_height, args.last_text_page)
        create_final_pdf_from_images(temp_image_files, output_pdf_path, page_width, page_height)
        # Al termine del blocco 'with' la cartella temporanea verrà eliminata automaticamente.

if __name__ == "__main__":
    main()
