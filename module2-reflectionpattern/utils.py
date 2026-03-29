# === Standard Library ===
import os
import re
import json
import base64
import mimetypes
from pathlib import Path

# === Third-Party (lightweight imports only) ===
from dotenv import load_dotenv, find_dotenv
try:
    # Newer/older Anthropic SDKs export different names; try common ones.
    from anthropic import Anthropic as AnthropicClient
except Exception:
    try:
        from anthropic import Client as AnthropicClient
    except Exception:
        AnthropicClient = None
from html import escape

# === Env & Clients ===
# Load the nearest .env file (search parent folders) so notebooks run from subfolders still find keys
load_dotenv(find_dotenv())
openai_api_key = os.getenv("OPENAI_API_KEY")
anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
anthropic_base_url = os.getenv("ANTHROPIC_BASE_URL", "").strip() or None

openai_client = None

def _get_openai_client():
    global openai_client
    if openai_client is not None:
        return openai_client
    try:
        from openai import OpenAI
    except Exception as e:
        raise RuntimeError("OpenAI SDK not installed; install the 'openai' package") from e
    openai_client = OpenAI(api_key=openai_api_key) if openai_api_key else OpenAI()
    return openai_client

# Initialize Anthropic client if available; be defensive about SDK differences
if AnthropicClient is None:
    anthropic_client = None
else:
    try:
        if anthropic_api_key:
            anthropic_client = AnthropicClient(api_key=anthropic_api_key)
        else:
            anthropic_client = AnthropicClient()
        # If a custom base URL is provided, try to set it (some SDKs accept this)
        if anthropic_base_url:
            try:
                setattr(anthropic_client, "base_url", anthropic_base_url)
            except Exception:
                # ignore if SDK doesn't support setting base_url this way
                pass
    except Exception:
        anthropic_client = None

def _require_anthropic():
    if anthropic_client is None:
        raise RuntimeError(
            "Anthropic client not available. Install the 'anthropic' package and set ANTHROPIC_API_KEY, or set ANTHROPIC_BASE_URL if needed."
        )


def get_response(model: str, prompt: str) -> str:
    if "claude" in model.lower() or "anthropic" in model.lower():
        # Anthropic / Claude-style models
        _require_anthropic()
        try:
            message = anthropic_client.messages.create(
                model=model,
                max_tokens=1000,
                messages=[{"role": "user", "content": [{"type": "text", "text": prompt}]}],
            )
            # Try common access patterns for text
            if hasattr(message, "content") and message.content:
                first = message.content[0]
                return getattr(first, "text", str(first))
            return str(message)
        except Exception:
            # Fallbacks for different SDK interfaces
            try:
                if hasattr(anthropic_client, "chat"):
                    resp = anthropic_client.chat.create(model=model, messages=[{"role": "user", "content": prompt}])
                    return getattr(resp, "content", "") or str(resp)
            except Exception:
                pass
            raise

    else:
        # Default to OpenAI format for all other models (gpt-4, o3-mini, o1, etc.)
        client = _get_openai_client()
        response = client.responses.create(
            model=model,
            input=prompt,
        )
        return response.output_text
    
# === Data Loading ===
def load_and_prepare_data(csv_path: str):
    """Load CSV and derive date parts commonly used in charts.

    Imports pandas lazily so importing this module doesn't require pandas.
    """
    try:
        import pandas as pd
    except Exception as e:
        raise RuntimeError("pandas is required to load and prepare data") from e

    df = pd.read_csv(csv_path)
    # Be tolerant if 'date' exists
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["quarter"] = df["date"].dt.quarter
        df["month"] = df["date"].dt.month
        df["year"] = df["date"].dt.year
    return df

# === Helpers ===
def make_schema_text(df) -> str:
    """Return a human-readable schema from a DataFrame-like object.

    This function does not require pandas to be imported at module load.
    """
    try:
        dtypes = df.dtypes
    except Exception:
        # Fallback to introspecting values
        return "\n".join(f"- {c}: {type(df[c])}" for c in df.columns)
    return "\n".join(f"- {c}: {dt}" for c, dt in dtypes.items())

def ensure_execute_python_tags(text: str) -> str:
    """Normalize code to be wrapped in <execute_python>...</execute_python>."""
    text = text.strip()
    # Strip ```python fences if present
    text = re.sub(r"^```(?:python)?\s*|\s*```$", "", text).strip()
    if "<execute_python>" not in text:
        text = f"<execute_python>\n{text}\n</execute_python>"
    return text

def encode_image_b64(path: str) -> tuple[str, str]:
    """Return (media_type, base64_str) for an image file path."""
    mime, _ = mimetypes.guess_type(path)
    media_type = mime or "image/png"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return media_type, b64


from typing import Any

def print_html(content: Any, title: str | None = None, is_image: bool = False):
    """
    Pretty-print inside a styled card.
    - If is_image=True and content is a string: treat as image path/URL and render <img>.
    - If content is a pandas DataFrame/Series: render as an HTML table.
    - Otherwise (strings/others): show as code/text in <pre><code>.
    """
    try:
        from html import escape as _escape
    except ImportError:
        _escape = lambda x: x

    def image_to_base64(image_path: str) -> str:
        import base64
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode("utf-8")

    # Render content
    if is_image and isinstance(content, str):
        b64 = image_to_base64(content)
        rendered = f'<img src="data:image/png;base64,{b64}" alt="Image" style="max-width:100%; height:auto; border-radius:8px;">'
    else:
        # Lazy-check for pandas DataFrame/Series
        try:
            import pandas as pd
            is_df = isinstance(content, pd.DataFrame)
            is_series = isinstance(content, pd.Series)
        except Exception:
            is_df = False
            is_series = False

        if is_df:
            rendered = content.to_html(classes="pretty-table", index=False, border=0, escape=False)
        elif is_series:
            rendered = content.to_frame().to_html(classes="pretty-table", border=0, escape=False)
        elif isinstance(content, str):
            rendered = f"<pre><code>{_escape(content)}</code></pre>"
        else:
            rendered = f"<pre><code>{_escape(str(content))}</code></pre>"

    css = """
    <style>
    .pretty-card{
      font-family: ui-sans-serif, system-ui;
      border: 2px solid transparent;
      border-radius: 14px;
      padding: 14px 16px;
      margin: 10px 0;
      background: linear-gradient(#fff, #fff) padding-box,
                  linear-gradient(135deg, #3b82f6, #9333ea) border-box;
      color: #111;
      box-shadow: 0 4px 12px rgba(0,0,0,.08);
    }
    .pretty-title{
      font-weight:700;
      margin-bottom:8px;
      font-size:14px;
      color:#111;
    }
    /* 🔒 Only affects INSIDE the card */
    .pretty-card pre, 
    .pretty-card code {
      background: #f3f4f6;
      color: #111;
      padding: 8px;
      border-radius: 8px;
      display: block;
      overflow-x: auto;
      font-size: 13px;
      white-space: pre-wrap;
    }
    .pretty-card img { max-width: 100%; height: auto; border-radius: 8px; }
    .pretty-card table.pretty-table {
      border-collapse: collapse;
      width: 100%;
      font-size: 13px;
      color: #111;
    }
    .pretty-card table.pretty-table th, 
    .pretty-card table.pretty-table td {
      border: 1px solid #e5e7eb;
      padding: 6px 8px;
      text-align: left;
    }
    .pretty-card table.pretty-table th { background: #f9fafb; font-weight: 600; }
    </style>
    """

    title_html = f'<div class="pretty-title">{title}</div>' if title else ""
    card = f'<div class="pretty-card">{title_html}{rendered}</div>'
    try:
        from IPython.display import HTML, display
        display(HTML(css + card))
    except Exception:
        # Fallback: print raw HTML for environments without IPython
        print(css + card)

    

    
def image_anthropic_call(model_name: str, prompt: str, media_type: str, b64: str) -> str:
    """
    Call Anthropic Claude (messages.create) with text+image and return *all* text blocks concatenated.
    Adds a system message to enforce strict JSON output.
    """
    msg = anthropic_client.messages.create(
        model=model_name,
        max_tokens=2000,
        temperature=0,
        system=(
            "You are a careful assistant. Respond with a single valid JSON object only. "
            "Do not include markdown, code fences, or commentary outside JSON."
        ),
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
            ],
        }],
    )

    # Anthropic returns a list of content blocks; collect all text
    parts = []
    for block in (msg.content or []):
        if getattr(block, "type", None) == "text":
            parts.append(block.text)
    return "".join(parts).strip()


def image_openai_call(model_name: str, prompt: str, media_type: str, b64: str) -> str:
    data_url = f"data:{media_type};base64,{b64}"
    client = _get_openai_client()
    resp = client.responses.create(
        model=model_name,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": data_url},
                ],
            }
        ],
    )
    content = (resp.output_text or "").strip()
    return content