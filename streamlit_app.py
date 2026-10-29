import json
import os

import httpx
import pandas as pd
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")

MATCH_LEVEL_LABELS = {
    "strong_match": "🟢 Strong match",
    "partial_match": "🟡 Partial match",
    "weak_match": "🔴 Weak match",
    "manual_review_required": "⚠️ Manual review required",
}
STATUS_ICONS = {"met": "✅ Met", "partial": "🟡 Partial", "not_met": "❌ Not met"}
FLAG_EXPLANATIONS = {
    "unreadable_file": "The file could not be read as a PDF.",
    "no_extractable_text": "No text could be extracted; it may be a scanned image.",
    "possible_prompt_injection": "The CV contains text that tries to instruct the AI. Read it yourself.",
    "screening_failed": "The AI assessment failed for this CV.",
    "unverified_evidence": "Some AI claims had no matching quote in the CV and were downgraded.",
    "truncated": "The CV was very long; only the first part was assessed.",
}

st.set_page_config(page_title="Resume Screener under EU AI Act", page_icon="📋", layout="wide")

st.title("📋 Resume Screener under EU AI Act")
st.caption(
    "Decision support for recruiters: personal data is removed before the AI sees a CV, "
    "every match is backed by a quote from the CV, and every run is audit-logged."
)

with st.sidebar:
    st.header("⚙️ Configuration")
    api_key = st.text_input(
        "Groq API Key",
        type="password",
        value=os.getenv("GROQ_API_KEY", ""),
        placeholder="gsk_...",
        help="Get a free key at console.groq.com",
    )
    st.markdown("---")
    st.markdown("**How it works**")
    st.markdown(
        "1. Enter the job title and description\n"
        "2. Optionally define the requirements yourself\n"
        "3. Upload one or more CVs as PDFs\n"
        "4. Review the ranked shortlist and the evidence\n"
        "5. You make the decision, not the tool"
    )

st.subheader("Job Details")
col1, col2 = st.columns([1, 2])
with col1:
    job_title = st.text_input("Job Title", placeholder="e.g. Data Engineer")
with col2:
    job_description = st.text_area(
        "Job Description", placeholder="Paste the full job description here...", height=150
    )

with st.expander("Define requirements yourself (optional)"):
    st.caption("Leave empty to let the AI extract them from the job description. Separate items with commas.")
    must_have = st.text_input("Must-have", placeholder="e.g. Python, SQL, 2+ years data engineering")
    nice_to_have = st.text_input("Nice-to-have", placeholder="e.g. Airflow, Docker, German B2")

st.subheader("Upload CVs")
uploaded_files = st.file_uploader("Upload PDF CVs", type=["pdf"], accept_multiple_files=True)


def show_results(data: dict):
    st.warning(data["human_review_notice"], icon="👤")
    st.success(f"Screened {data['total_candidates']} candidate(s) for **{data['job_title']}**")

    source = "you" if data["requirements_source"] == "recruiter" else "the AI from the job description"
    st.markdown(f"**Requirements** (defined by {source})")
    st.markdown(
        "  \n".join(
            f"- {r['name']} — {'must-have' if r['priority'] == 'must_have' else 'nice-to-have'}"
            for r in data["requirements"]
        )
    )

    candidates = data["ranked_candidates"]
    overview = pd.DataFrame([
        {
            "Rank": i,
            "Candidate": c["candidate_id"],
            "File": c["filename"],
            "Score": c["score"],
            "Match": MATCH_LEVEL_LABELS[c["match_level"]],
            "Must-haves met": f"{c['must_haves_met']}/{c['must_haves_total']}",
            "Flags": ", ".join(c["flags"]),
        }
        for i, c in enumerate(candidates, start=1)
    ])
    st.subheader("Shortlist")
    st.dataframe(overview, hide_index=True, use_container_width=True)

    d1, d2 = st.columns(2)
    d1.download_button("⬇️ Download CSV", overview.to_csv(index=False), "screening_results.csv", "text/csv")
    d2.download_button("⬇️ Download JSON", json.dumps(data, indent=2), "screening_results.json", "application/json")

    st.subheader("Evidence per candidate")
    for i, c in enumerate(candidates, start=1):
        title = f"{i}. {c['candidate_id']} ({c['filename']}) — {c['score']}/100 — {MATCH_LEVEL_LABELS[c['match_level']]}"
        with st.expander(title, expanded=(i == 1)):
            for flag in c["flags"]:
                st.error(FLAG_EXPLANATIONS.get(flag, flag), icon="⚠️")

            if c["assessments"]:
                st.dataframe(
                    pd.DataFrame([
                        {
                            "Requirement": a["requirement"],
                            "Priority": "Must-have" if a["priority"] == "must_have" else "Nice-to-have",
                            "Status": STATUS_ICONS[a["status"]],
                            "Evidence from CV": a["evidence"],
                            "Quote verified": "✔" if a["evidence_verified"] else ("⚠" if a["evidence"] else ""),
                        }
                        for a in c["assessments"]
                    ]),
                    hide_index=True,
                    use_container_width=True,
                )

            st.markdown("**Summary**")
            st.info(c["summary"])

            if c["redactions"]:
                removed = ", ".join(f"{k.replace('_', ' ')} ({v})" for k, v in c["redactions"].items())
                st.caption(f"🔒 Removed before AI assessment: {removed}")

    st.caption(f"Audit reference: run `{data['run_id']}` · model `{data['model']}` · {data['created_at']}")


if st.button("🔍 Screen Candidates", type="primary"):
    if not api_key:
        st.error("Please enter your Groq API key in the sidebar.")
    elif not job_title or not job_description:
        st.error("Please enter the job title and description.")
    elif not uploaded_files:
        st.error("Please upload at least one CV.")
    else:
        with st.spinner(f"Screening {len(uploaded_files)} candidate(s)..."):
            files = [("files", (f.name, f.getvalue(), "application/pdf")) for f in uploaded_files]
            try:
                response = httpx.post(
                    f"{API_URL}/screen",
                    data={
                        "job_title": job_title,
                        "job_description": job_description,
                        "must_have": must_have,
                        "nice_to_have": nice_to_have,
                    },
                    files=files,
                    headers={"x-api-key": api_key},
                    timeout=300,
                )
            except httpx.HTTPError as e:
                st.error(f"Could not reach the API at {API_URL}: {e}")
            else:
                if response.status_code == 200:
                    st.session_state["results"] = response.json()
                else:
                    detail = response.json().get("detail", response.text) if response.content else response.text
                    st.error(f"Screening failed ({response.status_code}): {detail}")

if "results" in st.session_state:
    show_results(st.session_state["results"])
