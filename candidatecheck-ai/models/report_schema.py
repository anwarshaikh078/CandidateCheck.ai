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
    "sc" + "am",
    "liar",
    "dish" + "onest",
    "fabri" + "cated",
)

LANGUAGE_REPLACEMENTS = (
    ("fraud " + "confirmed", "verification concern"),
    ("fake " + "candidate", "candidate package needing verification"),
    ("definitely " + "ai-generated", "low-specificity writing"),
    ("definitely " + "ai generated", "low-specificity writing"),
    ("reject " + "because ai", "verify writing and experience claims before deciding"),
    ("reject this candidate " + "because of ai", "verify writing and experience claims before deciding"),
    ("sc" + "am", "verification concern"),
    ("liar", "candidate"),
    ("dish" + "onest", "unclear"),
    ("fabri" + "cated", "not supported by enough evidence"),
)


class PriorityLevel(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


class Recommendation(str, Enum):
    PROCEED = "Proceed"
    VERIFY_FIRST = "Verify first"
    HOLD_REJECT = "Hold/reject"


class EvidenceStrength(str, Enum):
    STRONG = "Strong"
    MEDIUM = "Medium"
    WEAK = "Weak"
    NOT_ENOUGH = "Not enough evidence"


class QuestionCategory(str, Enum):
    GENERAL = "General verification"
    ROLE_SPECIFIC = "Role-specific technical"
    RED_FLAG = "Resume red-flag follow-up"
    CLIENT_READINESS = "Client-submission readiness"
    PROFILE_EVIDENCE = "Profile evidence follow-up"


class ClientSubmissionRisk(BaseModel):
    level: PriorityLevel
    explanation: str = Field(..., min_length=1)


class ProfileEvidenceMatch(BaseModel):
    profile_assets_found: List[str] = Field(default_factory=list)
    external_evidence_summary: str = Field(..., min_length=1)
    supported_claims: List[str] = Field(default_factory=list)
    unsupported_or_weak_claims: List[str] = Field(default_factory=list)
    profile_gaps: List[str] = Field(default_factory=list)
    recruiter_follow_up: List[str] = Field(default_factory=list)


class ExtractedClaim(BaseModel):
    claim_type: str = Field(..., min_length=1)
    claim: str = Field(..., min_length=1)
    resume_evidence: str = Field(..., min_length=1)
    external_evidence: str = Field(..., min_length=1)
    evidence_strength: EvidenceStrength
    why_it_matters: str = Field(..., min_length=1)
    what_to_verify: str = Field(..., min_length=1)


class RoleFitGap(BaseModel):
    gap: str = Field(..., min_length=1)
    importance: PriorityLevel
    explanation: str = Field(..., min_length=1)


class RecruiterQuestion(BaseModel):
    category: QuestionCategory
    question: str = Field(..., min_length=1)
    why_ask_this: str = Field(..., min_length=1)
    related_claim: str = Field(..., min_length=1)
    good_answer_should_include: str = Field(..., min_length=1)
    weak_answer_signals: str = Field(..., min_length=1)


class CandidateReport(BaseModel):
    verification_priority_score: int = Field(..., ge=0, le=100)
    verification_priority_level: PriorityLevel
    recommendation: Recommendation
    one_paragraph_summary: str = Field(..., min_length=1)
    top_3_verification_priorities: List[str] = Field(default_factory=list)
    client_submission_risk: ClientSubmissionRisk
    profile_evidence_match: ProfileEvidenceMatch
    extracted_claims: List[ExtractedClaim] = Field(default_factory=list)
    role_fit_gaps: List[RoleFitGap] = Field(default_factory=list)
    recruiter_questions: List[RecruiterQuestion] = Field(default_factory=list)
    client_submission_brief: str = Field(..., min_length=1)
    disclaimer: str = REPORT_DISCLAIMER

    @model_validator(mode="before")
    @classmethod
    def sanitize_product_language(cls, data):
        return sanitize_report_language(data)

    @field_validator("verification_priority_score", mode="before")
    @classmethod
    def normalize_score(cls, score):
        if isinstance(score, float):
            return round(score)
        return score

    @field_validator("verification_priority_level")
    @classmethod
    def level_matches_score(cls, level: PriorityLevel, info):
        score = info.data.get("verification_priority_score")
        if score is None:
            return level
        return score_to_level(score)

    @field_validator("disclaimer")
    @classmethod
    def disclaimer_is_required_text(cls, disclaimer: str):
        return REPORT_DISCLAIMER

    @model_validator(mode="after")
    def normalize_and_check_report(self):
        self.verification_priority_level = score_to_level(self.verification_priority_score)
        self.disclaimer = REPORT_DISCLAIMER
        _reject_banned_language(self.model_dump(mode="json"))
        return self


def score_to_level(score: int) -> PriorityLevel:
    if score <= 30:
        return PriorityLevel.LOW
    if score <= 65:
        return PriorityLevel.MEDIUM
    return PriorityLevel.HIGH


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
