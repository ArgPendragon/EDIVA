# your_autogen_script.py

import os
import openai
from dotenv import load_dotenv

#########################################
# 1) Load .env variables
#########################################
load_dotenv()  # This reads your .env file

openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "")
openrouter_api_base = os.getenv("OPENROUTER_API_BASE", "https://openrouter.ai/api/v1")
openrouter_model = os.getenv("OPENROUTER_MODEL", "openai/gpt-3.5-turbo")

#########################################
# 2) Configure openai for OpenRouter
#########################################
openai.api_base = openrouter_api_base
openai.api_key = openrouter_api_key
openai.default_headers.update({
    "Authorization": f"Bearer {openai.api_key}"
})

#########################################
# 3) Setup llm_config for AutoGen
#########################################
llm_config = {
    "api_key": openai.api_key,
    "model": openrouter_model,
    "use_cache": False,
    "config_list": [
        {
            "api_key": openai.api_key,
            "model": openrouter_model
        }
    ]
}

#########################################
# 4) Create Agents
#########################################
from autogen import AssistantAgent, UserProxyAgent

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
# 5) Initiate Conversation
#########################################
user_proxy.initiate_chat(
    assistant,
    message="Hello, are we connected to OpenRouter?"
)
