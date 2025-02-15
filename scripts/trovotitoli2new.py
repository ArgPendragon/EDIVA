#!/usr/bin/env python3
import json
import re
import sys
import os

def format_header(text):
    """
    Returns the text formatted with markup.
    In this example we use HTML to center, enlarge, and embolden the text,
    with newline breaks before and after.
    Change this markup as needed.
    """
    return "\n\n<b><center style='font-size: larger;'>" + text + "</center></b>\n\n"

def process_page(page):
    """
    Processes the "content" field of a page.
    
    - If the content begins with a chapter header (e.g. "Capitolo 6 Satellite Primordiale ..."),
      it extracts two parts:
         1. The literal "Capitolo <number>" (e.g. "Capitolo 6")
         2. The chapter title (e.g. "Satellite Primordiale"),
      up to the first occurrence of a normal header in full caps.
      Both parts are formatted separately and placed at the top of the text.
    
    - In the rest of the content, any “normal” header (a sequence of uppercase words,
      where at least one word has 4+ letters) is detected, its metadata (text, start index,
      and position) is recorded, and the header is replaced with its formatted version
      (which includes newlines and markup).
    
    - To be safe on data already processed with new formatting (or that contain our marker),
      we first check if the content already contains the formatting marker or a flag.
      If so, we simply return the page unchanged.
    
    - Finally, the formatted content is saved back into the page along with updated fields.
    """
    content = page.get("content", "")
    
    # If content is a list (from a previous processing), join it into a single string.
    if isinstance(content, list):
        content = "\n".join(content)
    
    if not content:
        return page

    # Check if the content already seems to be processed by the new version.
    # We assume that our inserted markup <b><center style='font-size: larger;'> is unique.
    if page.get("new_formatting_applied", False) or "<b><center style='font-size: larger;'>" in content:
        # Already processed by new formatting—skip further modifications.
        return page

    # --- Process Chapter Header (Capitolo) if present ---
    letter_class = r'A-ZÀ-ÖØ-Þ'  # uppercase letters including accented ones
    capitolo = None
    formatted_top = ""
    
    # If the text starts with "Capitolo", attempt to extract chapter info.
    if content.startswith("Capitolo"):
        # Extract the "Capitolo <number>" token.
        capitolo_num_match = re.match(r'^(Capitolo\s+\d+)', content)
        if capitolo_num_match:
            capitolo_num = capitolo_num_match.group(1)
            remainder = content[len(capitolo_num):].lstrip()
            # Assume the chapter title extends until the first occurrence of a normal header (full caps).
            uppercase_header_pattern = r'\b([' + letter_class + r']+(?:\s+[' + letter_class + r']+)+)\b'
            header_match = re.search(uppercase_header_pattern, remainder)
            if header_match:
                # Everything before the first full caps header is the chapter title.
                chapter_title = remainder[:header_match.start()].rstrip()
                if not chapter_title:
                    # Fallback: if nothing is found, take at least the first word.
                    chapter_title = remainder.split()[0]
                remainder = remainder[header_match.start():]
            else:
                # If no subsequent header is found, assume the rest is the title.
                chapter_title = remainder
                remainder = ""
            capitolo = {"numero": capitolo_num, "titolo": chapter_title}
            # Build the formatted block: format the chapter literal and the title separately.
            formatted_top += format_header(capitolo_num)
            formatted_top += format_header(chapter_title)
            # Update content to be just the remaining part.
            content = remainder

    # --- Process normal headers in the remaining content ---
    # This pattern detects sequences of uppercase words (using our defined letter_class)
    # where at least one word is 4+ letters long.
    header_pattern = (
        r'\b(?=(?:[' + letter_class + r']+\s+)*[' + letter_class + r']{4,}\b)'
        r'([' + letter_class + r']+(?:\s+[' + letter_class + r']+)*)\b'
    )
    headers_found = []
    for match in re.finditer(header_pattern, content):
        header_text = match.group(1)
        start_index = match.start()
        total_length = len(content)
        ratio = start_index / total_length if total_length > 0 else 0
        if ratio < 0.33:
            pos = "inizio"
        elif ratio > 0.66:
            pos = "fine"
        else:
            pos = "mezzo"
        headers_found.append({
            "text": header_text,
            "start": start_index,
            "position": pos
        })

    # Replace each header with its formatted version.
    # Process in reverse order to avoid shifting indices.
    headers_found_sorted = sorted(headers_found, key=lambda h: h["start"], reverse=True)
    for header in headers_found_sorted:
        start = header["start"]
        end = start + len(header["text"])
        formatted = format_header(header["text"])
        content = content[:start] + formatted + content[end:]

    # Combine the formatted chapter block (if any) with the processed content.
    new_content = formatted_top + content

    # Update the page with new fields and formatted content.
    page["content"] = new_content
    if headers_found:
        page["headers"] = headers_found
    if capitolo:
        page["capitolo"] = capitolo

    # Mark the page as having been processed by the new script.
    page["new_formatting_applied"] = True

    return page

def process_json_file(infile, outfile):
    """Loads the JSON file, processes each page, and writes the updated file."""
    try:
        with open(infile, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Errore durante il caricamento del JSON: {e}")
        sys.exit(1)

    if not isinstance(data, list):
        print("Il file JSON non contiene una lista di pagine.")
        sys.exit(1)

    new_data = []
    for page in data:
        new_page = process_page(page)
        new_data.append(new_page)

    try:
        with open(outfile, 'w', encoding='utf-8') as f:
            json.dump(new_data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Errore durante la scrittura del file JSON: {e}")
        sys.exit(1)
    print(f"Elaborate {len(new_data)} pagine. File aggiornato salvato in: {outfile}")

if __name__ == '__main__':
    # Se non vengono passati argomenti, chiede in input i percorsi dei file, con default
    # presi dalle variabili ambientali (o valori predefiniti se le variabili non esistono)
    if len(sys.argv) < 3:
        default_input = os.environ.get("INPUT_FOLDER", "input.json")
        default_output = os.environ.get("OUTPUT_FOLDER", "output.json")
        
        input_val = input(f"Inserisci il file di input [{default_input}]: ").strip()
        if input_val == "":
            input_file = default_input
        else:
            input_file = input_val
            os.environ["INPUT_FOLDER"] = input_file  # aggiorna la variabile ambientale

        output_val = input(f"Inserisci il file di output [{default_output}]: ").strip()
        if output_val == "":
            output_file = default_output
        else:
            output_file = output_val
            os.environ["OUTPUT_FOLDER"] = output_file  # aggiorna la variabile ambientale
    else:
        # Se vengono forniti come argomenti, li usa e aggiorna le variabili ambientali se necessario
        input_file = sys.argv[1]
        output_file = sys.argv[2]
        if os.environ.get("INPUT_FOLDER", "input.json") != input_file:
            os.environ["INPUT_FOLDER"] = input_file
        if os.environ.get("OUTPUT_FOLDER", "output.json") != output_file:
            os.environ["OUTPUT_FOLDER"] = output_file

    process_json_file(input_file, output_file)
