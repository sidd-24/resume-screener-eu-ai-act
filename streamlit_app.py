import streamlit as st
import httpx

API_URL = "http://localhost:8000"

st.set_page_config(
    page_title="Resume Screener",
    page_icon="📋",
    layout="wide",
)

st.title("📋 Resume Screener")
st.caption("Upload a job description and multiple CVs to get ranked candidates.")

with st.sidebar:
    st.header("⚙️ Configuration")
    api_key = st.text_input(
        "Groq API Key",
        type="password",
        placeholder="gsk_...",
        help="Get a free key at console.groq.com",
    )
    st.markdown("---")
    st.markdown("**How it works**")
    st.markdown(
        "1. Enter the job title and description\n"
        "2. Upload one or more CVs as PDFs\n"
        "3. Click Screen Candidates\n"
        "4. Get ranked results with scores"
    )

st.subheader("Job Details")
col1, col2 = st.columns([1, 2])

with col1:
    job_title = st.text_input("Job Title", placeholder="e.g. Data Engineer")

with col2:
    job_description = st.text_area(
        "Job Description",
        placeholder="Paste the full job description here...",
        height=150,
    )

st.subheader("Upload CVs")
uploaded_files = st.file_uploader(
    "Upload PDF CVs",
    type=["pdf"],
    accept_multiple_files=True,
)

if st.button("🔍 Screen Candidates", type="primary"):
    if not api_key:
        st.error("Please enter your Groq API key in the sidebar.")
    elif not job_title or not job_description:
        st.error("Please enter the job title and description.")
    elif not uploaded_files:
        st.error("Please upload at least one CV.")
    else:
        with st.spinner(f"Screening {len(uploaded_files)} candidate(s)..."):
            files = [
                ("files", (f.name, f.read(), "application/pdf"))
                for f in uploaded_files
            ]
            try:
                response = httpx.post(
                    f"{API_URL}/screen",
                    data={
                        "job_title": job_title,
                        "job_description": job_description,
                    },
                    files=files,
                    headers={"x-api-key": api_key},
                    timeout=120,
                )
                response.raise_for_status()
                data = response.json()

                st.success(f"Screened {data['total_candidates']} candidate(s) for **{data['job_title']}**")
                st.markdown("---")
                st.subheader("Ranked Candidates")

                for i, candidate in enumerate(data["ranked_candidates"]):
                    rank = i + 1
                    score = candidate["score"]

                    if score >= 75:
                        color = "🟢"
                    elif score >= 50:
                        color = "🟡"
                    else:
                        color = "🔴"

                    with st.expander(
                        f"{rank}. {color} {candidate['name']} — Score: {score}/100 — {candidate['recommendation']}",
                        expanded=(rank == 1),
                    ):
                        col1, col2 = st.columns(2)
                        with col1:
                            st.markdown("**Matching Skills**")
                            for skill in candidate["matching_skills"]:
                                st.markdown(f"✅ {skill}")
                        with col2:
                            st.markdown("**Missing Skills**")
                            for skill in candidate["missing_skills"]:
                                st.markdown(f"❌ {skill}")

                        st.markdown("**Summary**")
                        st.info(candidate["summary"])

            except Exception as e:
                st.error(f"Something went wrong: {str(e)}")