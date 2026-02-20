"""
Configuration management for the uxai-ugc-agent.
Handles loading environment variables and provides a centralized config object.
"""

import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # OpenRouter
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_BASE_URL: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    OPENROUTER_MODEL_FAST: str = os.getenv("OPENROUTER_MODEL_FAST", "anthropic/claude-haiku-4-5")
    OPENROUTER_MODEL_MAIN: str = os.getenv("OPENROUTER_MODEL_MAIN", "anthropic/claude-sonnet-4-6")
    OPENROUTER_SITE_URL: str = os.getenv("OPENROUTER_SITE_URL", "http://localhost:5000")
    OPENROUTER_APP_NAME: str = os.getenv("OPENROUTER_APP_NAME", "uxai-ugc-agent")

    # Media APIs
    ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")
    ELEVENLABS_VOICE_ID: str = os.getenv("ELEVENLABS_VOICE_ID", "")
    HEYGEN_API_KEY: str = os.getenv("HEYGEN_API_KEY", "")
    HEYGEN_AVATAR_ID: str = os.getenv("HEYGEN_AVATAR_ID", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    # Reddit
    REDDIT_CLIENT_ID: str = os.getenv("REDDIT_CLIENT_ID", "")
    REDDIT_CLIENT_SECRET: str = os.getenv("REDDIT_CLIENT_SECRET", "")
    REDDIT_USER_AGENT: str = os.getenv("REDDIT_USER_AGENT", "uxai-ugc-agent/1.0")

    # Notifications
    NTFY_URL: str = os.getenv("NTFY_URL", "https://ntfy.stargety.com/ugc")

    # Pipeline behavior
    HUMAN_REVIEW_TIMEOUT_SECONDS: int = int(os.getenv("HUMAN_REVIEW_TIMEOUT_SECONDS", "120"))
    QA_AUTO_APPROVE_THRESHOLD: float = float(os.getenv("QA_AUTO_APPROVE_THRESHOLD", "7.5"))
    MAX_QA_ITERATIONS: int = int(os.getenv("MAX_QA_ITERATIONS", "3"))
    PROCESSING_RESOLUTION: int = int(os.getenv("PROCESSING_RESOLUTION", "720"))
    OUTPUT_DIR: str = os.getenv("OUTPUT_DIR", "./output")

config = Config()
