# Course Activity Dashboard + Data Analyst Agent

## 1. What the agent does

A Streamlit dashboard with one Gemini-powered agent. The dashboard shows:

- **Weekly Active Students (WAU)**: unique students with at least one `weekly_activity` row in the week.
- **Weekly Activity Rate**: active students / eligible students (signed up by the end of that week).
- **Average Learning Time per Active Student**: minutes watched per active student per week, with the median next to the mean.

Below the charts, you can type a question (for example, "Which country has the highest activation rate?").
The agent writes a read-only SQL query, runs it, and answers in plain words. The SQL it used is shown under the answer.

## 2. What data it uses

PostgreSQL database, read through `DATABASE_URL` (read-only, one SELECT per query, 20 s timeout).

| Table | Used for |
|---|---|
| `users` | signup week (eligible students) |
| `enrollments` | links activity rows to users |
| `weekly_activity` | active students and `minutes_watched` |
| `dim_course` | course names (used by the agent) |


## 3. How to run the project

1. Install Python 3 and the packages:
   ```
   python -m pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` and fill it in:
   ```
   GEMINI_API_KEY=your-key-here
   GEMINI_MODEL=gemini-3.1-flash-lite
   DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DBNAME?sslmode=require
   ```
3. Start the app from this folder:
   ```
   streamlit run app.py
   ```

Files: `app.py` (dashboard), `agent.py` (Gemini agent), `queries.py` (dashboard metrics), `db.py` (read-only database access).
