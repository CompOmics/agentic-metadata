import os
from openai import OpenAI
from .logging import get_logger

logger = get_logger(__name__)

class LLMClient:
    def __init__(self, config=None):
        config = config or {}

        # Auto-detect provider from model name prefix if not explicitly set
        model = config.get("model", "llama-4-scout")
        default_provider = "openai"
        if model.startswith("claude"):
            default_provider = "anthropic"
        elif model.startswith("gemini"):
            default_provider = "gemini"

        self.provider = config.get("provider", default_provider)
        self.base_url = config.get("base_url", "https://llm.jetstream-cloud.org/llama-4-scout/v1/")
        self.model = model

        # First check for direct api_key in config
        self.api_key = config.get("api_key", "")

        # If not found, try environment variable
        if not self.api_key:
            api_key_var = config.get("api_key_env_var", "LLM_API_KEY")
            self.api_key = os.environ.get(api_key_var, "")
            if not self.api_key:
                logger.warning(f"No API key found in config or environment variable {api_key_var}")

        # max_tokens for providers that require it (Anthropic)
        self.max_tokens = config.get("max_tokens", 4096)

        # Initialize appropriate client
        if self.provider == "gemini":
            self._init_gemini_client()
        elif self.provider == "anthropic":
            self._init_anthropic_client()
        else:
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

