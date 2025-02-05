import os
import json

def index_files(root_dir):
    # Inizializziamo la struttura dati per i contenuti e per i metadati
    data = {
        "codex": None,
        "novel": None,
        "entries": [],
        "notes": []
    }
    metadata = {}

    # Scorriamo ricorsivamente la directory
    for dirpath, dirnames, filenames in os.walk(root_dir):
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception as e:
                print(f"Errore nella lettura di {filepath}: {e}")
                continue

            # Otteniamo il percorso relativo rispetto alla directory di partenza
            rel_path = os.path.relpath(filepath, root_dir)

            # Gestione del file codex.html
            if filename.lower() == "codex.html":
                data["codex"] = {
                    "path": rel_path,
                    "content": content
                }
                metadata[rel_path] = {
                    "type": "codex",
                    "description": "File HTML del Codex"
                }
            # Gestione del file novel.md
            elif filename.lower() == "novel.md":
                data["novel"] = {
                    "path": rel_path,
                    "content": content
                }
                metadata[rel_path] = {
                    "type": "novel",
                    "description": "Manoscritto completo in markdown"
                }
            # Altri file: in sottocartelle
            else:
                # Se il nome contiene 'entry', lo consideriamo come informazione ufficiale
                if "entry" in filename.lower():
                    data["entries"].append({
                        "path": rel_path,
                        "content": content
                    })
                    metadata[rel_path] = {
                        "type": "entry",
                        "description": "Informazioni ufficiali (personaggi, location, lore)"
                    }
                else:
                    # Altrimenti, lo consideriamo come appunto (note)
                    data["notes"].append({
                        "path": rel_path,
                        "content": content
                    })
                    metadata[rel_path] = {
                        "type": "note",
                        "description": "Appunti vari"
                    }
    return data, metadata

if __name__ == "__main__":
    # Impostiamo la directory di partenza (se non specificato, si assume la cartella corrente)
    root_dir = os.getcwd()
    data, metadata = index_files(root_dir)
    
    # Salviamo i file JSON risultanti
    with open("data.json", "w", encoding="utf-8") as f_data:
        json.dump(data, f_data, indent=2, ensure_ascii=False)
    
    with open("metadata.json", "w", encoding="utf-8") as f_meta:
        json.dump(metadata, f_meta, indent=2, ensure_ascii=False)
    
    print("Indicizzazione completata. Sono stati generati 'data.json' e 'metadata.json'.")
