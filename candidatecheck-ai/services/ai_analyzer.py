import json
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import ValidationError

from models.report_schema import CandidateReport


BASE_DIR = Path(__file__).resolve().parents[1]
PROMPT_PATH = BASE_DIR / "prompts" / "candidate_risk_prompt.txt"
DEFAULT_MODEL = "gpt-4o-mini"


class AnalyzerConfigurationError(Exception):
    """Raised when OpenAI analysis is not configured."""


class AnalyzerResponseError(Exception):
    """Raised when the AI response is missing, invalid JSON, or fails validation."""


def analyze_candidate(
    *,
    resume_text: str,
    target_role: str,
    candidate_name: Optional[str] = None,
    linkedin_text: Optional[str] = None,
    github_url: Optional[str] = None,
    recruiter_notes: Optional[str] = None,
) -> CandidateReport:
    load_dotenv(BASE_DIR / ".env")
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise AnalyzerConfigurationError(
            "OpenAI is not configured. Add OPENAI_API_KEY to your .env file and restart Streamlit."
        )

    prompt = _load_prompt()
    try:
        from openai import OpenAI
    except Exception as exc:
        raise AnalyzerConfigurationError(
            "The OpenAI Python package could not be imported. Reinstall dependencies with pip install -r requirements.txt."
        ) from exc

    client = OpenAI(api_key=api_key, timeout=60)
    model = (os.getenv("OPENAI_MODEL") or DEFAULT_MODEL).strip()

    user_payload = {
        "candidate_name": candidate_name or "",
        "target_role": target_role,
        "linkedin_or_profile_text": linkedin_text or "",
        "github_or_portfolio_url": github_url or "",
        "recruiter_notes": recruiter_notes or "",
        "resume_text": resume_text,
    }

    try:
        response = client.chat.completions.create(
            model=model,
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": (
                        "Analyze this candidate package and return the required JSON only.\n\n"
                        + json.dumps(user_payload, ensure_ascii=False)
                    ),
                },
            ],
        )
    except Exception as exc:
        raise AnalyzerResponseError(f"OpenAI analysis failed: {exc}") from exc

    raw_content = ""
    if response.choices and response.choices[0].message:
        raw_content = response.choices[0].message.content or ""
    if not raw_content:
        raise AnalyzerResponseError("OpenAI returned an empty response.")

    return parse_and_validate_report(raw_content)


def parse_and_validate_report(raw_content: str) -> CandidateReport:
    try:
        parsed = json.loads(_strip_json_markdown(raw_content))
    except json.JSONDecodeError as exc:
        raise AnalyzerResponseError("OpenAI returned JSON that could not be parsed.") from exc

    try:
        return CandidateReport.model_validate(parsed)
    except ValidationError as exc:
        raise AnalyzerResponseError(f"OpenAI returned JSON that did not match the report schema: {exc}") from exc


def _load_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise AnalyzerConfigurationError("The analysis prompt file is missing.") from exc


def _strip_json_markdown(raw_content: str) -> str:
    content = raw_content.strip()
    if content.startswith("```"):
        lines = content.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        content = "\n".join(lines).strip()

    if not content.startswith("{"):
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1 and end > start:
            content = content[start : end + 1]

    return content
