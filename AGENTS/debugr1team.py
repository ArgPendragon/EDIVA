import os
import logging
from dotenv import load_dotenv
from autogen import GroupChatManager, GroupChat, UserProxyAgent, AssistantAgent

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

llm_config = {
    "config_list": [{
        "model": "gpt-3.5-turbo",
        "api_key": os.getenv("OPENROUTER_API_KEY"),
        "base_url": "https://openrouter.ai/api/v1",
        "headers": {
            "HTTP-Referer": "https://myapp.ediva.it",
            "X-Title": "AutoGen-Team"
        }
    }]
}

philosopher = AssistantAgent(
    name="AgentA",
    system_message="Risposte filosofiche brevi (max 15 parole).",
    llm_config=llm_config
)

analyst = AssistantAgent(
    name="AgentB",
    system_message="Analisi tecniche concise (max 15 parole).",
    llm_config=llm_config
)

groupchat = GroupChat(
    agents=[philosopher, analyst],
    messages=[],
    max_round=6,
    speaker_selection_method="round_robin"
)

manager = GroupChatManager(
    groupchat=groupchat,
    llm_config=llm_config
)

user_proxy = UserProxyAgent(
    name="UserProxy",
    human_input_mode="NEVER",
    max_consecutive_auto_reply=0,
    code_execution_config={"use_docker": False}
)

try:
    user_proxy.initiate_chat(
        manager,
        message="Spiegami la teoria della relatività in 2 frasi.",
        clear_history=True
    )
except Exception as e:
    logger.error(f"Errore: {str(e)}")
