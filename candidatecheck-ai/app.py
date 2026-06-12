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
from services.extract_text import ResumeExtractionError, extract_resume_text


APP_TITLE = "CandidateCheck AI"
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
    st.caption("Technical resume screening for verification risk and recruiter follow-up.")

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
    st.subheader("Analyze Resume")

    with st.form("analysis_form"):
        left, right = st.columns([0.95, 1.05])
        with left:
            candidate_name = st.text_input("Candidate name (optional)")
            target_role = st.selectbox("Target role", [""] + TARGET_ROLES, index=0)
            uploaded_file = st.file_uploader("Resume upload", type=["pdf", "docx"])
        with right:
            linkedin_text = st.text_area("LinkedIn/profile text (optional)", height=110)
            github_url = st.text_input("GitHub/portfolio URL (optional)")
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

    resume_meta = build_resume_metadata(uploaded_file.name, resume_text)

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
                linkedin_text=linkedin_text,
                github_url=github_url,
                recruiter_notes=recruiter_notes,
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
    score_col.metric("Verification Priority Score", report.risk_score)
    level_col.metric("Verification Priority Level", report.risk_level.value)
    step_col.metric("Recommended Next Step", report.recommended_next_step.value)

    st.markdown(f"**Summary**  \n{report.summary}")

    overview_tab, questions_tab, signals_tab, details_tab = st.tabs(
        ["Actions", "Questions", "Signals", "Details"]
    )

    with overview_tab:
        st.markdown("#### Top Recruiter Actions")
        render_bullet_list(report.top_recruiter_actions)

    with questions_tab:
        render_questions(report)

    with signals_tab:
        st.markdown("#### Risk Signals")
        if report.red_flags:
            for flag in report.red_flags:
                st.markdown(
                    f"<span class='badge {flag.severity.value.lower()}'>{flag.severity.value}</span> "
                    f"<strong>{flag.title}</strong>",
                    unsafe_allow_html=True,
                )
                st.write(flag.explanation)
        else:
            st.write("No major risk signals were identified.")

        signal_col, quality_col, writing_col = st.columns(3)
        with signal_col:
            st.markdown("#### Missing Information")
            render_bullet_list(report.missing_information)
        with quality_col:
            st.markdown("#### Resume Quality")
            render_bullet_list(report.resume_quality_signals)
        with writing_col:
            st.markdown("#### Writing Specificity")
            render_bullet_list(report.ai_generic_writing_signals)

    with details_tab:
        detail_col_1, detail_col_2, detail_col_3 = st.columns(3)
        with detail_col_1:
            st.markdown("#### Timeline")
            st.write(report.timeline_consistency)
        with detail_col_2:
            st.markdown("#### Skills")
            st.write(report.skills_credibility)
        with detail_col_3:
            st.markdown("#### Profile")
            st.write(report.linkedin_consistency)

    st.info(report.disclaimer)


def render_questions(report: CandidateReport) -> None:
    questions = [question.model_dump(mode="json") for question in report.verification_questions]
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
                st.caption(f"Related signal: {item['related_signal']}")
                st.write(f"Purpose: {item['purpose']}")
                st.write(f"Expected good answer: {item['expected_good_answer']}")


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


def build_resume_metadata(filename: str, resume_text: str) -> dict:
    cleaned_text = " ".join(resume_text.split())
    return {
        "filename": filename,
        "word_count": len(cleaned_text.split()),
        "fingerprint": hashlib.sha256(cleaned_text.encode("utf-8")).hexdigest()[:12],
        "preview": cleaned_text[:260],
    }


def render_resume_metadata(resume_meta: dict) -> None:
    file_col, words_col, hash_col = st.columns([2, 1, 1])
    file_col.caption(f"Analyzed file: {resume_meta['filename']}")
    words_col.caption(f"Words: {resume_meta['word_count']}")
    hash_col.caption(f"Text ID: {resume_meta['fingerprint']}")
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
