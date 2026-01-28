import os
from openai import OpenAI
from .logging import get_logger

logger = get_logger(__name__)

class LLMClient:
    def __init__(self, config=None):
        config = config or {}
        self.base_url = config.get("base_url", "https://llm.jetstream-cloud.org/llama-4-scout/v1/")
        self.model = config.get("model", "llama-4-scout")
        
        api_key_var = config.get("api_key_env_var", "LLM_API_KEY")
        self.api_key = os.environ.get(api_key_var, "")
        
        if not self.api_key:
            logger.warning(f"No API key found in environment variable {api_key_var}")

        self.client = OpenAI(base_url=self.base_url, api_key=self.api_key)

    def get_completion(self, messages, temperature=0.0):
        chat_completion = self.client.chat.completions.create(
            messages=messages,
            model=self.model,
            temperature=temperature,
        )
        return chat_completion.choices[0].message.content
