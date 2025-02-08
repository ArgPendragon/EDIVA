import os
import sys
import json
import logging
import httpx
from openai import OpenAI
from dotenv import load_dotenv

# Enable logging if you need to see more details (optional)
logging.basicConfig(level=logging.INFO)

# Load environment variables from .env
load_dotenv()

# Retrieve and clean up the API key
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    print("Error: OPENROUTER_API_KEY environment variable is not set!")
    sys.exit(1)
OPENROUTER_API_KEY = OPENROUTER_API_KEY.strip()

# Create a custom httpx.Client with all the required headers
custom_http_client = httpx.Client(
    headers={
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "https://example.com",  # Optional: your site URL for leaderboard rankings
        "X-Title": "My Site",                   # Optional: your site name for leaderboard rankings
        "Content-Type": "application/json"      # Ensure JSON payloads are handled correctly
    }
)

# Instantiate the OpenAI client with the custom HTTP client and correct base_url
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,  # (Used for logging/fallback)
    http_client=custom_http_client,
)

# Define input and output directories
INPUT_FOLDER = "D:/EDIVA/cardonaproject/raw/1God/test"  # Folder with JSON files (e.g. chunk001.json, chunk002.json, etc.)
OUTPUT_FOLDER = os.path.join(INPUT_FOLDER, "processed_chunks")  # Where processed files will be saved

# Verify that the input folder exists
if not os.path.exists(INPUT_FOLDER):
    print(f"Error: the input folder '{INPUT_FOLDER}' does not exist!")
    sys.exit(1)

# Create the output folder (and subfolders) if needed
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Full prompt to be sent to GPT
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
    "[\n"
    "    {\n"
    '        "page_type": "string",\n'
    '        "image_present": true | false,\n'
    '        "page_number": integer | null,\n'
    '        "content": "string",\n'
    '        "bibliography": ["string"],\n'
    '        "captions": ["string"]\n'
    "    }\n"
    "]\n"
    "Keep the original structure intact.\n"
    "Include all sections while ensuring proper formatting.\n\n"
    "✅ Sample Cleaned Output\n"
    '[\n'
    '    {\n'
    '        "page_type": "main",\n'
    '        "image_present": true,\n'
    '        "page_number": 9,\n'
    '        "content": "The sacred precinct was constructed in honor of the god. The rites of Dionysus closely resembled those of the Egyptian god Osiris. Herodotus believed the Greek rites were borrowed and modified from the Egyptians.",\n'
    '        "bibliography": [\n'
    '            "1. W. Oates & E. O\'Neil, The Complete Greek Drama (1938), p. xxiii.",\n'
    '            "2. J. G. Frazer, The Golden Bough (London, 1974, abridged edition), p. 507.",\n'
    '            "3. G. J. Griffiths, \'Interpretatio Graeca,\' in W. Helck & E. Otto, Lexikon der Ägyptologie, Vol. II (1980), col. 167."\n'
    '        ],\n'
    '        "captions": []\n'
    '    }\n'
    ']\n\n'
    "🔴 Final Instruction to GPT\n"
    'Return only a valid JSON object { [...] } without any additional text or explanation. The JSON must be parseable by a standard JSON parser.'
)

def process_file(file_path, relative_path):
    """
    Process a file:
      - Skip processing if the output file already exists.
      - Otherwise, load the JSON, send it to GPT, and write the response.
    """
    output_file = os.path.join(OUTPUT_FOLDER, relative_path)
    if os.path.exists(output_file):
        print(f"Skipping {file_path} (output already exists)")
        return

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return

    user_message = "Process the following JSON data:\n" + json.dumps(data)

    try:
        response = client.chat.completions.create(
            model="openai/gpt-4o",  # As per OpenRouter documentation
            messages=[
                {"role": "system", "content": FULL_PROMPT},
                {"role": "user", "content": user_message}
            ],
            temperature=0
        )
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return

    try:
        output_text = response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error retrieving response for {file_path}: {e}")
        return

    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(output_text)
        print(f"Processed file saved to: {output_file}")
    except Exception as e:
        print(f"Error writing output file {output_file}: {e}")

def process_directory(input_dir):
    """
    Recursively scan the input directory (excluding the output folder)
    and process all JSON files.
    """
    for root, dirs, files in os.walk(input_dir):
        # Exclude the output folder to prevent infinite loops
        dirs[:] = [d for d in dirs if os.path.abspath(os.path.join(root, d)) != os.path.abspath(OUTPUT_FOLDER)]
        rel_dir = os.path.relpath(root, input_dir)
        if rel_dir == ".":
            rel_dir = ""
        for file in sorted(files):
            if file.endswith(".json"):
                full_path = os.path.join(root, file)
                relative_file_path = os.path.join(rel_dir, file) if rel_dir else file
                process_file(full_path, relative_file_path)

if __name__ == "__main__":
    process_directory(INPUT_FOLDER)
