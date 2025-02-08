#!/usr/bin/env python3
import os
import openai
import httpx
import logging
from dotenv import load_dotenv
from autogen import AssistantAgent, UserProxyAgent

def setup_logging():
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

def debug_openai_request(api_base, api_key):
    logging.debug("🚀 DEBUGGING AutoGen Request to OpenRouter...")
    logging.debug(f"🔹 Base URL: {api_base}")
    logging.debug(f"🔹 API Key (masked): {api_key[:10]}... (masked)")

def main():
    load_dotenv()
    openrouter_api_key  = os.getenv("OPENROUTER_API_KEY")
    openrouter_api_base = os.getenv("OPENROUTER_API_BASE", "https://openrouter.ai/api/v1")
    openrouter_model    = os.getenv("OPENROUTER_MODEL", "gpt-4o-mini")  # forziamo gpt-4o-mini

    if not openrouter_api_key or "sk-or-v1" not in openrouter_api_key:
        raise ValueError("❌ ERROR: Missing or invalid OpenRouter API key in .env!")
    
    # Configuro OpenAI
    openai.api_key  = openrouter_api_key
    openai.api_base = openrouter_api_base

    logging.debug("API Key e Base URL caricati correttamente:")
    logging.debug(f"API Key: {openrouter_api_key[:10]}... (masked)")
    logging.debug(f"Base URL: {openrouter_api_base}")

    # MONKEY PATCH: patch della classe base client per assicurare che ogni istanza abbia 'headers'
    try:
        from openai import _base_client as base_client
        original_init = base_client.Client.__init__
        def new_init(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            if not hasattr(self, "headers"):
                self.headers = {
                    "Authorization": f"Bearer {openrouter_api_key}",
                    "Content-Type": "application/json"
                }
                logging.debug("Headers aggiunti all'istanza di Client")
        base_client.Client.__init__ = new_init
    except Exception as e:
        logging.exception("Errore durante il patching di base_client.Client: " + str(e))
    
    # Configurazione LLM per AutoGen (uguale a quella usata in test singolo)
    llm_config = {
        "api_key": openrouter_api_key,
        "model": openrouter_model,
        "config_list": [
            {
                "api_key": openrouter_api_key,
                "model": openrouter_model,
                "base_url": openrouter_api_base,
            }
        ]
    }
    
    # (Opzionale) creazione di una sessione httpx con gli header
    session = httpx.Client(
        headers={
            "Authorization": f"Bearer {openrouter_api_key}",
            "Content-Type": "application/json"
        }
    )
    
    debug_openai_request(openrouter_api_base, openrouter_api_key)
    
    # Creazione degli agenti
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
    
    # Avvio della conversazione
    try:
        logging.debug("Inizializzo la chat con l'assistente...")
        user_proxy.initiate_chat(
            assistant,
            message="Hello, are we connected to OpenRouter?"
        )
    except Exception as e:
        logging.exception(f"❌ Error during chat initiation: {e}")

if __name__ == "__main__":
    setup_logging()
    main()
