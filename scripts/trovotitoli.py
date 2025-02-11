#!/usr/bin/env python3
import json
import re
import sys

def process_page(page):
    """
    Processa il campo "content" di una pagina (content è una stringa unica).

    - Se il contenuto inizia con un capitolo nel formato:
         "Capitolo <numero> <HEADER_IN_FULLCAPS> [resto...]"
      allora estrae le prime due parti e le salva nel nuovo campo "capitolo"
      (come dizionario con chiavi "numero" e "titolo"), e rimuove quella porzione
      dal campo "content".

      La parte che segue "Capitolo <numero>" viene catturata come intera stringa in full caps,
      includendo anche lettere accentate, a patto che almeno una parola abbia 4 o più lettere.

    - Se, nel contenuto (dopo eventuale rimozione), vengono trovate altre sottostringhe
      che rappresentano header – cioè sequenze contigue di parole in full caps (inclusi caratteri accentati),
      dove almeno una parola ha 4 o più lettere – allora si registra ciascun header con:
          - "text": il testo trovato (l'intera sequenza),
          - "start": l'indice di partenza nella stringa,
          - "position": "inizio", "mezzo" o "fine" in base al rapporto tra start e lunghezza totale.
      
    - Nel caso in cui il pattern del capitolo sia stato trovato, si assume che l'unico header da
      registrare sia quello estratto (ossia il titolo in full caps) e si imposta il campo "headers"
      come array contenente quella stringa.
      
    Infine il campo "content" viene aggiornato (senza la parte del capitolo) e i nuovi campi vengono aggiunti.
    """
    content = page.get("content", "")
    if not content:
        return page

    capitolo = None
    # Definiamo una classe di caratteri che includa le lettere A-Z e quelle accentate (Unicode Latin-1 uppercase)
    letter_class = r'A-ZÀ-ÖØ-Þ'
    
    # Pattern per il capitolo:
    #   - Group 1: "Capitolo <numero>"
    #   - Group 2: una sequenza di parole in full caps (con lettere appartenenti a [A-ZÀ-ÖØ-Þ])
    #              la lookahead (?=(?:[A-ZÀ-ÖØ-Þ]+\s+)*[A-ZÀ-ÖØ-Þ]{4,}\b) assicura che almeno una parola abbia 4 o più lettere.
    #   - Group 3: il resto della stringa.
    capitolo_pattern = r'^(Capitolo\s+\d+)\s+(?=(?:[' + letter_class + r']+\s+)*[' + letter_class + r']{4,}\b)([' + letter_class + r']+(?:\s+[' + letter_class + r']+)*)(.*)$'
    m = re.match(capitolo_pattern, content)
    if m:
        capitolo_title = m.group(2).strip()
        capitolo = {"numero": m.group(1).strip(), "titolo": capitolo_title}
        # Aggiorna il content rimuovendo la parte corrispondente al capitolo
        content = m.group(3).lstrip()

    # --- Ricerca degli header "normali" ---
    headers_found = []
    total_length = len(content)
    # Pattern per trovare una o più parole in full caps (inclusi caratteri accentati),
    # dove la lookahead garantisce che almeno una parola abbia 4 o più lettere.
    header_pattern = r'\b(?=(?:[' + letter_class + r']+\s+)*[' + letter_class + r']{4,}\b)([' + letter_class + r']+(?:\s+[' + letter_class + r']+)*)\b'
    for match in re.finditer(header_pattern, content):
        header_text = match.group(1)
        start_index = match.start()
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

    # Se abbiamo estratto un capitolo, usiamo come unico header il titolo estratto.
    if capitolo:
        headers_found = [capitolo["titolo"]]

    # Aggiorna il campo "content" e aggiunge i nuovi campi se presenti.
    page["content"] = content
    if headers_found:
        page["headers"] = headers_found
    if capitolo:
        page["capitolo"] = capitolo

    return page

def process_json_file(infile, outfile):
    """Carica il file JSON, elabora ciascuna pagina e riscrive il file aggiornato."""
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
    if len(sys.argv) < 3:
        print("Uso: {} input.json output.json".format(sys.argv[0]))
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]
    process_json_file(input_file, output_file)
