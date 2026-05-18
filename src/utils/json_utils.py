import json
import re
from pathlib import Path


def safe_json_load(path, default=None, label: str = ""):
    """Load JSON from a file path (str or Path), returning `default` on any error."""
    p = Path(path)
    tag = label or p.name
    if not p.exists():
        print(f"[json_utils] WARNING: {tag} not found; using default.")
        return default
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"[json_utils] WARNING: {tag} is malformed ({e}); using default.")
        return default


def parse_llm_json(raw: str, label: str = "") -> dict:
    """
    Parse JSON from an LLM response robustly:
      1. Guard against None / empty.
      2. Strip markdown code fences (```json ... ``` or ``` ... ```).
      3. Direct parse.
      4. Regex extraction of first {...} or [...] block.
    Raises ValueError with the raw tail on total failure.
    """
    if not raw:
        raise ValueError(f"[{label or 'llm'}] LLM returned empty response")

    text = raw.strip()

    # 1. Strip markdown fence
    fence = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        try:
            return json.loads(fence.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 2. Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 3. Extract first JSON object or array
    for open_ch, close_ch in [('{', '}'), ('[', ']')]:
        start = text.find(open_ch)
        end   = text.rfind(close_ch)
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass

    raise ValueError(
        f"[{label or 'llm'}] Could not extract valid JSON from LLM response.\n"
        f"Response tail: ...{raw[-300:]}"
    )
