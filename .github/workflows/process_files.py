import os
import json
from openai import OpenAI

# Configurazione per OpenRouter
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Inizializza il client con il nuovo pattern (v1.0.0)
client = OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url=OPENROUTER_BASE_URL,  # Imposta la base API per OpenRouter
    default_headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"}
)

# Cartelle per i file di input e output
INPUT_FOLDER = "./cardonaproject/raw/1God/actionstest"
OUTPUT_FOLDER = "./cardonaproject/raw/1God/actionstest/processed_chunks"

# Crea la cartella di output se non esiste
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Il prompt completo da usare; se lo desideri, puoi copiarlo nell'OpenAI Canvas Editor
FULL_PROMPT = (
    "🎯 Objective\n"
    "You are an AI assistant that cleans and refines OCR-extracted JSON text, ensuring accuracy while maintaining its original sentence and wording structure.\n\n"
    "📂 Input Format\n"
    "The input consists of a list of sections, each containing:\n"
    "page_type: Identifies the type of page, such as \"main\" or \"index\"\n"
    "image_present: true if an image is on the page, which may cause text misalignment.\n"
    "page_number: The page number, if available.\n"
    "content: The main text extracted from the page.\n"
    "bibliography: A list of references found at the bottom of the page.\n"
    "captions: Any image captions detected (unreliable attribution).\n\n"
    "🛠 How to Process the Data\n"
    "1️⃣ Text Refinement\n"
    "Preserve the original text while fixing OCR errors. Do not summarize, remove, or alter meaning. Your task is only to correct spelling, restore broken sentences, and fix formatting issues while keeping the structure, order, and details identical to the reconstructed input. Be aware of possible errors in field attribution (content, bibliography and captions), expect captions on image_present pages.\n"
    "If a sentence seems unclear or fragmented, attempt to restore it rather than omitting or summarizing it. Improve paragraph structure for better readability.\n"
    "Ensure historical names, locations, and terminology are correct.\n\n"
    "2️⃣ Handling Pages with Images (image_present)\n"
    "📌 When image_present is true:\n"
    "Be mindful of misplaced text, bibliography errors, or missing/altered words caused by images.\n"
    "Verify that captions are correctly identified and not merged into the main content.\n\n"
    "📌 When image_present is false:\n"
    "The text is generally more reliable, but citation placement and bibliography errors may still need attention.\n\n"
    "3️⃣ Organizing Citations & Bibliography\n"
    "Move misplaced citations from the content into the bibliography section.\n"
    "Deduplicate and reorder bibliography references sequentially (1, 2, 3…).\n"
    "Ensure that all in-text citations are listed in the bibliography.\n"
    "Bibliography numbering resets at the start of a new chapter but may continue from previous pages within the same section (it should be sequential).\n\n"
    "📤 Expected JSON Output Format\n"
    "The response should follow this structure:\n"
    "{\n"
    '    "cleaned_data": [\n'
    "        {\n"
    '            "page_type": "string",\n'
    '            "image_present": true | false,\n'
    '            "page_number": integer | null,\n'
    '            "content": "string",\n'
    '            "bibliography": ["string"],\n'
    '            "captions": ["string"]\n'
    '            "headers": ["string"]\n'
    "        }\n"
    "    ]\n"
    "}\n"
    "Keep the original structure intact.\n"
    "Include all sections while ensuring proper formatting.\n\n"
    "✅ Sample Cleaned Output\n"
    "{\n"
    '    "cleaned_data": [\n'
    "        {\n"
    '            "page_type": "main",\n'
    '            "image_present": true,\n'
    '            "page_number": 9,\n'
    '            "content": "The sacred precinct was constructed in honor of the god. The rites of Dionysus closely resembled those of the Egyptian god Osiris. Herodotus believed the Greek rites were borrowed and modified from the Egyptians.",\n'
    '            "bibliography": [\n'
    '                "22. W. Oates & E. O’Neil, The Complete Greek Drama (1938), p. xxiii.",\n'
    '                "23. J. G. Frazer, The Golden Bough (London, 1974, abridged edition), p. 507.",\n'
    '                "24. G. J. Griffiths, \'Interpretatio Graeca,\' in W. Helck & E. Otto, Lexikon der Ägyptologie, Vol. II (1980), col. 167."\n'
    "            ],\n"
    '            "captions": []\n'
    "        }\n"
    "    ]\n"
    "}\n\n"
    "🔴 Final Instruction to GPT\n"
    'Return a valid JSON object { "cleaned_data": [...] } without markdown formatting, triple backticks, or extra formatting (such as "\\n").'
)

def process_file(filepath):
    # Legge il contenuto del file JSON
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Errore nel decodificare il file {filepath}: {e}")
        return

    user_message = "Process the following JSON data:\n" + json.dumps(data)

    try:
        # Utilizza il nuovo client per effettuare la richiesta
        response = client.chat.completions.create(
            model="openai/gpt-4o-mini",  # Scegli il modello che preferisci
            messages=[
                {"role": "system", "content": FULL_PROMPT},
                {"role": "user", "content": user_message}
            ],
            temperature=0
        )
    except Exception as e:
        print(f"Errore nella chiamata a OpenRouter per il file {filepath}: {e}")
        return

    # Accedi al contenuto della risposta utilizzando la notazione a punto (pydantic)
    output_text = response.choices[0].message.content.strip()

    # Salva l'output in un nuovo file nella cartella di output
    filename = os.path.basename(filepath)
    output_filepath = os.path.join(OUTPUT_FOLDER, filename)
    with open(output_filepath, "w", encoding="utf-8") as f:
        f.write(output_text)
    print(f"File processato e salvato: {output_filepath}")

def main():
    try:
        all_files = os.listdir(INPUT_FOLDER)
    except Exception as e:
        print(f"Errore nell'aprire la cartella di input ({INPUT_FOLDER}): {e}")
        return

    print(f"Contenuto della cartella di input ({os.path.abspath(INPUT_FOLDER)}): {all_files}")

    files = [os.path.join(INPUT_FOLDER, f) for f in all_files if f.endswith(".json")]
    if not files:
        print("Nessun file JSON trovato nella cartella di input.")
        return
    for file in files:
        process_file(file)

if __name__ == "__main__":
    main()
