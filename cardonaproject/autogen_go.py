# your_autogen_script.py

import os
import openai
from dotenv import load_dotenv
from autogen import AssistantAgent, UserProxyAgent

#########################################
# 1) Load .env variables safely
#########################################
load_dotenv()

openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
openrouter_api_base = os.getenv("OPENROUTER_API_BASE", "https://openrouter.ai/api/v1")
openrouter_model = os.getenv("OPENROUTER_MODEL", "openai/gpt-3.5-turbo")

if not openrouter_api_key or "sk-or-v1" not in openrouter_api_key:
    raise ValueError("❌ ERROR: Missing or invalid OpenRouter API key. Check your .env file!")

#########################################
# 2) Configure OpenAI for OpenRouter
#########################################
openai.api_key = openrouter_api_key
openai.api_base = openrouter_api_base

# Fix for OpenAI 1.x+ (No more `default_headers.update()`)
client = openai.OpenAI(api_key=openai.api_key, base_url=openai.api_base)

# ✅ Print debugging info
print(f"🔍 API Key Sent: {openrouter_api_key[:10]}... (masked)")
print(f"🔍 OpenRouter Base URL: {openrouter_api_base}")

#########################################
# 3) Setup llm_config for AutoGen (FIXED HEADERS)
#########################################
llm_config = {
    "api_key": openrouter_api_key,
    "model": openrouter_model,
    "config_list": [
        {
            "api_key": openrouter_api_key,
            "model": openrouter_model,
            "base_url": openrouter_api_base
        }
    ]
}

# ✅ Force OpenRouter Headers Globally
import httpx
openai_client = openai.OpenAI(api_key=openrouter_api_key, base_url=openrouter_api_base)

openai_client.http_client = httpx.Client(
    headers={
        "Authorization": f"Bearer {openrouter_api_key}",
        "Content-Type": "application/json"
    }
)

#########################################
# 4) Create Agents
#########################################
assistant = AssistantAgent(
    name="assistant",
    llm_config=llm_config,
    system_message="You are a helpful assistant using OpenRouter."
)

user_proxy = UserProxyAgent(
    name="user_proxy",
    human_input_mode="ALWAYS",
    max_consecutive_auto_reply=1,
    code_execution_config=False,
    system_message="You are the user, controlling the conversation."
)

#########################################
# 5) Initiate Conversation (New API Format)
#########################################
try:
    user_proxy.initiate_chat(
        assistant,
        message="Hello, are we connected to OpenRouter?"
    )
except Exception as e:
    print(f"❌ Error during chat initiation: {e}")
