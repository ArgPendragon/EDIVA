import os
import json
import requests
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Retrieve the OpenRouter API key from your environment.
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    print("Error: OPENROUTER_API_KEY environment variable is not set!")
    exit(1)

# Set up the URL and headers exactly as per OpenRouter's quickstart docs.
url = "https://openrouter.ai/api/v1/chat/completions"
headers = {
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "HTTP-Referer": "https://example.com",  # Optional: Replace with your site URL for leaderboard rankings.
    "X-Title": "My Site",                   # Optional: Replace with your site name for leaderboard rankings.
    "Content-Type": "application/json"      # Ensure the payload is sent as JSON.
}

# Define a simple payload as per the quickstart.
data = {
    "model": "openai/gpt-4o",  # Use the documented model name.
    "messages": [
        {"role": "user", "content": "Hello, OpenRouter test!"}
    ],
    "temperature": 0
}

print("Sending test request to OpenRouter API via requests...")
response = requests.post(url, headers=headers, json=data)

print("Status Code:", response.status_code)
print("Response Body:")
print(response.text)
