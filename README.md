# 📋 Resume Screener

An AI-powered resume screening API that ranks candidates against a job description. Upload multiple CVs as PDFs and get back a ranked list with scores, matching skills, missing skills, and hire/no-hire recommendations.

## Stack

| Layer | Tool |
|---|---|
| API Framework | FastAPI |
| LLM | Groq (Llama 3.3 70B) |
| Orchestration | LangChain |
| PDF Parsing | PyPDF |
| Validation | Pydantic v2 |
| UI | Streamlit |
| Testing | pytest |

## Features

- Upload multiple CVs in one request
- Extracts and parses text from PDF files automatically
- Scores each candidate from 0 to 100
- Lists matching and missing skills per candidate
- Gives a Hire / No Hire recommendation
- Returns candidates ranked by score
- Clean Streamlit UI for easy demo

## Demo

![Resume Screener UI](assets/Sample_Output.png)


## Project Structure

```
resume-screener/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI routes
│   ├── models.py        # Pydantic request/response models
│   ├── parser.py        # PDF text extraction
│   └── screener.py      # LLM screening logic
├── tests/
│   ├── __init__.py
│   └── test_screener.py # pytest test suite
├── streamlit_app.py     # Streamlit UI
├── requirements.txt
└── .gitignore
```

## Setup

**1. Clone the repo**
```bash
git clone https://github.com/sidd-24/resume-screener
cd resume-screener
```

**2. Create and activate virtual environment**
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate
```

**3. Install dependencies**
```bash
pip install -r requirements.txt
```

**4. Get a free Groq API key**

Sign up at [console.groq.com](https://console.groq.com) and create an API key.

## Running the app

**Start the API in terminal 1:**
```bash
uvicorn app.main:app --reload
```

**Start the Streamlit UI in terminal 2:**
```bash
streamlit run streamlit_app.py
```

Open `http://localhost:8501` in your browser.

## API Usage

### Screen candidates

```bash
curl -X POST http://localhost:8000/screen \
  -H "x-api-key: your_groq_api_key" \
  -F "job_title=Data Engineer" \
  -F "job_description=We need a Python developer with SQL and ETL experience." \
  -F "files=@candidate1.pdf" \
  -F "files=@candidate2.pdf"
```

**Response:**
```json
{
  "job_title": "Data Engineer",
  "total_candidates": 2,
  "ranked_candidates": [
    {
      "name": "John Doe",
      "score": 90,
      "matching_skills": ["Python", "SQL", "ETL pipelines"],
      "missing_skills": ["Apache Airflow"],
      "summary": "Strong candidate with 3 years of data engineering experience.",
      "recommendation": "Hire"
    },
    {
      "name": "Jane Smith",
      "score": 60,
      "matching_skills": ["Python"],
      "missing_skills": ["SQL", "ETL pipelines", "Apache Airflow"],
      "summary": "Junior candidate with Python skills but limited data engineering experience.",
      "recommendation": "No Hire"
    }
  ]
}
```

## Running Tests

```bash
pytest tests/ -v
```

All tests use mocking so no real API key is needed.