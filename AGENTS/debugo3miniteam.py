#!/usr/bin/env python3
import os
import logging
from dotenv import load_dotenv
import openai
import httpx

# Importa il team e la classe agente dalla versione team
try:
    from autogen_agentchat.teams import SelectorGroupChat
except ImportError as e:
    logging.error("Impossibile importare SelectorGroupChat: " + str(e))
    raise

try:
    from autogen_agentchat.agents import AssistantAgent
except ImportError as e:
    logging.error("Impossibile importare AssistantAgent: " + str(e))
    raise

# (Opzionale) Se esiste il client del modello, importalo
try:
    from autogen_ext.models.openai import OpenAIChatCompletionClient
except ImportError as e:
    logging.warning("Impossibile importare OpenAIChatCompletionClient: " + str(e))
    OpenAIChatCompletionClient = None

def setup_logging():
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

# Configurazione del team (basata sul JSON fornito)
TEAM_CONFIG = {
  "provider": "autogen_agentchat.teams.SelectorGroupChat",
  "component_type": "team",
  "version": 1,
  "component_version": 1,
  "description": "A 2-agent team that converses for 5 rounds and then returns a final answer, with both {roles} and {participants} in the selector prompt.",
  "label": "2-Agent Selector Team",
  "config": {
    "initial_messages": [
      {"role": "user", "content": "What is the meaning of life?"}
    ],
    "participants": [
      {
        "provider": "autogen_agentchat.agents.AssistantAgent",
        "component_type": "agent",
        "version": 1,
        "component_version": 1,
        "description": "Agent A, the philosopher.",
        "label": "AgentA",
        "config": {
          "name": "AgentA",
          "description": "Agent A offers philosophical insights.",
          "system_message": "You are Agent A. Provide a philosophical view on the conversation.",
          "model_client": {
            "provider": "autogen_ext.models.openai.OpenAIChatCompletionClient",
            "component_type": "model",
            "version": 1,
            "component_version": 1,
            "label": "OpenAIChatCompletionClient",
            "config": {
              "model": "gpt-4o-mini",
              "api_key": "${OPENAI_API_KEY}",
              "organization": "openrouter",
              "base_url": "https://openrouter.ai/api/v1",
              "timeout": 90,
              "temperature": 0.2,
              "max_tokens": 750,
              "top_p": 0.9,
              "frequency_penalty": 0.1,
              "presence_penalty": 0.2,
              "stop": ["TERMINATE"],
              "model_info": {
                "name": "gpt-4o-mini",
                "description": "gpt-4o-mini via OpenRouter, supporting function calling.",
                "vision": False,
                "function_calling": True,
                "json_output": True,
                "family": "gpt-35"
              }
            }
          },
          "tools": [],
          "handoffs": [],
          "model_context": {
            "provider": "autogen_core.model_context.UnboundedChatCompletionContext",
            "component_type": "chat_completion_context",
            "version": 1,
            "component_version": 1,
            "description": "An unbounded chat context that keeps the full conversation history.",
            "label": "UnboundedChatCompletionContext",
            "config": {}
          },
          "model_client_stream": False,
          "reflect_on_tool_use": False,
          "tool_call_summary_format": "{result}"
        }
      },
      {
        "provider": "autogen_agentchat.agents.AssistantAgent",
        "component_type": "agent",
        "version": 1,
        "component_version": 1,
        "description": "Agent B, the analyst.",
        "label": "AgentB",
        "config": {
          "name": "AgentB",
          "description": "Agent B offers analytical insights.",
          "system_message": "You are Agent B. Provide an analytical and thoughtful response.",
          "model_client": {
            "provider": "autogen_ext.models.openai.OpenAIChatCompletionClient",
            "component_type": "model",
            "version": 1,
            "component_version": 1,
            "label": "OpenAIChatCompletionClient",
            "config": {
              "model": "gpt-4o-mini",
              "api_key": "${OPENAI_API_KEY}",
              "organization": "openrouter",
              "base_url": "https://openrouter.ai/api/v1",
              "timeout": 90,
              "temperature": 0.2,
              "max_tokens": 750,
              "top_p": 0.9,
              "frequency_penalty": 0.1,
              "presence_penalty": 0.2,
              "stop": ["TERMINATE"],
              "model_info": {
                "name": "gpt-4o-mini",
                "description": "gpt-4o-mini via OpenRouter, supporting function calling.",
                "vision": False,
                "function_calling": True,
                "json_output": True,
                "family": "gpt-35"
              }
            }
          },
          "tools": [],
          "handoffs": [],
          "model_context": {
            "provider": "autogen_core.model_context.UnboundedChatCompletionContext",
            "component_type": "chat_completion_context",
            "version": 1,
            "component_version": 1,
            "description": "An unbounded chat context that keeps the full conversation history.",
            "label": "UnboundedChatCompletionContext",
            "config": {}
          },
          "model_client_stream": False,
          "reflect_on_tool_use": False,
          "tool_call_summary_format": "{result}"
        }
      }
    ],
    "termination_condition": {
      "provider": "autogen_agentchat.base.OrTerminationCondition",
      "component_type": "termination",
      "version": 1,
      "component_version": 1,
      "label": "OrTerminationCondition",
      "config": {
        "conditions": [
          {
            "provider": "autogen_agentchat.conditions.MaxMessageTermination",
            "component_type": "termination",
            "version": 1,
            "component_version": 1,
            "description": "Terminate after 5 messages have been exchanged.",
            "label": "MaxMessageTermination",
            "config": {"max_messages": 5}
          },
          {
            "provider": "autogen_agentchat.conditions.TextMentionTermination",
            "component_type": "termination",
            "version": 1,
            "component_version": 1,
            "description": "Terminate if 'TERMINATE' is mentioned.",
            "label": "TextMentionTermination",
            "config": {"text": "TERMINATE"}
          }
        ]
      }
    },
    "selector_prompt": (
      "You are the coordinator of a role-playing conversation. "
      "The following roles are available: {roles} and the following participants: {participants}. "
      "Given the conversation so far: {history}, select the next role from {roles} to speak. "
      "Only return the role name."
    ),
    "allow_repeated_speaker": False
  }
}

def substitute_env_variables(config):
    if isinstance(config, dict):
        return {k: substitute_env_variables(v) for k, v in config.items()}
    elif isinstance(config, list):
        return [substitute_env_variables(item) for item in config]
    elif isinstance(config, str):
        return config.replace("${OPENAI_API_KEY}", os.getenv("OPENAI_API_KEY", ""))
    else:
        return config

def main():
    load_dotenv()
    openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
    if not openrouter_api_key:
        logging.error("❌ OPENROUTER_API_KEY non è definita!")
        return

    team_config_full = substitute_env_variables(TEAM_CONFIG)
    logging.debug("Team configuration dopo la sostituzione delle variabili:")
    logging.debug(team_config_full)

    team_config = team_config_full.get("config", {})
    if not team_config:
        logging.error("❌ Configurazione del team non trovata sotto 'config'.")
        return

    if "initial_messages" in team_config:
        logging.warning("Rimuovo 'initial_messages' dalla configurazione (non accettata dal costruttore).")
        team_config.pop("initial_messages")

    if "model_client" not in team_config:
        logging.warning("Aggiungo 'model_client' alla configurazione del team.")
        team_config["model_client"] = {
            "provider": "autogen_ext.models.openai.OpenAIChatCompletionClient",
            "config": {
                "model": "gpt-4o-mini",
                "api_key": os.getenv("OPENAI_API_KEY"),
                "organization": "openrouter",
                "base_url": os.getenv("OPENROUTER_API_BASE", "https://openrouter.ai/api/v1"),
                "timeout": 90,
                "temperature": 0.2,
                "max_tokens": 750,
                "top_p": 0.9,
                "frequency_penalty": 0.1,
                "presence_penalty": 0.2,
                "stop": ["TERMINATE"],
                "model_info": {
                    "name": "gpt-4o-mini",
                    "description": "gpt-4o-mini via OpenRouter, supporting function calling.",
                    "vision": False,
                    "function_calling": True,
                    "json_output": True,
                    "family": "gpt-35"
                }
            }
        }

    # Converte la lista dei partecipanti (attualmente dizionari) in istanze di AssistantAgent.
    participants_config = team_config.get("participants", [])
    participants = []
    for p in participants_config:
        agent_conf = p.get("config", {})
        # Costruiamo l'agente SENZA passare 'llm_config'
        try:
            agent = AssistantAgent(
                name=agent_conf.get("name", "UnnamedAgent"),
                system_message=agent_conf.get("system_message", "")
            )
        except Exception as e:
            logging.error("Errore nell'istanziazione di AssistantAgent: " + str(e))
            continue
        # Se il client del modello è disponibile, proviamo a istanziarlo
        mc_conf = agent_conf.get("model_client", {}).get("config", {})
        if OpenAIChatCompletionClient is not None and mc_conf:
            try:
                model_client = OpenAIChatCompletionClient(**mc_conf)
                agent.model_client = model_client
            except Exception as e:
                logging.error("Errore nell'istanziazione di model_client: " + str(e))
        participants.append(agent)
    team_config["participants"] = participants

    try:
        team_chat = SelectorGroupChat(**team_config)
        logging.info("Team chat istanziato correttamente.")
    except Exception as e:
        logging.exception("❌ Errore durante l'istanza del team chat: " + str(e))
        return

    try:
        logging.info("Avvio della conversazione del team...")
        team_chat.start_chat()  # Usa .run() se richiesto dalla versione della libreria
    except Exception as e:
        logging.exception("❌ Errore durante l'esecuzione della conversazione del team: " + str(e))

if __name__ == "__main__":
    setup_logging()
    main()
