import cv2
import pytesseract
import os
import json
import logging
import numpy as np
import argparse
import re
import markdown  # pip install markdown
from pathlib import Path
from PIL import Image

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def normalize_coords(coords):
    """Normalize coordinates to a list of four integers [x, y, w, h]."""
    if coords is None:
        return None
    if isinstance(coords, dict):
        try:
            return [int(coords.get("x", 0)), int(coords.get("y", 0)),
                    int(coords.get("w", 0)), int(coords.get("h", 0))]
        except Exception as e:
            logging.error(f"Error normalizing dict coords {coords}: {e}")
            return None
    elif isinstance(coords, (list, tuple)):
        try:
            return [int(c) for c in coords]
        except Exception as e:
            logging.error(f"Error normalizing list coords {coords}: {e}")
            return None
    else:
        logging.error(f"Unknown coords format: {coords}")
        return None

def crop_region(image, coords):
    """Crop a region from a PIL image using normalized coordinates."""
    norm_coords = normalize_coords(coords)
    if norm_coords is None:
        return None
    try:
        x, y, w, h = norm_coords
        return image.crop((x, y, x + w, y + h))
    except Exception as e:
        logging.error(f"crop_region error with coords {coords}: {e}")
        return None

def mask_exclusion_areas(pil_img, regions):
    """Mask (whiten out) regions in the image specified by a list of [x, y, w, h]."""
    cv_img = np.array(pil_img.convert('RGB'))
    for coords in regions:
        norm_coords = normalize_coords(coords)
        if norm_coords is None:
            continue
        try:
            x, y, w, h = norm_coords
            cv_img[y:y + h, x:x + w] = [255, 255, 255]
        except Exception as e:
            logging.error(f"mask_exclusion_areas error with coords {coords}: {e}")
    return Image.fromarray(cv_img)

def run_ocr_on_image(pil_img, config='--oem 3 --psm 6 -c preserve_interword_spaces=1', lang='eng'):
    """Run OCR on a PIL image and return the extracted text."""
    try:
        text = pytesseract.image_to_string(pil_img, config=config, lang=lang).strip()
        return text
    except Exception as e:
        logging.error(f"OCR error: {e}")
        return ""

def convert_markdown_to_html(text):
    """
    Converte un testo formattato in markdown in HTML.
    Utilizza l'estensione "nl2br" per trasformare le nuove righe in <br/>.
    """
    html = markdown.markdown(text, extensions=["nl2br"])
    return html

def convert_page_markdown(page):
    """
    Converte il testo della pagina in HTML:
      - Se il campo "content" (inizialmente uguale a "main_text") non è vuoto e non è
        già stato convertito (flag "markdown_converted"), allora lo converte in HTML.
      - Il risultato viene salvato in "content" e viene impostato il flag "markdown_converted".
      - Rimuove eventualmente il campo "main_text".
    """
    content = page.get("content", "")
    if not content:
        return page
    if page.get("markdown_converted", False):
        return page

    new_content = convert_markdown_to_html(content)
    page["content"] = new_content
    page["markdown_converted"] = True
    page.pop("main_text", None)
    return page

def format_header(text):
    """
    Format a header using HTML markup.
    In questo esempio il testo viene centrato, ingrandito e reso in grassetto,
    con newline prima e dopo.
    """
    return "\n\n<b><center style='font-size: larger;'>" + text + "</center></b>\n\n"

def process_record(record):
    """
    Riordina le coordinate per le didascalie:
      - Se esiste già "caption_coordinates", elimina le altre.
      - Altrimenti, se esiste "internal_caption_coordinates" o "external_caption_coordinates",
        assegna il primo disponibile a "caption_coordinates" e elimina gli altri.
    """
    if record.get("caption_coordinates"):
        record.pop("internal_caption_coordinates", None)
        record.pop("external_caption_coordinates", None)
    else:
        if record.get("internal_caption_coordinates"):
            record["caption_coordinates"] = record["internal_caption_coordinates"]
        elif record.get("external_caption_coordinates"):
            record["caption_coordinates"] = record["external_caption_coordinates"]
        record.pop("internal_caption_coordinates", None)
        record.pop("external_caption_coordinates", None)
    return record

def process_page(image_path, page_info):
    """
    Processa una singola pagina:
      - Per le pagine indice, esegue l'OCR e restituisce il testo indice.
      - Per le pagine principali:
          1. Se presente "caption_coordinates", estrae l'area didascalia e ne esegue l'OCR.
          2. Se è presente un "separator_y", esclude l'area sottostante.
          3. Maschera le aree escluse (didascalia, area sotto separator_y ed eventuali aree immagine)
             e esegue l'OCR sul testo principale.
          4. Rileva e formatta gli header nel testo principale.
      - Imposta il campo "content" uguale al testo principale (con header formattati) e lo converte in HTML.
    """
    try:
        original_image = Image.open(image_path)
    except Exception as e:
        logging.error(f"Error opening image {image_path}: {e}")
        return None

    page_number = page_info.get("page_number")
    image_present = page_info.get("type", "image-absent") == "image-present"
    page_type = page_info.get("page_type", "main")

    # Gestione per pagine indice
    if page_type == "index":
        index_text = run_ocr_on_image(original_image)
        page_output = {
            "page_type": page_type,
            "page_number": page_number,
            "index_text": index_text
        }
        page_output["content"] = index_text
        page_output = convert_page_markdown(page_output)
        return page_output

    captions = []
    exclusion_regions = []

    # Elaborazione dell'area didascalia (se presente, unificata in "caption_coordinates")
    if page_info.get("caption_coordinates"):
        coords = page_info["caption_coordinates"]
        caption_img = crop_region(original_image, coords)
        if caption_img is not None:
            text_caption = run_ocr_on_image(caption_img)
            if text_caption:
                captions.append({"source": "caption", "text": text_caption.replace("\n", " ").strip()})
                exclusion_regions.append(coords)
        else:
            logging.error("Caption region could not be cropped.")

    # Esclusione dell'area sotto separator_y (senza estrarne il testo)
    if page_info.get("separator_y") is not None:
        try:
            separator_y = int(page_info["separator_y"])
            width, height = original_image.size
            if 0 < separator_y < height:
                exclusion_regions.append([0, separator_y, width, height - separator_y])
            else:
                logging.warning(f"separator_y value {separator_y} is out of bounds for image height {height}.")
        except Exception as e:
            logging.error(f"Error processing separator_y: {e}")

    # Esclusione di ulteriori aree immagine, se presenti.
    if page_info.get("image_coordinates"):
        exclusion_regions.append(page_info["image_coordinates"])

    # Elaborazione del testo principale escludendo le regioni sopra.
    main_text_image = mask_exclusion_areas(original_image, exclusion_regions)
    main_text_raw = run_ocr_on_image(main_text_image)
    main_text = " ".join(main_text_raw.replace("\n", " ").split())

    # --- Gestione degli header ---
    # Definiamo la classe di lettere (includendo lettere accentate)
    letter_class = r'A-ZÀ-ÖØ-Þ'
    # Pattern base per rilevare sequenze in maiuscolo (almeno una parola di 4+ lettere)
    header_pattern = (
        r'\b((?:[' + letter_class + r']+(?:\s+[' + letter_class + r']+)*))\b'
    )
    # Lista di eccezioni (termini comuni che non devono essere considerati header)
    exceptions = {"NASA", "KRONIA", "KRONOS", "USA", "EU", "AEON", "UK"}
    header_matches = []
    headers_found = []
    for match in re.finditer(header_pattern, main_text):
        header_text = match.group(1).strip()
        # Applichiamo le eccezioni:
        if header_text in exceptions:
            continue
        # Se è una singola parola e consiste solo di lettere che potrebbero formare un numero romano, escludila
        if " " not in header_text and re.fullmatch(r'[IVXLCDM]+', header_text):
            continue
        # Qui potresti aggiungere altre eccezioni simili, per esempio:
        # Escludi se header_text è un acronimo molto breve (ad esempio 2 lettere) ma non se è TAO (3 lettere)
        if len(header_text) <= 2:
            continue
        # Accetta il candidato
        start_index = match.start()
        end_index = match.end()
        header_matches.append((start_index, end_index, header_text))
        headers_found.append(header_text)

    # Sostituisci gli header nel testo, elaborando in ordine inverso per non alterare gli indici
    header_matches_sorted = sorted(header_matches, key=lambda x: x[0], reverse=True)
    for start, end, header_text in header_matches_sorted:
        formatted = format_header(header_text)
        main_text = main_text[:start] + formatted + main_text[end:]

    # Costruiamo l'output della pagina
    page_output = {
        "page_type": page_type,
        "image_present": image_present,
        "page_number": page_number,
        "main_text": main_text,
        "captions": captions,
        "headers": headers_found  # Solo i testi degli header rilevati
    }
    # Impostiamo "content" uguale a "main_text" e applichiamo la conversione in HTML.
    page_output["content"] = page_output["main_text"]
    page_output = convert_page_markdown(page_output)
    return page_output

def process_images(input_dir):
    """
    Processa le immagini utilizzando il file JSON (bookindex.json).
    L'output viene suddiviso in chunk da 3 pagine ciascuno.
    Integra anche la logica per riordinare le coordinate delle didascalie.
    """
    script_dir = Path(input_dir)
    input_file = script_dir / "bookindex.json"
    output_dir = script_dir / "chunks"
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_file.exists():
        logging.error("ERROR: bookindex.json not found!")
        return

    try:
        with open(input_file, "r", encoding="utf-8") as f:
            book_index = json.load(f)
    except Exception as e:
        logging.error(f"ERROR loading bookindex.json: {e}")
        return

    # Riordina i record per la didascalia
    book_index = [process_record(record) for record in book_index]

    all_pages = []
    chunk_counter = 1
    total_pages = len(book_index)
    for index, page_info in enumerate(book_index, start=1):
        image_path = script_dir / page_info.get("file", "")
        if not image_path.exists():
            logging.warning(f"Missing image: {page_info.get('file', 'UNKNOWN')}, skipping.")
            continue

        logging.info(f"Processing {page_info.get('file', 'UNKNOWN')} ({index}/{total_pages})")
        page_json = process_page(image_path, page_info)
        if page_json:
            all_pages.append(page_json)

        # Salva ogni chunk da 3 pagine
        if len(all_pages) == 3:
            chunk_file = output_dir / f"chunk_{chunk_counter:03d}.json"
            with open(chunk_file, "w", encoding="utf-8") as f:
                json.dump(all_pages, f, indent=4, ensure_ascii=False)
            logging.info(f"Saved chunk: {chunk_file} (contains {len(all_pages)} page(s))")
            chunk_counter += 1
            all_pages = []

    # Salva eventuali pagine residue in un ultimo chunk
    if all_pages:
        chunk_file = output_dir / f"chunk_{chunk_counter:03d}.json"
        with open(chunk_file, "w", encoding="utf-8") as f:
            json.dump(all_pages, f, indent=4, ensure_ascii=False)
        logging.info(f"Saved chunk: {chunk_file} (contains {len(all_pages)} page(s))")

    logging.info(f"Processing complete! Chunks saved in {output_dir}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="OCR Script aggiornato con conversione markdown -> HTML, rilevazione e formattazione degli header (con eccezioni) e output in chunk da 3 pagine ciascuno."
    )
    parser.add_argument("--input", default=".", help="Directory contenente le immagini e il file bookindex.json")
    args = parser.parse_args()
    process_images(args.input)
