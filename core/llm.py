import os
from openai import OpenAI
from .logging import get_logger

logger = get_logger(__name__)
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

class LLMClient:
    def __init__(self, config=None):
        config = config or {}

        configured_provider = config.get("provider")
        configured_endpoint = config.get("base_url")
        configured_key_var = config.get("api_key_env_var")
        if configured_provider not in (None, "openrouter"):
            raise ValueError("Only the OpenRouter provider is supported.")
        if configured_endpoint and configured_endpoint.rstrip("/") != OPENROUTER_BASE_URL:
            raise ValueError(f"Only the OpenRouter endpoint is supported: {OPENROUTER_BASE_URL}")
        if configured_key_var not in (None, "OPENROUTER_API_KEY"):
            raise ValueError("Only OPENROUTER_API_KEY is supported for LLM credentials.")

        self.provider = "openrouter"
        self.base_url = OPENROUTER_BASE_URL
        self.model = config.get("model", "google/gemma-4-31b-it")
        self.api_key = os.environ.get("OPENROUTER_API_KEY", "")
        if not self.api_key:
            raise EnvironmentError("OPENROUTER_API_KEY environment variable is not set.")

        # max_tokens for providers that require it (Anthropic)
        self.max_tokens = config.get("max_tokens", 4096)

        self.client = OpenAI(base_url=self.base_url, api_key=self.api_key)

    # ------------------------------------------------------------------
    # Gemini
    # ------------------------------------------------------------------

    def _init_gemini_client(self):
        """Initialize Google Generative AI client for Gemini."""
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self.gemini_model = genai.GenerativeModel(self.model)
            logger.info(f"Initialized Gemini client with model: {self.model}")
        except ImportError:
            raise ImportError(
                "google-generativeai package required for Gemini. "
                "Install with: pip install google-generativeai"
            )

    def _get_gemini_completion(self, messages, temperature=0.0):
        """Get completion from Google Gemini API."""
        gemini_messages = []
        system_prompt = None

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                system_prompt = content
            elif role == "user":
                gemini_messages.append({"role": "user", "parts": [content]})
            elif role == "assistant":
                gemini_messages.append({"role": "model", "parts": [content]})

        chat = self.gemini_model.start_chat(
            history=gemini_messages[:-1] if len(gemini_messages) > 1 else []
        )

        final_prompt = gemini_messages[-1]["parts"][0] if gemini_messages else ""
        if system_prompt:
            final_prompt = f"{system_prompt}\n\n{final_prompt}"

        generation_config = {"temperature": temperature}
        response = chat.send_message(final_prompt, generation_config=generation_config)
        return response.text

    # ------------------------------------------------------------------
    # Anthropic
    # ------------------------------------------------------------------

    def _init_anthropic_client(self):
        """Initialize Anthropic client for Claude models."""
        try:
            import anthropic
            self.anthropic_client = anthropic.Anthropic(api_key=self.api_key)
            logger.info(f"Initialized Anthropic client with model: {self.model}")
        except ImportError:
            raise ImportError(
                "anthropic package required for Claude models. "
                "Install with: pip install anthropic"
            )

    def _get_anthropic_completion(self, messages, temperature=0.0):
        """Get completion from Anthropic Claude API (Messages API).

        The Anthropic Messages API requires the system prompt to be passed
        as a top-level ``system`` argument rather than as a message with
        role='system'.  Non-system messages are forwarded as-is.
        """
        system_prompt = None
        anthropic_messages = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                # Anthropic takes a single top-level system string;
                # concatenate if multiple system messages are present.
                system_prompt = (system_prompt + "\n\n" + content) if system_prompt else content
            else:
                # 'user' and 'assistant' roles map directly
                anthropic_messages.append({"role": role, "content": content})

        kwargs = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": temperature,
            "messages": anthropic_messages,
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        response = self.anthropic_client.messages.create(**kwargs)
        return response.content[0].text

    # ------------------------------------------------------------------
    # OpenAI-compatible
    # ------------------------------------------------------------------

    def _get_openai_completion(self, messages, temperature=0.0):
        """Get completion from OpenAI-compatible API."""
        try:
            from .reproducibility import get_seed
            seed = get_seed()
        except ImportError:
            seed = None

        kwargs = {
            "messages": messages,
            "model": self.model,
            "temperature": temperature,
        }

        if seed is not None:
            kwargs["seed"] = seed

        chat_completion = self.client.chat.completions.create(**kwargs)
        return chat_completion.choices[0].message.content

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def get_completion(self, messages, temperature=0.0):
        if self.provider == "gemini":
            return self._get_gemini_completion(messages, temperature)
        elif self.provider == "anthropic":
            return self._get_anthropic_completion(messages, temperature)
        else:
            return self._get_openai_completion(messages, temperature)

