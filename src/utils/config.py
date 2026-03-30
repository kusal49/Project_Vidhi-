"""
Environment variable management and validation.
All config values are read from here — never import os.getenv elsewhere.
"""
import os
from dotenv import load_dotenv

load_dotenv()


def get_env_var(var_name: str, required: bool = True) -> str:
    value = os.getenv(var_name)
    if required and not value:
        raise ValueError(
            f"CRITICAL: '{var_name}' is missing from your .env file.\n"
            f"See .env.example for all required keys."
        )
    return value or ""


def validate_environment():
    """Validate all required keys are present at startup."""
    required = ["GROQ_API_KEY"]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing)}\n"
            f"Copy .env.example → .env and fill in your keys."
        )


# Typed config accessors
def groq_api_key() -> str:
    return get_env_var("GROQ_API_KEY")

def chroma_persist_dir() -> str:
    return get_env_var("CHROMA_PERSIST_DIR", required=False) or "data/chroma_db"

def gmail_credentials_path() -> str:
    return get_env_var("GMAIL_CREDENTIALS_PATH", required=False) or "credentials.json"

def gmail_token_path() -> str:
    return get_env_var("GMAIL_TOKEN_PATH", required=False) or "token.json"

def langsmith_enabled() -> bool:
    return os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
