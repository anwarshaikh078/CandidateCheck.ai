import hashlib
from datetime import datetime
from typing import Iterable

import pandas as pd
import streamlit as st
from pydantic import ValidationError

from models.report_schema import REPORT_DISCLAIMER, CandidateReport, QuestionCategory
from services.ai_analyzer import (
    AnalyzerConfigurationError,
    AnalyzerResponseError,
    analyze_candidate,
)
from services.database import fetch_reports, init_db, save_report
from services.extract_text import ResumeExtractionError, extract_resume_links, extract_resume_text


APP_TITLE = "CandidateCheck AI"
PRODUCT_POSITIONING = "Candidate Submission Readiness Checker"
TARGET_ROLES = [
    "Data Engineer",
    "DevOps Engineer",
    "Cloud Engineer",
    "Cybersecurity Engineer",
    "Java Developer",
    "Python Developer",
    "QA Automation Engineer",
    "Salesforce Developer",
    "Data Analyst",
    "Business Analyst",
]


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, page_icon="CC", layout="wide")
    inject_styles()
    try:
        init_db()
    except Exception as exc:
        st.error(f"Local report storage could not be initialized: {exc}")
        return

    st.title(APP_TITLE)
    st.caption(PRODUCT_POSITIONING)

    analyze_tab, reports_tab, about_tab = st.tabs(
        ["Analyze Resume", "Past Reports", "About / Disclaimer"]
    )

    with analyze_tab:
        render_analyze_page()
    with reports_tab:
        render_past_reports_page()
    with about_tab:
        render_about_page()


def render_analyze_page() -> None:
    st.subheader("Analyze Candidate Submission Readiness")

    with st.form("analysis_form"):
        left, right = st.columns([0.95, 1.05])
        with left:
            candidate_name = st.text_input("Candidate name (optional)")
            target_role = st.selectbox("Target role", [""] + TARGET_ROLES, index=0)
            uploaded_file = st.file_uploader("Resume upload", type=["pdf", "docx"])
            job_description = st.text_area("Job description (optional)", height=130)
        with right:
            linkedin_text = st.text_area("LinkedIn/profile text (optional)", height=110)
            github_url = st.text_input("GitHub/portfolio URL (optional)")
            github_portfolio_summary = st.text_area(
                "GitHub/portfolio summary (optional)",
                height=90,
                help="Paste repo/project descriptions, portfolio notes, or profile summaries. The app does not scrape websites.",
            )
            recruiter_notes = st.text_area("Recruiter notes (optional)", height=90)

        submitted = st.form_submit_button("Analyze Candidate", type="primary")

    if not submitted:
        st.info("Upload a resume and choose a target role to generate a verification report.")
        return

    if not target_role:
        st.error("Please select a target role before analysis.")
        return
    if uploaded_file is None:
        st.error("Please upload a PDF or DOCX resume.")
        return

    try:
        resume_text = extract_resume_text(uploaded_file)
    except ResumeExtractionError as exc:
        st.error(str(exc))
        return

    extracted_links = extract_resume_links(uploaded_file)
    resume_meta = build_resume_metadata(uploaded_file.name, resume_text, extracted_links)

    if len(resume_text.split()) < 120:
        st.warning(
            "The extracted resume text is very short. Results may be less reliable; consider uploading a fuller text-based resume."
        )

    with st.expander("View extracted resume text"):
        st.text_area("Extracted text", resume_text, height=260, label_visibility="collapsed")

    try:
        with st.spinner("Analyzing candidate package and generating verification questions..."):
            report = analyze_candidate(
                resume_text=resume_text,
                target_role=target_role,
                candidate_name=candidate_name,
                job_description=job_description,
                linkedin_text=linkedin_text,
                github_url=github_url,
                github_portfolio_summary=github_portfolio_summary,
                recruiter_notes=recruiter_notes,
                extracted_links=extracted_links,
            )
            report_id = save_report(
                candidate_name=candidate_name,
                target_role=target_role,
                report=report,
            )
    except AnalyzerConfigurationError as exc:
        st.error(str(exc))
        st.code("Copy .env.example to .env, then set OPENAI_API_KEY=your_key")
        return
    except AnalyzerResponseError as exc:
        st.error(str(exc))
        return
    except Exception as exc:
        st.error(f"Analysis could not be completed: {exc}")
        return

    st.success(f"Report saved as ID {report_id}.")
    st.session_state["last_report"] = {
        "report": report,
        "candidate_name": candidate_name or "Unnamed candidate",
        "target_role": target_role,
        "resume_meta": resume_meta,
    }
    render_report(report, candidate_name or "Unnamed candidate", target_role, resume_meta)


def render_report(
    report: CandidateReport,
    candidate_name: str,
    target_role: str,
    resume_meta: dict | None = None,
) -> None:
    st.divider()
    st.subheader("Candidate Verification Report")
    st.caption(f"{candidate_name} - {target_role}")
    if resume_meta:
        render_resume_metadata(resume_meta)

    score_col, level_col, step_col = st.columns(3)
    step_col.metric("Submission Recommendation", report.recommendation.value)
    score_col.metric("Verification Priority Score", report.verification_priority_score)
    level_col.metric("Verification Priority Level", report.verification_priority_level.value)

    priority_col, risk_col, profile_col = st.columns(3)
    with priority_col:
        st.markdown("#### Top 3 Verification Priorities")
        render_bullet_list(report.top_3_verification_priorities[:3])
    with risk_col:
        st.markdown("#### Client Submission Risk")
        st.markdown(f"**{report.client_submission_risk.level.value}**")
        st.write(report.client_submission_risk.explanation)
    with profile_col:
        st.markdown("#### Profile Evidence Match")
        st.write(report.profile_evidence_match.external_evidence_summary)

    st.markdown("#### Questions to Ask")
    render_question_preview(report)

    st.markdown(f"**Summary**  \n{report.one_paragraph_summary}")

    claims_tab, fit_tab, profile_tab, questions_tab, brief_tab = st.tabs(
        ["Claim Evidence Table", "Role Fit Gaps", "Profile Evidence Match", "Recruiter Questions", "Client Brief"]
    )

    with claims_tab:
        render_claim_evidence_table(report)

    with fit_tab:
        render_role_fit_gaps(report)

    with profile_tab:
        render_profile_evidence_match(report)

    with questions_tab:
        render_questions(report)

    with brief_tab:
        st.markdown("#### Client Submission Brief")
        st.write(report.client_submission_brief)
        with st.expander("Claims To Validate"):
            render_bullet_list([claim.what_to_verify for claim in report.extracted_claims])

    st.info(report.disclaimer)


def render_questions(report: CandidateReport) -> None:
    questions = [question.model_dump(mode="json") for question in report.recruiter_questions]
    if not questions:
        st.warning("No verification questions were returned.")
        return

    categories = [category.value for category in QuestionCategory]
    question_tabs = st.tabs(categories)
    for tab, category in zip(question_tabs, categories):
        category_questions = [item for item in questions if item["category"] == category]
        with tab:
            if not category_questions:
                st.write("No questions returned for this category.")
                continue
            for index, item in enumerate(category_questions, start=1):
                st.markdown(f"**{index}. {item['question']}**")
                st.caption(f"Related claim: {item['related_claim']}")
                st.write(f"Why ask this: {item['why_ask_this']}")
                st.write(f"Good answer should include: {item['good_answer_should_include']}")
                st.write(f"Weak answer signals: {item['weak_answer_signals']}")


def render_question_preview(report: CandidateReport) -> None:
    for question in report.recruiter_questions[:4]:
        st.markdown(f"- **{question.category.value}:** {question.question}")


def render_claim_evidence_table(report: CandidateReport) -> None:
    if not report.extracted_claims:
        st.info("No extracted claims were returned.")
        return
    rows = [
        {
            "Claim Type": claim.claim_type,
            "Claim": claim.claim,
            "Evidence Strength": claim.evidence_strength.value,
            "Resume Evidence": claim.resume_evidence,
            "External/Profile Evidence": claim.external_evidence,
            "Why It Matters": claim.why_it_matters,
            "Recruiter Should Verify": claim.what_to_verify,
        }
        for claim in report.extracted_claims
    ]
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


def render_role_fit_gaps(report: CandidateReport) -> None:
    if not report.role_fit_gaps:
        st.success("No major role fit gaps were returned.")
        return
    for gap in report.role_fit_gaps:
        st.markdown(
            f"<span class='badge {gap.importance.value.lower()}'>{gap.importance.value}</span> "
            f"<strong>{gap.gap}</strong>",
            unsafe_allow_html=True,
        )
        st.write(gap.explanation)


def render_profile_evidence_match(report: CandidateReport) -> None:
    profile = report.profile_evidence_match
    top_left, top_right = st.columns(2)
    with top_left:
        st.markdown("#### Profile Assets Found")
        render_bullet_list(profile.profile_assets_found)
    with top_right:
        st.markdown("#### External Evidence Summary")
        st.write(profile.external_evidence_summary)

    supported_col, weak_col = st.columns(2)
    with supported_col:
        st.markdown("#### Supported Claims")
        render_bullet_list(profile.supported_claims)
    with weak_col:
        st.markdown("#### Unsupported or Weak Claims")
        render_bullet_list(profile.unsupported_or_weak_claims)

    with st.expander("Profile Gaps and Follow-Up"):
        st.markdown("##### Profile Gaps")
        render_bullet_list(profile.profile_gaps)
        st.markdown("##### Recruiter Follow-Up")
        render_bullet_list(profile.recruiter_follow_up)


def render_past_reports_page() -> None:
    st.subheader("Past Reports")
    reports = fetch_reports()
    if not reports:
        st.info("No reports saved yet. Analyze a resume to build your local report history.")
        return

    table_rows = [
        {
            "ID": report["id"],
            "Created": _format_timestamp(report["created_at"]),
            "Candidate": report["candidate_name"] or "Unnamed candidate",
            "Target Role": report["target_role"],
            "Score": report["risk_score"],
            "Level": report["risk_level"],
            "Next Step": report["recommended_next_step"],
        }
        for report in reports
    ]
    st.dataframe(pd.DataFrame(table_rows), hide_index=True, use_container_width=True)

    st.markdown("### Report Details")
    selected_id = st.selectbox("Select a report", [row["ID"] for row in table_rows])
    selected = next(report for report in reports if report["id"] == selected_id)
    try:
        report = CandidateReport.model_validate(selected["full_report"])
    except (TypeError, ValueError, ValidationError) as exc:
        st.error(f"Saved report {selected_id} could not be displayed because it no longer matches the report schema.")
        st.caption(str(exc))
        return
    render_report(
        report,
        selected["candidate_name"] or "Unnamed candidate",
        selected["target_role"],
    )


def render_about_page() -> None:
    st.subheader("About / Disclaimer")
    st.write(
        "CandidateCheck AI helps recruiters screen technical resumes for verification risk, "
        "missing evidence, possible inconsistencies, and practical follow-up questions before "
        "client submission."
    )
    st.write(
        "The product is designed for IT recruiters, staffing agencies, contract recruiters, "
        "and recruiters hiring remote technical candidates."
    )
    st.info(REPORT_DISCLAIMER)
    st.markdown(
        """
        **Responsible-use notes**

        - Use the report as a recruiter workflow aid.
        - Verify claims through candidate conversation, references, work samples, or approved client processes.
        - Do not use the score as the sole basis for hiring decisions.
        - Treat month/year date ranges as normal resume formatting.
        - Treat internships, co-ops, assistantships, research roles, and part-time work during school as plausible unless the resume contains a specific contradiction.
        - Keep candidate data in systems approved by your organization.
        """
    )


def render_bullet_list(items: Iterable[str]) -> None:
    items = list(items)
    if not items:
        st.write("No items provided.")
        return
    for item in items:
        st.markdown(f"- {item}")


def build_resume_metadata(filename: str, resume_text: str, extracted_links: list[str]) -> dict:
    cleaned_text = " ".join(resume_text.split())
    return {
        "filename": filename,
        "word_count": len(cleaned_text.split()),
        "fingerprint": hashlib.sha256(cleaned_text.encode("utf-8")).hexdigest()[:12],
        "preview": cleaned_text[:260],
        "links": extracted_links,
    }


def render_resume_metadata(resume_meta: dict) -> None:
    file_col, words_col, hash_col = st.columns([2, 1, 1])
    file_col.caption(f"Analyzed file: {resume_meta['filename']}")
    words_col.caption(f"Words: {resume_meta['word_count']}")
    hash_col.caption(f"Text ID: {resume_meta['fingerprint']}")
    links = resume_meta.get("links", [])
    if links:
        st.caption(f"Embedded links found: {len(links)}")
        with st.expander("Embedded resume links"):
            for link in links:
                st.markdown(f"- {link}")
    with st.expander("Resume text preview"):
        st.write(resume_meta["preview"] or "No preview available.")


def _format_timestamp(timestamp: str) -> str:
    try:
        value = datetime.fromisoformat(timestamp)
        return value.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return timestamp


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        .block-container {
            max-width: 1180px;
            padding-top: 2rem;
        }
        .badge {
            border-radius: 6px;
            color: #111827;
            display: inline-block;
            font-size: 0.78rem;
            font-weight: 700;
            margin-right: 0.45rem;
            padding: 0.12rem 0.42rem;
            text-transform: uppercase;
        }
        .badge.low {
            background: #d9f99d;
        }
        .badge.medium {
            background: #fde68a;
        }
        .badge.high {
            background: #fecaca;
        }
        div[data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            padding: 1rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
