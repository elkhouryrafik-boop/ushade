import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import (
    LLM_PROVIDER, ANTHROPIC_API_KEY, ANTHROPIC_MODEL,
    OPENAI_API_KEY, OPENAI_MODEL
)


def provider_name() -> str:
    if LLM_PROVIDER == "anthropic" and ANTHROPIC_API_KEY:
        return "anthropic"
    if OPENAI_API_KEY:
        return "openai"
    return "offline"


def complete(system_prompt: str, messages: list, max_tokens: int = 900) -> str | None:
    if LLM_PROVIDER == "anthropic" and ANTHROPIC_API_KEY:
        result = _anthropic_complete(system_prompt, messages, max_tokens)
        if result is not None:
            return result

    if OPENAI_API_KEY:
        return _openai_complete(system_prompt, messages, max_tokens)

    return None


def _anthropic_complete(system_prompt: str, messages: list, max_tokens: int) -> str | None:
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=messages,
        )
        return response.content[0].text
    except Exception:
        return None


def _openai_complete(system_prompt: str, messages: list, max_tokens: int) -> str | None:
    try:
        import openai
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        full_messages = [{"role": "system", "content": system_prompt}] + messages
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            max_tokens=max_tokens,
            messages=full_messages,
        )
        return response.choices[0].message.content
    except Exception:
        return None
