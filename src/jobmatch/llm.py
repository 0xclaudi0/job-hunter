"""One place that calls Claude, so every request gets the same checks."""

from __future__ import annotations

from typing import Any, Protocol

FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_TOKENS = 16000


class ClaudeError(RuntimeError):
    pass


class ClaudeClient(Protocol):
    """anthropic.Anthropic() fits this. Tests pass a fake."""

    beta: Any


def call_claude(
    client: ClaudeClient,
    model: str,
    effort: str,
    system: str,
    prompt: str,
    schema: dict | None = None,
) -> str:
    """Send one request and return the text reply. Raise ClaudeError when no usable text came back."""
    output_config: dict[str, Any] = {"effort": effort}
    if schema is not None:
        output_config["format"] = {"type": "json_schema", "schema": schema}

    response = client.beta.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        betas=[FALLBACK_BETA],
        fallbacks="default",  # on a safety decline, the API re-runs the request on a fallback model
        output_config=output_config,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )

    if response.stop_reason == "refusal":
        details = getattr(response, "stop_details", None)
        category = getattr(details, "category", None) if details else None
        raise ClaudeError(f"Claude declined the request (category: {category})")
    if response.stop_reason == "max_tokens":
        raise ClaudeError(f"Reply was cut off at max_tokens={MAX_TOKENS}")

    text = "".join(block.text for block in response.content if block.type == "text").strip()
    if not text:
        raise ClaudeError("Claude returned no text")
    return text
