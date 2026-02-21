import time
import json
from typing import List, Dict, Any, Optional
from openai import OpenAI
from config import config
from utils.logger import log

class LLMClient:
    def __init__(self):
        self.api_key = config.OPENROUTER_API_KEY
        self.base_url = config.OPENROUTER_BASE_URL
        self.model_fast = config.OPENROUTER_MODEL_FAST
        self.model_main = config.OPENROUTER_MODEL_MAIN
        self.site_url = config.OPENROUTER_SITE_URL
        self.app_name = config.OPENROUTER_APP_NAME

        self.client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            default_headers={
                "HTTP-Referer": self.site_url,
                "X-Title": self.app_name,
            }
        )

    def complete(self, 
                 system: str, 
                 user: str, 
                 model: str = "main",   # "main" or "fast"
                 temperature: float = 0.7,
                 max_tokens: int = 2000,
                 response_format: str = "text"  # "text" or "json"
                ) -> str:
        
        model_name = self.model_main if model == "main" else self.model_fast
        
        sys_prompt = system
        if response_format == "json":
            sys_prompt += "\nRespond ONLY with valid JSON. No markdown, no explanation."

        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user}
        ]

        def _make_request():
            completion = self.client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                extra_body={"response_format": {"type": "json_object"}} if response_format == "json" else None
            )
            log.info(f"Using model: {model_name}", context="LLMClient")
            return completion

        try:
            # First attempt
            response = _make_request()
        except Exception as e:
            log.warning(f"LLM request failed: {e}. Retrying in 3s...", context="LLMClient")
            time.sleep(3)
            try:
                # Retry once
                response = _make_request()
            except Exception as e:
                log.error(f"LLM request failed after retry: {e}", context="LLMClient")
                raise

        content = response.choices[0].message.content
        
        # Log usage info if available
        usage = getattr(response, 'usage', None)
        if usage:
            log.info(f"Model: {model_name} | Prompt: {usage.prompt_tokens} | Completion: {usage.completion_tokens}", context="LLMClient")
        
        return content

    def complete_json(self, system: str, user: str, model: str = "main") -> dict:
        """
        Calls complete() with response_format="json", parses and returns dict.
        Uses a higher max_tokens to avoid truncation of large JSON responses from
        free-tier models that have low default output limits.
        """
        content = self.complete(
            system, user,
            model=model,
            response_format="json",
            max_tokens=4096  # override default 2000 to avoid truncated JSON
        )
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            log.warning(f"JSON parse failed ({e}). Attempting rescue of truncated response...", context="LLMClient")
            # Rescue: try to find the last valid closing brace/bracket and parse up to there
            rescued = _rescue_truncated_json(content)
            if rescued is not None:
                log.warning("Rescued partial JSON from truncated LLM response.", context="LLMClient")
                return rescued
            log.error(f"Failed to parse JSON response (unrecoverable):\n{content[:500]}...", context="LLMClient")
            raise ValueError(f"Invalid JSON response from LLM: {content}") from e


def _rescue_truncated_json(content: str) -> "dict | None":
    """
    Try to close a truncated JSON string by finding the last complete
    top-level object or array and parsing just that portion.
    """
    import json
    # Try progressively shorter substrings ending at }, ] to find valid JSON
    for end_char in ('}', ']'):
        idx = content.rfind(end_char)
        while idx > 0:
            candidate = content[:idx + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                idx = content.rfind(end_char, 0, idx)
    return None
