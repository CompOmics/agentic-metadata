from openai import OpenAI

class LLMClient:
    def __init__(self, base_url="https://llm.jetstream-cloud.org/llama-4-scout/v1/", api_key="", model="llama-4-scout"):
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model

    def get_completion(self, messages, temperature=0.0):
        chat_completion = self.client.chat.completions.create(
            messages=messages,
            model=self.model,
            temperature=temperature,
        )
        return chat_completion.choices[0].message.content
