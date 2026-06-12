# CandidateCheck AI

CandidateCheck AI is a Streamlit MVP for technical resume verification support. It helps recruiters identify verification risk, missing information, weak technical proof, timeline issues, profile inconsistencies, and specific validation questions before moving a candidate forward.

This app is intentionally not a production SaaS. It uses local SQLite storage and a single Streamlit interface.

## Features

- Upload PDF or DOCX resumes.
- Enter target role, profile text, portfolio URL, and recruiter notes.
- Extract resume text with PyMuPDF or python-docx.
- Analyze candidate materials with the OpenAI API.
- Validate structured JSON reports with Pydantic.
- Save reports locally in SQLite.
- Review past reports inside the app.
- Generate recruiter-ready verification questions grouped by category.

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
