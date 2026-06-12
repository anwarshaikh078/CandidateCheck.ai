# CandidateCheck AI

CandidateCheck AI is a Streamlit MVP for evidence-based candidate submission readiness. It helps recruiters identify which resume claims are supported, which claims need verification, how profile assets relate to resume claims, and what questions to ask before client submission.

This app is intentionally not a production SaaS. It uses local SQLite storage and a single Streamlit interface.

## Features

- Upload PDF or DOCX resumes.
- Enter target role, optional job description, profile text, portfolio URL/summary, and recruiter notes.
- Extract resume text with PyMuPDF or python-docx.
- Extract embedded PDF/DOCX hyperlinks such as LinkedIn, GitHub, and portfolio URLs.
- Analyze candidate materials with the OpenAI API.
- Validate structured JSON reports with Pydantic.
- Save reports locally in SQLite.
- Review past reports inside the app.
- Generate claim evidence tables, profile evidence match, role fit gaps, client submission brief, and recruiter-ready verification questions grouped by category.

## Setup

Use Python 3.11 or newer.

```bash
cd candidatecheck-ai
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env`:

```bash
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o-mini
```

## Run

```bash
streamlit run app.py
```

The app will create a local SQLite database at `data/candidatecheck.db`.

## Product Disclaimer

This report supports human review and should not be used as the sole basis for hiring decisions.

CandidateCheck AI does not make definitive claims about a candidate. Recruiters should use the report to guide follow-up questions, verification steps, and client-submission readiness checks.

## Future Roadmap

- User authentication and workspace separation.
- Exportable PDF reports.
- Role-specific prompt packs.
- Team review notes.
- ATS integrations.
- Bulk analysis workflows.
- Audit logs and retention controls.
