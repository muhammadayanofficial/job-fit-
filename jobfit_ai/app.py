import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv
from flask import Flask, render_template, request, url_for

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "local-jobfit-development-key")
DATABASE_PATH = BASE_DIR / "jobfit.db"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()

SKILL_TERMS = [
    "Python", "JavaScript", "TypeScript", "Java", "C++", "C#", "PHP", "Ruby", "Go",
    "Rust", "SQL", "PostgreSQL", "MySQL", "SQLite", "MongoDB", "Redis", "HTML", "CSS",
    "React", "Next.js", "Vue", "Angular", "Node.js", "Express", "Flask", "Django", "FastAPI",
    "REST API", "GraphQL", "Git", "GitHub", "Docker", "Kubernetes", "AWS", "Azure", "GCP",
    "Linux", "CI/CD", "Machine Learning", "Deep Learning", "Natural Language Processing",
    "Data Analysis", "Data Visualization", "Power BI", "Tableau", "Excel", "Pandas", "NumPy",
    "scikit-learn", "TensorFlow", "PyTorch", "Generative AI", "Prompt Engineering", "LLM",
    "Communication", "Leadership", "Problem Solving", "Project Management", "Agile", "Scrum",
    "Customer Support", "Sales", "Marketing", "SEO", "Content Writing", "Figma", "UI/UX",
    "Research", "Testing", "Automation", "Accounting", "Financial Analysis", "Negotiation",
]

STOP_WORDS = {
    "about", "above", "after", "again", "against", "also", "among", "and", "any", "are",
    "around", "because", "been", "before", "being", "below", "between", "both", "but", "can",
    "candidate", "could", "each", "either", "else", "ensure", "every", "experience", "from",
    "further", "have", "having", "into", "its", "job", "join", "least", "like", "looking",
    "make", "many", "more", "most", "must", "need", "needed", "our", "other", "please", "role",
    "same", "should", "since", "such", "team", "than", "that", "their", "them", "then", "there",
    "these", "they", "this", "those", "through", "under", "using", "very", "want", "well", "were",
    "what", "when", "where", "which", "while", "will", "with", "within", "would", "you", "your",
    "the", "for", "from", "are", "was", "who", "has", "had", "not", "all", "per", "etc", "able",
    "work", "working", "years", "year", "strong", "excellent", "good", "ability", "skills", "skill",
}


@contextmanager
def get_connection():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database():
    with get_connection() as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_title TEXT NOT NULL,
                company TEXT NOT NULL DEFAULT '',
                score INTEGER NOT NULL,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )


def contains_term(text, term):
    pattern = r"(?<!\w)" + re.escape(term) + r"(?!\w)"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def extract_keywords(text, limit=14):
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9+#.-]{2,}", text.lower())
    counts = {}
    for word in words:
        cleaned = word.strip(".-")
        if len(cleaned) < 3 or cleaned in STOP_WORDS or cleaned.isdigit():
            continue
        counts[cleaned] = counts.get(cleaned, 0) + 1
    return [word for word, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]]


def calculate_match(resume_text, job_description):
    required_skills = [term for term in SKILL_TERMS if contains_term(job_description, term)]

    if required_skills:
        matched = [term for term in required_skills if contains_term(resume_text, term)]
        missing = [term for term in required_skills if term not in matched]
        score = round((len(matched) / len(required_skills)) * 100) if required_skills else 0
        return score, matched, missing, required_skills

    job_words = extract_keywords(job_description, limit=12)
    resume_words = set(extract_keywords(resume_text, limit=300))
    matched = [word for word in job_words if word in resume_words]
    missing = [word for word in job_words if word not in resume_words]
    score = round((len(matched) / len(job_words)) * 100) if job_words else 0
    return score, matched, missing, job_words


def fallback_recommendations(score, matched, missing, job_title):
    if matched:
        strengths = [
            "Your resume already includes relevant terms: " + ", ".join(matched[:5]) + ".",
            "Keep the most relevant experience near the top so the hiring manager sees it quickly.",
        ]
    else:
        strengths = [
            "Your resume gives the matcher a starting point, but few explicit job-related terms were found.",
            "Use specific examples from real projects, employment, coursework, or volunteering.",
        ]

    improvements = [
        "Add measurable outcomes where you can support them, such as time saved, revenue influenced, or work completed.",
        "Use the job description's terminology only where it accurately describes your experience.",
        "Move the most relevant project or role above less relevant experience.",
    ]
    if missing:
        improvements.insert(0, "Address these relevant terms where truthful: " + ", ".join(missing[:6]) + ".")

    if score >= 75:
        summary = f"Your resume shows a strong keyword overlap for {job_title or 'this role'}. Improve the evidence behind your strongest matches before applying."
    elif score >= 45:
        summary = f"Your resume has a partial match for {job_title or 'this role'}. A few targeted edits could make relevant experience easier to recognize."
    else:
        summary = f"The current keyword overlap for {job_title or 'this role'} is limited. Check whether the role is a fit, then tailor your resume using only skills and experience you can substantiate."

    return {
        "summary": summary,
        "strengths": strengths,
        "improvements": improvements,
        "interview_questions": [
            "Which project best demonstrates your most relevant skill, and what was the outcome?",
            "Tell me about a challenge you faced that is similar to this role's responsibilities.",
            "What would you want to learn or improve in your first 90 days?",
        ],
    }


def get_gemini_recommendations(resume_text, job_description, job_title, company, matched, missing, score):
    if not GEMINI_API_KEY:
        return None, "Local keyword analysis is ready. Add GEMINI_API_KEY to your .env file for tailored AI feedback."

    prompt = f"""You are a practical career coach. Compare this resume against the job description.
Return only valid JSON with this exact structure:
{{
  "summary": "2-3 clear sentences, honest and specific",
  "strengths": ["3 short points"],
  "improvements": ["4 specific actions; never invent experience or credentials"],
  "interview_questions": ["3 relevant questions"]
}}
Rules: do not claim to predict ATS results or hiring outcomes; do not fabricate experience; phrase missing skills as gaps to address only if the candidate genuinely has them. Be direct and avoid generic praise.
Job title: {job_title or 'Not specified'}
Company: {company or 'Not specified'}
Calculated keyword overlap score: {score}%
Matched terms: {', '.join(matched) if matched else 'None identified'}
Missing terms: {', '.join(missing) if missing else 'None identified'}
RESUME:
{resume_text[:12000]}
JOB DESCRIPTION:
{job_description[:12000]}
"""

    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    try:
        response = requests.post(
            endpoint,
            params={"key": GEMINI_API_KEY},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json", "temperature": 0.35},
            },
            timeout=35,
        )
        response.raise_for_status()
        payload = response.json()
        generated_text = payload["candidates"][0]["content"]["parts"][0]["text"]
        data = json.loads(generated_text)
        for key in ("summary", "strengths", "improvements", "interview_questions"):
            if key not in data:
                raise ValueError(f"Missing field: {key}")
        data["strengths"] = [str(item) for item in data["strengths"][:5]]
        data["improvements"] = [str(item) for item in data["improvements"][:6]]
        data["interview_questions"] = [str(item) for item in data["interview_questions"][:5]]
        data["summary"] = str(data["summary"])
        return data, "AI feedback generated with Gemini."
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as error:
        app.logger.warning("Gemini recommendation request failed: %s", error)
        return None, "Gemini feedback could not be loaded, so local matching results are shown instead. Check your API key and model setting."


def read_recent_analyses(limit=6):
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT id, job_title, company, score, created_at FROM analyses ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def save_analysis(job_title, company, result):
    created_at = datetime.now().strftime("%d %b %Y, %I:%M %p")
    with get_connection() as connection:
        cursor = connection.execute(
            "INSERT INTO analyses (job_title, company, score, result_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (job_title, company, result["score"], json.dumps(result), created_at),
        )
        return cursor.lastrowid, created_at


@app.route("/", methods=["GET", "POST"])
def index():
    result = None
    form_data = {"job_title": "", "company": "", "resume_text": "", "job_description": ""}
    error_message = None

    if request.method == "POST":
        form_data = {key: request.form.get(key, "").strip() for key in form_data}
        resume_text = form_data["resume_text"]
        job_description = form_data["job_description"]

        if len(resume_text) < 80 or len(job_description) < 80:
            error_message = "Paste a fuller resume and job description (at least 80 characters each) for a useful comparison."
        elif len(resume_text) > 20000 or len(job_description) > 20000:
            error_message = "Please keep each text field under 20,000 characters."
        else:
            score, matched, missing, required = calculate_match(resume_text, job_description)
            recommendations, ai_note = get_gemini_recommendations(
                resume_text,
                job_description,
                form_data["job_title"],
                form_data["company"],
                matched,
                missing,
                score,
            )
            if recommendations is None:
                recommendations = fallback_recommendations(score, matched, missing, form_data["job_title"])

            result = {
                "job_title": form_data["job_title"] or "Target role",
                "company": form_data["company"],
                "score": score,
                "matched_skills": matched,
                "missing_skills": missing,
                "required_count": len(required),
                "matched_count": len(matched),
                "missing_count": len(missing),
                "summary": recommendations["summary"],
                "strengths": recommendations["strengths"],
                "improvements": recommendations["improvements"],
                "interview_questions": recommendations["interview_questions"],
                "ai_enabled": recommendations is not None and "AI feedback generated" in ai_note,
                "ai_note": ai_note,
            }
            analysis_id, created_at = save_analysis(form_data["job_title"] or "Target role", form_data["company"], result)
            result["id"] = analysis_id
            result["created_at"] = created_at

    return render_template(
        "index.html",
        result=result,
        form_data=form_data,
        error_message=error_message,
        recent_analyses=read_recent_analyses(),
    )


@app.route("/analysis/<int:analysis_id>")
def view_analysis(analysis_id):
    with get_connection() as connection:
        row = connection.execute(
            "SELECT id, result_json, created_at FROM analyses WHERE id = ?", (analysis_id,)
        ).fetchone()
    if row is None:
        return render_template(
            "index.html",
            result=None,
            form_data={"job_title": "", "company": "", "resume_text": "", "job_description": ""},
            error_message="That saved analysis could not be found.",
            recent_analyses=read_recent_analyses(),
        ), 404

    result = json.loads(row["result_json"])
    result["id"] = row["id"]
    result["created_at"] = row["created_at"]
    return render_template(
        "index.html",
        result=result,
        form_data={"job_title": result.get("job_title", ""), "company": result.get("company", ""), "resume_text": "", "job_description": ""},
        error_message=None,
        recent_analyses=read_recent_analyses(),
        viewing_saved=True,
    )


initialize_database()

if __name__ == "__main__":
    app.run(debug=True)
