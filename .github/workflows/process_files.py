import os
import json
import openai

# Cartelle per i file di input e output
INPUT_FOLDER = "cardonaproject/raw/1God/actionstest"
OUTPUT_FOLDER = "cardonaproject/raw/1God/actionstest/processed_chunks"

# Crea la cartella di output se non esiste
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Il prompt completo da utilizzare per processare i file JSON.
# Puoi copiare questo intero testo e incollarlo nell'OpenAI Canvas Editor se desideri testarlo o modificarlo interattivamente.
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
    "captions: Any image captions detected (may contain duplicated or misplaced text).\n\n"
    "🛠 How to Process the Data\n"
    "1️⃣ Text Refinement\n"
    "Preserve the original text while fixing OCR errors. Do not summarize, remove, or alter meaning. Your task is only to correct spelling, restore broken sentences, and fix formatting issues. Be aware of possible errors in field attribution (content, bibliography and captions), expect captions texton image_present pages.\n"
    "If a sentence seems unclear or fragmented, attempt to restore it rather than omitting or summarizing it. Improve paragraph structure for better readability.\n"
    "Since it's important scientific material, ensure historical names, locations, and terminology are correct.\n\n"
    "2️⃣ Handling Pages with Images (image_present)\n"
    "📌 When image_present is true:\n"
    "Be mindful of misplaced text, bibliography errors, or missing/altered words caused by images.\n"
    "Verify that captions are correctly identified and not merged into the main content (correct if needed).\n\n"
    "📌 When image_present is false:\n"
    "The text is generally more reliable, but bibliography errors may still need attention.\n\n"
    "3️⃣ Organizing Citations & Bibliography\n"
    "Deduplicate bibliography references and be aware of ocr mistakes in identifying small numbers. Try to reproduce the original sequence (...,21, 22, 23…). Hint: when you find a chapter header in main text, bibliography numbering will reset.\n"
    "📤 Expected JSON Output Format\n"
    "The response should follow this structure:\n"
    "{\n"
    '    "page_type": "string",\n'
    '    "image_present": true | false,\n'
    '    "page_number": integer | null,\n'
    '    "content": "string",\n'
    '    "bibliography": ["string"],\n'
    '    "captions": ["string"]\n'
    '    "headers": ["string"]\n'
    "}\n"
    "Keep the original structure intact.\n"
    "Include all sections while ensuring proper formatting.\n\n"

    "✅ Sample Cleaned Output\n"
    "{\n"
    '    "page_type": "main",\n'
    '    "image_present": true,\n'
    '    "page_number": 9,\n'

    '    "content": "The sacred precinct was constructed in honor of the god. The rites of Dionysus closely resembled those of the Egyptian god Osiris. Herodotus believed the Greek rites were borrowed and modified from the Egyptians.",\n'
    '    "bibliography": [\n'
    '                "1. W. Oates & E. O’Neil, The Complete Greek Drama (1938), p. xxiii.",\n'
    '                "2. J. G. Frazer, The Golden Bough (London, 1974, abridged edition), p. 507.",\n'
    '                "3. G. J. Griffiths, \'Interpretatio Graeca,\' in W. Helck & E. Otto, Lexikon der Ägyptologie, Vol. II (1980), col. 167."\n'
    '    ],\n'
    '    "captions": []\n'
    '    "headers": []\n'
    "}\n\n"
    "🔴 Final Instruction to GPT\n"

    'Return a valid JSON object { "cleaned_data": [...] } without markdown formatting, triple backticks, or extra formatting (such as "\\n").'

)

def process_file(filepath):
    # Legge il contenuto del file JSON
    with open(filepath, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"Errore nel decodificare il file {filepath}: {e}")
            return

    # Prepara il messaggio utente includendo i dati JSON
    user_message = "Process the following JSON data:\n" + json.dumps(data)

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",  # Puoi scegliere un altro modello se necessario
            messages=[
                {"role": "system", "content": FULL_PROMPT},
                {"role": "user", "content": user_message}
            ],
            temperature=0  # Bassa temperatura per maggiore determinismo
        )
    except Exception as e:
        print(f"Errore nella chiamata a OpenAI per il file {filepath}: {e}")
        return

    # Estrae la risposta testuale
    output_text = response.choices[0].message['content'].strip()

    # Salva l'output in un nuovo file nella cartella di output
    filename = os.path.basename(filepath)
    output_filepath = os.path.join(OUTPUT_FOLDER, filename)
    with open(output_filepath, 'w', encoding='utf-8') as f:
        f.write(output_text)
    print(f"File processato e salvato: {output_filepath}")

def main():
    # Ottiene la lista dei file JSON nella cartella di input
    files = [os.path.join(INPUT_FOLDER, f) for f in os.listdir(INPUT_FOLDER) if f.endswith('.json')]
    if not files:
        print("Nessun file JSON trovato nella cartella di input.")
        return
    for file in files:
        process_file(file)

if __name__ == "__main__":
    main()
