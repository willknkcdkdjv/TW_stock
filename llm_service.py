import json
import os
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    AuthenticationError,
    BadRequestError,
    OpenAI,
    RateLimitError,
)

BASE_DIR = Path(__file__).resolve().parent
MODEL = "gpt-5.5"

SYSTEM_INSTRUCTION = """你是一位謹慎的台灣股市市場分析師。

你必須遵守以下規則：
- 僅能根據使用者提供的市場脈絡（context）回答，不可引用脈絡以外的即時或歷史資料。
- 若脈絡資料不足以回答問題，必須明確說明「資料不足，無法判斷」。
- 不得提供直接的買進、賣出、持有等投資建議。
- 不得預測股價或報酬。
- 在適當時將內容區分為：觀察（事實）、推論（解讀）、風險（不確定性）。
- 以簡潔、專業的繁體中文回答。
- 聚焦台股、產業趨勢、量能趨勢、突破訊號、估值與觀察名單等主題。"""

MISSING_API_KEY_MESSAGE = (
    "未設定 OPENAI_API_KEY。請在專案根目錄的 .env 檔案中加入：OPENAI_API_KEY=你的金鑰"
)


def _load_env() -> None:
    load_dotenv(BASE_DIR / ".env")


def _get_api_key() -> str | None:
    _load_env()
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    return api_key or None


LLM_LIST_LIMITS = {
    "industry_trend": 5,
    "volume_spike": 10,
    "breakout": 10,
    "top_turnover": 10,
    "cheap_value": 10,
    "high_dividend": 10,
}


def _json_default(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if hasattr(obj, "item"):
        return obj.item()
    return str(obj)


def sanitize_llm_context(context: dict) -> dict:
    """Ensure only summary scalars and capped row lists are sent to the LLM."""

    def sanitize_scalar(value):
        if isinstance(value, (pd.DataFrame, pd.Series)):
            return None
        if isinstance(value, float) and pd.isna(value):
            return None
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return float(value)
        if hasattr(value, "item"):
            return value.item()
        return value

    def sanitize_row(row: dict) -> dict:
        return {k: sanitize_scalar(v) for k, v in row.items()}

    sanitized: dict = {}

    for key, value in (context or {}).items():
        if key == "market_summary":
            summary = {}
            for sub_key, sub_value in (value or {}).items():
                if sub_key == "filters" and isinstance(sub_value, dict):
                    summary[sub_key] = {
                        k: sanitize_scalar(v) for k, v in sub_value.items()
                    }
                elif sub_key == "signal_summary" and isinstance(sub_value, dict):
                    summary[sub_key] = {
                        k: sanitize_scalar(v) for k, v in sub_value.items()
                    }
                else:
                    summary[sub_key] = sanitize_scalar(sub_value)
            sanitized[key] = summary
            continue

        if isinstance(value, (pd.DataFrame, pd.Series)):
            sanitized[key] = []
            continue

        if isinstance(value, list):
            limit = LLM_LIST_LIMITS.get(key, 10)
            sanitized[key] = [
                sanitize_row(item) for item in value[:limit] if isinstance(item, dict)
            ]
            continue

        sanitized[key] = sanitize_scalar(value)

    return sanitized


def _compact_context_json(context: dict) -> str:
    return json.dumps(
        context,
        ensure_ascii=False,
        default=_json_default,
        separators=(",", ":"),
    )


def _build_user_input(question: str, context: dict) -> str:
    context_json = _compact_context_json(context)
    return (
        f"使用者問題：{question.strip()}\n\n"
        f"市場脈絡（JSON）：\n{context_json}"
    )


def _log_api_exception(exc: Exception) -> None:
    print(f"[llm_service] {type(exc).__name__}: {exc}", flush=True)


def _extract_error_message(exc: Exception) -> str:
    message = getattr(exc, "message", None)
    if message:
        return str(message).strip()

    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error_body = body.get("error")
        if isinstance(error_body, dict):
            nested = error_body.get("message")
            if nested:
                return str(nested).strip()

    text = str(exc).strip()
    return text or type(exc).__name__


def _format_api_error(exc: Exception) -> str:
    _log_api_exception(exc)

    if isinstance(exc, AuthenticationError):
        return "OpenAI API key is invalid or missing. Please check .env."
    if isinstance(exc, RateLimitError):
        return "OpenAI API rate limit reached. Please wait and try again."
    if isinstance(exc, APIConnectionError):
        return "Cannot connect to OpenAI API. Please check internet connection."
    if isinstance(exc, BadRequestError):
        return f"OpenAI API bad request: {_extract_error_message(exc)}"
    if isinstance(exc, APIStatusError):
        status_code = getattr(exc, "status_code", "unknown")
        return f"OpenAI API error ({status_code}): {_extract_error_message(exc)}"
    if isinstance(exc, APIError):
        return f"OpenAI API error: {_extract_error_message(exc)}"
    return f"{type(exc).__name__}: {_extract_error_message(exc)}"


def answer_market_question(question: str, context: dict) -> str:
    question = (question or "").strip()
    if not question:
        return "請輸入問題後再進行分析。"

    api_key = _get_api_key()
    if not api_key:
        return MISSING_API_KEY_MESSAGE

    try:
        client = OpenAI(api_key=api_key)
        safe_context = sanitize_llm_context(context or {})
        response = client.responses.create(
            model=MODEL,
            instructions=SYSTEM_INSTRUCTION,
            input=_build_user_input(question, safe_context),
        )
        output_text = getattr(response, "output_text", None)
        if output_text:
            return output_text.strip()
        return "AI 服務未回傳有效內容，請稍後再試。"
    except AuthenticationError as exc:
        return _format_api_error(exc)
    except RateLimitError as exc:
        return _format_api_error(exc)
    except APIConnectionError as exc:
        return _format_api_error(exc)
    except BadRequestError as exc:
        return _format_api_error(exc)
    except APIStatusError as exc:
        return _format_api_error(exc)
    except APIError as exc:
        return _format_api_error(exc)
    except Exception as exc:
        return _format_api_error(exc)
