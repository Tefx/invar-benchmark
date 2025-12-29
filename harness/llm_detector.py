"""
LLM-based semantic detection for interactive mode automation.

Uses OpenAI API to determine if the agent is waiting for user input.
"""

import json
import os
from pathlib import Path
from typing import Optional

# Load .env file if present
_env_loaded = False


def _load_env():
    """Load environment variables from .env file."""
    global _env_loaded
    if _env_loaded:
        return
    _env_loaded = True

    # Find .env in project root
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip())


# Lazy import to avoid dependency if not used
_openai_client: Optional[object] = None


def _get_client():
    """Get or create OpenAI client."""
    global _openai_client
    if _openai_client is None:
        _load_env()  # Load .env before checking
        try:
            from openai import OpenAI
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable not set")
            _openai_client = OpenAI(api_key=api_key)
        except ImportError:
            raise ImportError("openai package not installed. Run: pip install openai")
    return _openai_client


SYSTEM_PROMPT = """You analyze CLI output from an AI coding assistant to determine if it's waiting for user input.

Respond ONLY with a JSON object (no markdown, no explanation):
{"waiting": true/false, "response": "suggested input if waiting, else empty string"}

WAITING signals (respond with "continue" or appropriate action):
- Questions: "Next step?", "What would you like?", "Should I...", "How should I proceed?"
- Explicit prompts ending with "?"
- Requests for confirmation or direction
- Idle state after completing a task

NOT WAITING signals (respond with empty string):
- Active tool execution (Read, Write, Edit, Bash, etc.)
- Code generation in progress
- Thinking/processing indicators
- Partial output still streaming
- Error messages being displayed

For most waiting cases, respond with "continue" to let the agent proceed autonomously."""


def detect_waiting_state(recent_output: str, model: str = "gpt-4o-mini") -> tuple[bool, str]:
    """
    Use LLM to determine if agent is waiting for user input.

    Args:
        recent_output: Recent CLI output (last ~1000 chars)
        model: OpenAI model to use (default: gpt-4o-mini for cost/speed)

    Returns:
        (is_waiting, suggested_response)
    """
    if not recent_output.strip():
        return False, ""

    try:
        client = _get_client()

        # Truncate to last 1500 chars to manage token usage
        truncated = recent_output[-1500:] if len(recent_output) > 1500 else recent_output

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Recent CLI output:\n\n{truncated}"}
            ],
            max_tokens=100,
            temperature=0,
        )

        content = response.choices[0].message.content.strip()

        # Parse JSON response
        # Handle potential markdown wrapping
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]

        result = json.loads(content)
        is_waiting = result.get("waiting", False)
        suggested = result.get("response", "continue" if is_waiting else "")

        return is_waiting, suggested

    except Exception as e:
        # On any error, fall back to not waiting (safe default)
        print(f"[LLM Detector] Error: {e}")
        return False, ""


def is_llm_detection_available() -> bool:
    """Check if LLM detection is available (API key set)."""
    _load_env()
    return bool(os.environ.get("OPENAI_API_KEY"))
