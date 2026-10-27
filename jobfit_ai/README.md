# JobFit AI

A local Flask app that compares resume text with a job description. Python calculates a transparent keyword-overlap score; Gemini can add tailored feedback and interview-practice questions. Analyses are stored in a local SQLite database.

## Requirements

- Python 3.10 or newer
- A Gemini API key for AI-generated feedback (optional; keyword matching still works without it)

## Run on Windows

1. Extract the project folder and open it in VS Code.
2. Open a terminal inside the `jobfit_ai` folder.
3. Create a virtual environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

4. Install dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

5. Copy `.env.example` to `.env` and add your Gemini API key. Keep `.env` private. If you do not add a key, local matching still works.
6. Start the app:

   ```powershell
   python app.py
   ```

7. Open `http://127.0.0.1:5000` in your browser.

## Notes

- The app runs on your own computer. It is a portfolio prototype, not a production service.
- Use demo text or remove personal contact details before testing.
- The score measures text overlap for detected terms. It is not an ATS score, hiring probability, or guarantee of interview selection.
- Gemini feedback sends the resume and job-description text to the configured Gemini API. Do not submit sensitive information unless you are comfortable with that processing.
