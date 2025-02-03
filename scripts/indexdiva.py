import os
import json
import hashlib
import argparse
import re
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.embeddings import OpenAIEmbeddings
from flask import Flask, jsonify

# Definizione categorie basate su parole chiave
DEFAULT_CATEGORY_KEYWORDS = {
    "trama": ["evento", "svolta", "finale", "climax", "inizio", "conclusione", "narrazione", "capitolo", "plot", "story", "narrative"],
    "personaggi": ["protagonista", "antagonista", "ruolo", "sviluppo", "carattere", "nome", "biografia", "character", "hero", "villain", "role", "development"],
    "ambientazioni": ["luogo", "ambientazione", "descrizione", "scenario", "mappa", "setting", "location", "worldbuilding", "map"],
    "concetti": ["mitologia", "scienza", "teoria", "storia", "filosofia", "idea", "concept", "theory", "history", "philosophy"],
    "dialoghi": ["parlò", "disse", "rispose", "esclamò", "dialogo", "conversazione", "dialogue", "conversation", "quote", "speech"]
}

SPECIAL_FOLDERS = ["snippets", "idee"]


def load_custom_keywords(output_folder):
    """Loads custom keywords from a JSON file if it exists."""
    custom_keywords_path = os.path.join(output_folder, "custom_keywords.json")
    if os.path.exists(custom_keywords_path):
        try:
            with open(custom_keywords_path, "r", encoding="utf-8") as f:
                custom_keywords = json.load(f)
            return {**DEFAULT_CATEGORY_KEYWORDS, **custom_keywords}  # Merge with default keywords
        except Exception as e:
            print(f"⚠️ Errore nel caricamento dei custom keywords: {e}")
    return DEFAULT_CATEGORY_KEYWORDS  # Cartelle di brainstorming da identificare a parte


def parse_arguments():
    parser = argparse.ArgumentParser(description="Process files and build an index.")
    parser.add_argument("--input", type=str, required=True, help="Input folder containing the documents.")
    parser.add_argument("--output", type=str, default=None, help="Output folder for the index (defaults to input folder).")
    args = parser.parse_args()
    
    if args.output is None:
        args.output = args.input
    
    return args.input, args.output


def hash_text(text):
    return hashlib.md5(text.encode()).hexdigest()


def clean_text(text):
    """Removes YAML-like metadata and unnecessary headers."""
    text = re.sub(r"^---.*?---", "", text, flags=re.DOTALL)  # Remove YAML front matter
    text = re.sub(r"^#[^\n]*", "", text, flags=re.MULTILINE)  # Remove markdown headers
    return text.strip()


def extract_text_from_file(filepath):
    if not os.path.exists(filepath):
        print(f"⚠️ Errore: Il file {filepath} non esiste.")
        return None
    
    ext = os.path.splitext(filepath)[-1].lower()
    
    if ext == ".json":
        return None  # Skip JSON files explicitly
    
    try:
        if ext in [".txt", ".md"]:
            with open(filepath, "r", encoding="utf-8") as f:
                return clean_text(f.read())
        else:
            print(f"⚠️ Formato non supportato: {ext}")
            return None
    except Exception as e:
        print(f"❌ Errore durante l'elaborazione del file {filepath}: {e}")
        return None


def categorize_text(text):
    """Assigns categories based on detected keywords."""
    categories = []
    lower_text = text.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in lower_text for kw in keywords):
            categories.append(category)
    
    # Assign a category based on metadata (if present)
    if "type: character" in lower_text or "name:" in lower_text or "hero" in lower_text or "villain" in lower_text or "role" in lower_text:
        categories.append("personaggi")
    
    return list(set(categories)) if categories else ["varie"]


def infer_category_from_path(filepath):
    """Infers category based on folder structure."""
    path_parts = filepath.lower().split(os.sep)
    
    if "characters" in path_parts:
        return "personaggi"
    if "locations" in path_parts or "places" in path_parts:
        return "ambientazioni"
    if "concepts" in path_parts:
        return "concetti"
    if "other" in path_parts:
        return "trama" if "plot" in filepath.lower() or "story" in filepath.lower() else "concetti"
    
    return "varie"  # Default category if no path match
    """Infers category based on folder structure."""
    path_parts = filepath.lower().split(os.sep)
    if "characters" in path_parts:
        return "personaggi"
    if "locations" in path_parts or "places" in path_parts:
        return "ambientazioni"
    if "concepts" in path_parts:
        return "concetti"
    return "varie"  # Default category if no path match


def build_index(input_folder, output_folder):
    index = {}
    index_file = os.path.join(output_folder, "indexdiva.json")
    
    for root, _, files in os.walk(input_folder):
        folder_name = os.path.basename(root)
        folder_type = "brainstorming" if folder_name in SPECIAL_FOLDERS else "ufficiale"
        
        for file in files:
            filepath = os.path.join(root, file)
            text = extract_text_from_file(filepath)
            if text and len(text.strip()) > 10:
                doc_id = hash_text(text)
                categories = categorize_text(text[:500])
                inferred_category = infer_category_from_path(filepath)
                if inferred_category not in categories:
                    categories.append(inferred_category)
                
                # Remove "varie" if another category exists
                if "varie" in categories and len(categories) > 1:
                    categories.remove("varie")
                
                index[doc_id] = {
                    "file": file,
                    "categories": categories,
                    "summary": text[:300] + "...",  # Truncated for readability
                    "path": filepath,
                    "folder_type": folder_type,
                    "file_type": "official" if file == "entry.md" else "brainstorming" if file == "notes.md" else "varie"
                }
    
    with open(index_file, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=4, ensure_ascii=False)
    
    print(f"✅ Indice creato con {len(index)} documenti in {index_file}.")
    return index, index_file


def get_available_categories(index_file):
    if not os.path.exists(index_file):
        return list(CATEGORY_KEYWORDS.keys())
    
    with open(index_file, "r", encoding="utf-8") as f:
        index = json.load(f)
    
    dynamic_categories = set()
    for doc in index.values():
        dynamic_categories.update(doc["categories"])
    
    return list(set(CATEGORY_KEYWORDS.keys()) | dynamic_categories)


# Creazione API Flask
app = Flask(__name__)
input_folder, output_folder = parse_arguments()
CATEGORY_KEYWORDS = load_custom_keywords(output_folder)

@app.route("/categories", methods=["GET"])
def categories_endpoint():
    index_file = os.path.join(output_folder, "indexdiva.json")
    return jsonify({"available_categories": get_available_categories(index_file)})

if __name__ == "__main__":
    index, index_file = build_index(input_folder, output_folder)
    print(f"📌 Categorie disponibili: {get_available_categories(index_file)}")
    PORT = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=PORT)
