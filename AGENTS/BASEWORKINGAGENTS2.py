{
  "provider": "autogen_agentchat.teams.SelectorGroupChat",
  "component_type": "team",
  "version": 1,
  "component_version": 1,
  "description": "A 2-agent team that converses for 5 rounds (10 messages exchanged) and then returns a final answer, with both {roles} and {participants} in the selector prompt.",
  "label": "2-Agent Selector Team",
  "config": {
    "model_client": {
      "provider": "autogen_ext.models.openai.OpenAIChatCompletionClient",
      "component_type": "model",
      "version": 1,
      "component_version": 1,
      "label": "TeamOpenAIChatCompletionClient",
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
        "stop": [
          "TERMINATE"
        ],
        "model_info": {
          "name": "gpt-4o-mini",
          "description": "gpt-4o-mini via OpenRouter, supporting function calling.",
          "vision": false,
          "function_calling": true,
          "json_output": true,
          "family": "gpt-4o-mini"
        }
      }
    },
    "initial_messages": [
      {
        "role": "user",
        "content": "What is the meaning of life?"
      }
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
          "name": "agent_a",
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
              "stop": [
                "TERMINATE"
              ],
              "model_info": {
                "name": "gpt-4o-mini",
                "description": "gpt-4o-mini via OpenRouter, supporting function calling.",
                "vision": false,
                "function_calling": true,
                "json_output": true,
                "family": "gpt-4o-mini"
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
          "model_client_stream": false,
          "reflect_on_tool_use": false,
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
          "name": "agent_b",
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
              "stop": [
                "TERMINATE"
              ],
              "model_info": {
                "name": "gpt-4o-mini",
                "description": "gpt-4o-mini via OpenRouter, supporting function calling.",
                "vision": false,
                "function_calling": true,
                "json_output": true,
                "family": "gpt-4o-mini"
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
          "model_client_stream": false,
          "reflect_on_tool_use": false,
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
            "description": "Terminate after 10 messages have been exchanged.",
            "label": "MaxMessageTermination",
            "config": {
              "max_messages": 10
            }
          },
          {
            "provider": "autogen_agentchat.conditions.TextMentionTermination",
            "component_type": "termination",
            "version": 1,
            "component_version": 1,
            "description": "Terminate if 'TERMINATE' is mentioned.",
            "label": "TextMentionTermination",
            "config": {
              "text": "TERMINATE"
            }
          }
        ]
      }
    },
    "selector_prompt": "You are the coordinator of a role-playing conversation. The following roles are available: {roles} and the following participants: {participants}. Given the conversation so far: {history}, select the next role from {roles} to speak. Only return the role name.",
    "allow_repeated_speaker": false
  }
}
