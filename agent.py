"""The one agent: Gemini writes read-only SQL, reads the result, and answers in plain words."""
import os
import time
from functools import cache

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

from db import run_select

load_dotenv()

# Short schema + the same metric definitions as the dashboard, so answers match the charts.
SYSTEM_PROMPT = """You are a data analyst for an online-course platform. Answer questions about
student activity using the run_sql tool (PostgreSQL, read-only).

How to work, for every request:
1. Understand the question and pick the matching definition below. If it is unclear, state the assumption you made.
2. Get the data: write aggregated SQL with run_sql. Never guess numbers: query them.
3. Analyse: check that the numbers make sense (group sizes, partial periods, odd values) before you answer.
4. Answer in plain words for a non-technical reader: the key numbers first, then one or two sentences on what they
   mean, then any caveat that changes how the numbers should be read. Keep it short.

Tables (schema public):
- users(user_id, signup_date date, country, plan, persona, age_band, device_primary)
- enrollments(enrollment_id, user_id, course_id, course_url, specialization_id, course_no,
  enrolled_at TEXT, completed_at TEXT, last_week_reached, n_weeks, progress_pct, funnel_state, is_certified)
- weekly_activity(enrollment_id, week_number, active_date date, minutes_watched, quiz_attempts, quiz_score)
- payments(payment_id, user_id, paid_at date, amount_usd, plan, is_refunded)
- dim_course(course_id, course, n_weeks, total_minutes, partner, level, domain, review_score, ...)
- reviews(review_id, course_url, review_date TEXT, review_content, stars); review_link(enrollment_id, review_id)
Joins: users.user_id = enrollments.user_id; enrollments.enrollment_id = weekly_activity.enrollment_id;
enrollments.course_id = dim_course.course_id.

Definitions (use exactly these):
- Activation rate = users with at least one weekly_activity row / all users.
- Completed enrollment = is_certified = 1.
- Funnel states, in order: registered, viewed, explored, certified.
- Retention = share of a signup-month cohort with weekly_activity in month N after signup.
- Week = calendar week, Monday start: date_trunc('week', weekly_activity.active_date). (week_number is the course week, not a calendar week.)
- Weekly active students (WAU) = count(distinct enrollments.user_id) with a weekly_activity row in that calendar week
  (weekly_activity has no user_id: join enrollments).
- Weekly activity rate = WAU / eligible students, where eligible = users with signup_date on or before the end of that week.
- Learning time per active student = first sum minutes_watched per student per calendar week (ignore minutes_watched < 0),
  then average it over the active students of that week. Also give the median (percentile_cont(0.5)), because a few very
  active students pull the average up.

Rates and joins: users -> enrollments -> weekly_activity is one-to-many, so joined rows repeat each user. Never divide by
count(*) of a joined table. Build the list of active users once (distinct), then left join it to users. A share can never
exceed 100%: if it does, the SQL double counts, so fix it before answering. Do not use a correlated EXISTS per user: it
times out. Pattern for a rate by group (fast, about 1 second):
  with active as (select distinct e.user_id from weekly_activity w join enrollments e using (enrollment_id))
  select <group>, count(*) as users, count(a.user_id) as active_users,
         round(100.0 * count(a.user_id) / count(*), 1) as activation_pct
  from users u left join active a using (user_id) group by 1

Cautions:
- minutes_watched = -1 means unknown (169 rows): exclude it from sums. 692 rows have 0 minutes; 94 rows are above 600 minutes.
- users.country has aliases and NULLs. ALWAYS select and group by this expression instead of the raw column:
  case when country = 'USA' then 'United States' when country = 'DE' then 'Germany' when country = 'UK' then 'United Kingdom'
  else coalesce(country, 'Unknown') end
  Report the group size next to any rate by group, and ignore groups under 100 users when ranking.
- enrolled_at is text in two formats ('2022-06-08' and '01.01.2022', day first). Avoid it unless needed.
- progress_pct can exceed 100 (exactly 104.0 in 277 rows); cap it with least(progress_pct, 100) when averaging.
- completed_at is NULL unless certified (356 non-certified rows still have a date, 375 are before enrolled_at): do not rely on it.
- Signups run 2021-01 to 2023-02-25 (February 2023 is a partial month). Activity ends 2023-05-05, so the last week and
  anything after March 2023 is thin: do not call it a drop in engagement.
- This data looks synthetic; do not present findings as real business facts.
- Prefer aggregated queries (count, avg, group by). Results are cut at 200 rows; queries that scan large tables twice may time out.
If a query fails, read the error, fix the SQL and try again."""


@cache
def get_client(api_key: str) -> genai.Client:
    """Create the Gemini client once and reuse it. The SDK closes a client's connection when the
    object is garbage-collected, which caused "client has been closed" when a new one was made per question."""
    return genai.Client(api_key=api_key)


def ask(question: str) -> tuple[str, list[str]]:
    """Return (answer, list of SQL queries the agent ran)."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing. Add it to the .env file.")
    model = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")

    queries: list[str] = []

    def run_sql(sql: str) -> str:
        """Run one read-only SELECT on the course database and return the rows as CSV (max 200 rows)."""
        queries.append(sql)
        try:
            return run_select(sql).to_csv(index=False)
        except Exception as error:  # hand the error back so the model can fix its query
            return f"ERROR: {error}"

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        temperature=0,  # same question -> same SQL and numbers
        tools=[run_sql],  # the SDK calls this function for the model automatically
        automatic_function_calling=types.AutomaticFunctionCallingConfig(maximum_remote_calls=6),
    )
    for attempt in range(4):
        queries.clear()  # a retry starts over, so do not list SQL from the failed attempt
        try:
            response = get_client(api_key).models.generate_content(model=model, contents=question, config=config)
            break
        except errors.APIError as error:
            # 429/500/503 are usually temporary ("model is overloaded"), so wait a little and try again.
            if error.code not in (429, 500, 503) or attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))
    return response.text or "The agent ran out of steps before it could answer. Try a narrower question.", queries
