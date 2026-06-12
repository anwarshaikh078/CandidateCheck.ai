from enum import Enum
from typing import Any, List

from pydantic import BaseModel, Field, field_validator, model_validator


REPORT_DISCLAIMER = (
    "This report supports human review and should not be used as the sole basis "
    "for hiring decisions."
)

BANNED_LANGUAGE = (
    "fraud " + "confirmed",
    "fake " + "candidate",
    "definitely " + "ai-generated",
    "definitely " + "ai generated",
    "reject " + "because ai",
    "reject this candidate " + "because of ai",
    "scam",
    "liar",
    "dishonest",
)

LANGUAGE_REPLACEMENTS = (
    ("fraud " + "confirmed", "verification concern"),
    ("fake " + "candidate", "candidate package needing verification"),
    ("definitely " + "ai-generated", "low-specificity writing"),
    ("definitely " + "ai generated", "low-specificity writing"),
    ("reject " + "because ai", "verify writing and experience claims before deciding"),
    ("reject this candidate " + "because of ai", "verify writing and experience claims before deciding"),
    ("scam", "verification concern"),
    ("liar", "candidate"),
    ("dishonest", "unclear"),
)


class RiskLevel(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


class RecommendedNextStep(str, Enum):
    PROCEED = "Proceed"
    VERIFY_FIRST = "Verify first"
    HOLD_REJECT = "Hold/reject"


class QuestionCategory(str, Enum):
    GENERAL = "General verification"
    ROLE_SPECIFIC = "Role-specific technical"
    RED_FLAG = "Resume red-flag follow-up"
    CLIENT_READINESS = "Client-submission readiness"


class RedFlag(BaseModel):
    title: str = Field(..., min_length=1)
    severity: RiskLevel
    explanation: str = Field(..., min_length=1)


class VerificationQuestion(BaseModel):
    category: QuestionCategory
    question: str = Field(..., min_length=1)
    purpose: str = Field(..., min_length=1)
    related_signal: str = Field(..., min_length=1)
    expected_good_answer: str = Field(..., min_length=1)


class CandidateReport(BaseModel):
    risk_score: int = Field(..., ge=0, le=100)
    risk_level: RiskLevel
    recommended_next_step: RecommendedNextStep
    summary: str = Field(..., min_length=1)
    profile_assets_found: List[str] = Field(default_factory=list)
    candidate_evidence_snapshot: List[str] = Field(default_factory=list)
    key_claims_to_validate: List[str] = Field(default_factory=list)
    client_submission_brief: List[str] = Field(default_factory=list)
    top_recruiter_actions: List[str] = Field(default_factory=list)
    red_flags: List[RedFlag] = Field(default_factory=list)
    missing_information: List[str] = Field(default_factory=list)
    resume_quality_signals: List[str] = Field(default_factory=list)
    ai_generic_writing_signals: List[str] = Field(default_factory=list)
    timeline_consistency: str = Field(..., min_length=1)
    skills_credibility: str = Field(..., min_length=1)
    linkedin_consistency: str = Field(..., min_length=1)
    verification_questions: List[VerificationQuestion] = Field(default_factory=list)
    disclaimer: str = REPORT_DISCLAIMER

    @model_validator(mode="before")
    @classmethod
    def sanitize_product_language(cls, data):
        return sanitize_report_language(data)

    @field_validator("risk_score", mode="before")
    @classmethod
    def normalize_risk_score(cls, risk_score):
        if isinstance(risk_score, float):
            return round(risk_score)
        return risk_score

    @field_validator("risk_level")
    @classmethod
    def risk_level_matches_score(cls, risk_level: RiskLevel, info):
        score = info.data.get("risk_score")
        if score is None:
            return risk_level
        return score_to_level(score)

    @field_validator("disclaimer")
    @classmethod
    def disclaimer_is_required_text(cls, disclaimer: str):
        return REPORT_DISCLAIMER

    @model_validator(mode="after")
    def normalize_and_check_report(self):
        self.risk_level = score_to_level(self.risk_score)
        self.disclaimer = REPORT_DISCLAIMER
        _reject_banned_language(self.model_dump(mode="json"))
        return self


def score_to_level(score: int) -> RiskLevel:
    if score <= 30:
        return RiskLevel.LOW
    if score <= 65:
        return RiskLevel.MEDIUM
    return RiskLevel.HIGH


def _reject_banned_language(value: Any) -> None:
    if isinstance(value, str):
        normalized = value.lower()
        for phrase in BANNED_LANGUAGE:
            if phrase in normalized:
                raise ValueError("report contains product language that must not be displayed")
        return
    if isinstance(value, list):
        for item in value:
            _reject_banned_language(item)
        return
    if isinstance(value, dict):
        for item in value.values():
            _reject_banned_language(item)


def sanitize_report_language(value: Any) -> Any:
    if isinstance(value, str):
        sanitized = value
        for phrase, replacement in LANGUAGE_REPLACEMENTS:
            sanitized = _replace_case_insensitive(sanitized, phrase, replacement)
        return sanitized
    if isinstance(value, list):
        return [sanitize_report_language(item) for item in value]
    if isinstance(value, dict):
        return {key: sanitize_report_language(item) for key, item in value.items()}
    return value


def _replace_case_insensitive(value: str, needle: str, replacement: str) -> str:
    lower_value = value.lower()
    lower_needle = needle.lower()
    start = lower_value.find(lower_needle)
    while start != -1:
        end = start + len(needle)
        value = value[:start] + replacement + value[end:]
        lower_value = value.lower()
        start = lower_value.find(lower_needle, start + len(replacement))
    return value
