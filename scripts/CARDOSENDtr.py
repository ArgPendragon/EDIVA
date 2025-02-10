import os
import sys
import json
import logging
import httpx
from openai import OpenAI
from dotenv import load_dotenv
from rich.logging import RichHandler

# ------------------------------------------------------------------------------
# Setup Rich logging for a more colorful and informative output
# ------------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler()]
)
logger = logging.getLogger("rich")

# ------------------------------------------------------------------------------
# Define helper function to clean the GPT response
# ------------------------------------------------------------------------------
def clean_gpt_response(text: str) -> str:
    """
    Extracts the JSON portion from the GPT response by:
      - Finding the first occurrence of a JSON opening bracket ('[' or '{').
      - Scanning the text and balancing the brackets until the matching closing bracket is found.
      - Returning only the valid JSON substring.
      
    This effectively removes any extraneous text before the JSON starts or after it ends.
    """
    start_index = None
    start_char = None
    for i, ch in enumerate(text):
        if ch in ('[', '{'):
            start_index = i
            start_char = ch
            break

    if start_index is None:
        return text.strip()

    closing_char = ']' if start_char == '[' else '}'
    stack = []
    for i in range(start_index, len(text)):
        ch = text[i]
        if ch == start_char:
            stack.append(ch)
        elif ch == closing_char:
            if stack:
                stack.pop()
            if not stack:
                end_index = i + 1
                return text[start_index:end_index].strip()
    
    return text[start_index:].strip()

# ------------------------------------------------------------------------------
# Load environment variables from .env
# ------------------------------------------------------------------------------
load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    logger.critical("[bold red]Error:[/bold red] OPENROUTER_API_KEY environment variable is not set!")
    sys.exit(1)
OPENROUTER_API_KEY = OPENROUTER_API_KEY.strip()

# ------------------------------------------------------------------------------
# Create a custom httpx.Client with all the required headers
# ------------------------------------------------------------------------------
custom_http_client = httpx.Client(
    headers={
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "https://example.com",  # Optional: your site URL for leaderboard rankings
        "X-Title": "My Site",                   # Optional: your site name for leaderboard rankings
        "Content-Type": "application/json"
    }
)

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
    http_client=custom_http_client,
)

# ------------------------------------------------------------------------------
# Define input and output directories
# ------------------------------------------------------------------------------
INPUT_FOLDER = "D:/EDIVA/cardonaproject/processed/1God/slim"   # Folder with JSON files
OUTPUT_FOLDER = "D:/EDIVA/cardonaproject/tradotto/1God"  # Where processed files will be saved



if not os.path.exists(INPUT_FOLDER):
    logger.critical(f"[bold red]Error:[/bold red] The input folder '{INPUT_FOLDER}' does not exist!")
    sys.exit(1)

os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# ------------------------------------------------------------------------------
# Load the full prompt from an external file
# ------------------------------------------------------------------------------
PROMPT_FILE = "traslo.txt"  # Ensure this file exists and contains your prompt
if not os.path.exists(PROMPT_FILE):
    logger.critical(f"[bold red]Error:[/bold red] The prompt file '{PROMPT_FILE}' does not exist!")
    sys.exit(1)

try:
    with open(PROMPT_FILE, "r", encoding="utf-8") as pf:
        FULL_PROMPT = pf.read()
except Exception as e:
    logger.critical(f"[bold red]Error reading prompt file:[/bold red] {e}")
    sys.exit(1)

# ------------------------------------------------------------------------------
# File processing functions
# ------------------------------------------------------------------------------
def process_file(file_path, relative_path):
    """
    Process a file:
      - Skip processing if the output file already exists.
      - Otherwise, load the JSON and check whether it contains a "pages" key.
        If so, extract the list of pages before sending it to GPT.
      - Send the pages list to GPT, clean the response, and verify that
        the returned JSON is a list with the same number of pages and matching page numbers.
      - If verification fails, retry (up to a maximum number of attempts).
      - If verification never passes, save the last attempted output with a '.json.deb'
        extension for later comparison.
      
    Returns a status string: "processed", "skipped", or "error".
    """
    output_file = os.path.join(OUTPUT_FOLDER, relative_path)
    if os.path.exists(output_file):
        logger.info(f"[yellow]Skipping[/yellow] {file_path} (output already exists)")
        return "skipped"

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f"[red]Error reading[/red] {file_path}: {e}")
        return "error"

    # Option 2: If the input JSON is an object with a "pages" key,
    # extract the list of pages.
    if isinstance(data, dict) and "pages" in data:
        data = data["pages"]

    if not isinstance(data, list):
        logger.error(f"[red]Input JSON in {file_path} is not a list of pages.[/red]")
        return "error"

    max_attempts = 3
    attempt = 0
    verified_output_text = None
    last_attempt_output_text = None

    # Extract expected page numbers from the input
    input_page_numbers = {page.get("page_number") for page in data if isinstance(page, dict) and "page_number" in page}

    while attempt < max_attempts:
        attempt += 1
        logger.info(f"[blue]Attempt {attempt} for {file_path}[/blue]")

        user_message = "Process the following JSON data:\n" + json.dumps(data)
        try:
            response = client.chat.completions.create(
                model="openai/gpt-4o-mini",  # As per OpenRouter documentation
                messages=[
                    {"role": "system", "content": FULL_PROMPT},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.3,
                max_tokens=8000
            )
        except Exception as e:
            logger.error(f"[red]Error processing[/red] {file_path}: {e}")
            return "error"

        try:
            output_text = response.choices[0].message.content.strip()
            output_text = clean_gpt_response(output_text)
            last_attempt_output_text = output_text  # Save the latest output for fallback.
        except Exception as e:
            logger.error(f"[red]Error retrieving response for[/red] {file_path}: {e}")
            return "error"

        try:
            output_json = json.loads(output_text)
        except json.JSONDecodeError as e:
            logger.error(f"[red]Failed to parse output JSON on attempt {attempt} for {file_path}: {e}[/red]")
            continue  # Retry if JSON parsing fails

        # Check if output is a list
        if not isinstance(output_json, list):
            logger.error(f"[red]Output JSON is not a list on attempt {attempt} for {file_path}.[/red]")
            continue  # Retry

        # Check for truncated response (missing pages based on list length)
        if len(output_json) != len(data):
            logger.error(f"[red]Page count mismatch on attempt {attempt} for {file_path} "
                         f"(expected {len(data)} pages, got {len(output_json)}).[/red]")
            continue  # Retry

        # Extract page numbers from the output
        output_page_numbers = {page.get("page_number") for page in output_json if isinstance(page, dict) and "page_number" in page}
        if input_page_numbers != output_page_numbers:
            logger.error(f"[red]Missing or mismatched page numbers on attempt {attempt} for {file_path}.[/red]")
            continue  # Retry

        # If both checks pass, verification is successful.
        verified_output_text = output_text
        logger.info(f"[green]Verification passed on attempt {attempt} for {file_path}.[/green]")
        break

    if verified_output_text is None:
        fallback_file = output_file + ".deb"
        try:
            os.makedirs(os.path.dirname(fallback_file), exist_ok=True)
            with open(fallback_file, "w", encoding="utf-8") as f:
                f.write(last_attempt_output_text if last_attempt_output_text is not None else "")
            logger.error(f"[red]Max attempts reached. Verification failed for {file_path}. "
                         f"Last output saved to: {fallback_file}[/red]")
        except Exception as e:
            logger.error(f"[red]Error writing fallback output file {fallback_file}: {e}")
        return "error"

    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(verified_output_text)
        logger.info(f"[green]Processed[/green] file saved to: {output_file}")
        return "processed"
    except Exception as e:
        logger.error(f"[red]Error writing output file {output_file}: {e}")
        return "error"

def process_directory(input_dir):
    """
    Recursively scan the input directory (excluding the output folder)
    and process all JSON files.
    Returns counters for processed, skipped, and error files.
    """
    processed_count = 0
    skipped_count = 0
    error_count = 0

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
                status = process_file(full_path, relative_file_path)
                if status == "processed":
                    processed_count += 1
                elif status == "skipped":
                    skipped_count += 1
                else:
                    error_count += 1

    return processed_count, skipped_count, error_count

# ------------------------------------------------------------------------------
# Main execution
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    logger.info("[bold blue]Starting processing...[/bold blue]")
    processed, skipped, errors = process_directory(INPUT_FOLDER)

    logger.info("")
    logger.info("[bold blue]Processing complete![/bold blue]")
    logger.info(f"Files processed: [green]{processed}[/green]")
    logger.info(f"Files skipped: [yellow]{skipped}[/yellow]")
    logger.info(f"Errors encountered: [red]{errors}[/red]")
    logger.info("")

    if processed > 0:
        celebration_message = (
            "[bold green]Congratulations! All files processed successfully! 🎉🎊[/bold green]\n"
            "        __   __            _    _ _       _ \n"
            "        \\ \\ / /           | |  | (_)     | |\n"
            "         \\ V /___  _   _  | |  | |_ _ __ | |\n"
            "          \\ // _ \\| | | | | |/\\| | | '_ \\| |\n"
            "          | | (_) | |_| | \\  /\\  / | | | |_|\n"
            "          \\_/\\___/ \\__,_|  \\/  \\/|_|_| |_(_)\n"
        )
        logger.info(celebration_message)
    else:
        logger.warning("[yellow]No files were processed.[/yellow]")
