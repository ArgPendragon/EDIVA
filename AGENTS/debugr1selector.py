import os
import logging
from autogen_agentchat.teams import SelectorGroupChat
from autogen import GroupChatManager, AssistantAgent

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

llm_config = {
    "config_list": [{
        "model": "gpt-3.5-turbo",
        "api_key": os.getenv("OPENROUTER_API_KEY"),
        "base_url": "https://openrouter.ai/api/v1",
        "headers": {
            "HTTP-Referer": "https://myapp.ediva.it",
            "X-Title": "AutoGen-Selector"
        }
    }]
}

TEAM_CONFIG = {
    "participants": [
        {
            "name": "AgentA",
            "system_message": "Fai domande filosofiche. Termina con 'TU COSA NE PENSI?'.",
            "llm_config": llm_config
        },
        {
            "name": "AgentB",
            "system_message": "Dai spiegazioni scientifiche. Termina con 'VUOI CHIARIMENTI?'.",
            "llm_config": llm_config
        }
    ],
    "selector_prompt": """Ruoli disponibili: {roles}.
    Ultimo messaggio: {last_message}
    Scegli il prossimo ruolo tra {roles}.""",
    "max_messages": 5
}

agents = [AssistantAgent(**config) for config in TEAM_CONFIG["participants"]]

team_chat = SelectorGroupChat(
    participants=agents,
    selector_prompt=TEAM_CONFIG["selector_prompt"],
    termination_condition=lambda: len(team_chat.messages) >= TEAM_CONFIG["max_messages"]
)

manager = GroupChatManager(
    groupchat=team_chat,
    llm_config=llm_config
)

try:
    manager.initiate_chat(initial_message="La felicità può essere misurata scientificamente?")
except Exception as e:
    logger.error(f"Errore iniziale: {str(e)}")
