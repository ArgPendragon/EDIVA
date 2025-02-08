import os
import openai
import httpx
from dotenv import load_dotenv
from autogen import AssistantAgent, UserProxyAgent

#########################################
# 1) Load .env variables safely
#########################################
load_dotenv()

openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
openrouter_api_base = os.getenv("OPENROUTER_API_BASE", "https://openrouter.ai/api/v1")
openrouter_model = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o")

if not openrouter_api_key or "sk-or-v1" not in openrouter_api_key:
    raise ValueError("❌ ERROR: Missing or invalid OpenRouter API key. Check your .env file!")

#########################################
# 2) Configure OpenAI for OpenRouter (Fix: No `.headers`)
#########################################
openai.api_key = openrouter_api_key
openai.api_base = openrouter_api_base

# ✅ Print debugging info
print(f"🔍 API Key Loaded: {openrouter_api_key[:10]}... (masked)")
print(f"🔍 OpenRouter Base URL: {openrouter_api_base}")

#########################################
# 3) Setup llm_config for AutoGen (FIXED)
#########################################
llm_config = {
    "api_key": openrouter_api_key,
    "model": openrouter_model,
    "config_list": [
        {
            "api_key": openrouter_api_key,
            "model": openrouter_model,
            "base_url": openrouter_api_base,  # ✅ Corrected
        }
    ]
}

#########################################
# 4) Manually Define HTTPX Session with Headers
#########################################
session = httpx.Client(
    headers={
        "Authorization": f"Bearer {openrouter_api_key}",
        "Content-Type": "application/json"
    }
)

#########################################
# 5) Debugging OpenAI Request
#########################################
def debug_openai_request():
    """Prints base URL and API key to verify connection."""
    print("\n🚀 DEBUGGING AutoGen Request to OpenRouter...\n")
    print(f"🔹 Base URL: {openrouter_api_base}")
    print(f"🔹 API Key (Masked): {openrouter_api_key[:10]}... (masked)")

# Run debug before starting AutoGen
debug_openai_request()

#########################################
# 6) Create Agents
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
# 7) Initiate Conversation (New API Format)
#########################################
try:
    user_proxy.initiate_chat(
        assistant,
        message="Hello, are we connected to OpenRouter?"
    )
except Exception as e:
    print(f"❌ Error during chat initiation: {e}")
