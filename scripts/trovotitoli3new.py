#!/usr/bin/env python3
import json
import sys
import os
import markdown  # pip install markdown

def convert_markdown_to_html(text):
    """
    Converte un testo formattato in markdown in HTML.
    Puoi modificare le conversioni abilitando/disabilitando estensioni
    o post-processando l'HTML per usare solo i tag supportati da Platypus ReportLab.
    Per una conversione minima usiamo le impostazioni di default.
    """
    # Ad esempio, utilizziamo l'estensione "nl2br" per trasformare le nuove righe in <br/>
    html = markdown.markdown(text, extensions=["nl2br"])
    return html

def process_page(page):
    """
    Processa una singola pagina:
      - Se la pagina ha già il flag "markdown_converted", salta la conversione.
      - Altrimenti, se il campo "content" (stringa o lista) contiene markdown,
        lo converte in HTML.
      - Aggiorna il campo "content" con l'HTML convertito e aggiunge il flag.
    """
    content = page.get("content", "")
    # Se il contenuto è una lista (da processamenti precedenti), unisci le righe
    if isinstance(content, list):
        content = "\n".join(content)
    if not content:
        return page
    if page.get("markdown_converted", False):
        return page

    new_content = convert_markdown_to_html(content)
    page["content"] = new_content
    page["markdown_converted"] = True
    return page

def process_json_file(infile, outfile):
    """Carica il file JSON, processa ogni pagina convertendo il markdown in HTML e salva il file aggiornato."""
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

    print(f"Processate {len(new_data)} pagine. File aggiornato salvato come: {outfile}")

if __name__ == '__main__':
    # Recupera le cartelle di default dalle variabili d'ambiente
    default_input_folder = os.environ.get("INPUT_FOLDER", ".")
    default_output_folder = os.environ.get("OUTPUT_FOLDER", ".")
    
    # Definisci i percorsi default per i file (ipotizzando nomi predefiniti)
    default_input_file = os.path.join(default_input_folder, "input.json")
    default_output_file = os.path.join(default_output_folder, "output.json")
    
    if len(sys.argv) < 3:
        print("Argomenti non specificati. Modalità interattiva:")
        inp = input(f"Inserisci il percorso del file di input [{default_input_file}]: ").strip()
        if not inp:
            inp = default_input_file
        else:
            # Se il percorso inserito è diverso, aggiorna la variabile d'ambiente INPUT_FOLDER
            new_input_folder = os.path.dirname(inp)
            if new_input_folder != default_input_folder:
                os.environ["INPUT_FOLDER"] = new_input_folder
        
        outp = input(f"Inserisci il percorso del file di output [{default_output_file}]: ").strip()
        if not outp:
            outp = default_output_file
        else:
            # Se il percorso inserito è diverso, aggiorna la variabile d'ambiente OUTPUT_FOLDER
            new_output_folder = os.path.dirname(outp)
            if new_output_folder != default_output_folder:
                os.environ["OUTPUT_FOLDER"] = new_output_folder
        
        input_file = inp
        output_file = outp
    else:
        # Se vengono forniti gli argomenti da riga di comando, usali e aggiorna le variabili se necessario
        input_file = sys.argv[1]
        output_file = sys.argv[2]
        
        input_folder_arg = os.path.dirname(input_file)
        output_folder_arg = os.path.dirname(output_file)
        if input_folder_arg != default_input_folder:
            os.environ["INPUT_FOLDER"] = input_folder_arg
        if output_folder_arg != default_output_folder:
            os.environ["OUTPUT_FOLDER"] = output_folder_arg

    process_json_file(input_file, output_file)
