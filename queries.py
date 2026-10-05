"""The dashboard metrics. Definitions live here, in one place."""
import pandas as pd

from db import run_select


def weekly_metrics() -> pd.DataFrame:
    """One row per calendar week (Monday start): WAU, activity rate, avg and median learning minutes.

    Active student = at least one weekly_activity row in that week.
    Eligible student = signed up on or before the end of that week (a student cannot be active before signing up).
    """
    # Minutes per student per week. -1 is a placeholder for "unknown" (169 rows), so it is ignored in the sum.
    active = run_select("""
        select date_trunc('week', w.active_date)::date as week, e.user_id,
               sum(w.minutes_watched) filter (where w.minutes_watched >= 0) as minutes
        from weekly_activity w join enrollments e using (enrollment_id)
        group by 1, 2
    """, max_rows=200000)
    active["minutes"] = active["minutes"].astype(float).fillna(0)

    per_week = active.groupby("week")["minutes"].agg(wau="size", avg_minutes="mean", median_minutes="median")

    # Eligible students = cumulative signups up to the end of each week.
    signups = run_select("""
        select date_trunc('week', signup_date)::date as week, count(*) as n
        from users group by 1 order by 1
    """, max_rows=1000)
    eligible = signups.set_index("week")["n"].cumsum()
    eligible = eligible.reindex(per_week.index.union(eligible.index)).ffill()

    df = per_week.join(eligible.rename("eligible"))
    df["rate"] = df["wau"] / df["eligible"]

    # The last week of data stops part-way (data ends on a Friday), so it would look like a false drop.
    last_date = run_select("select max(active_date) as d from weekly_activity").loc[0, "d"]
    if pd.Timestamp(last_date).dayofweek != 6:
        df = df.iloc[:-1]
    df.index = pd.to_datetime(df.index)
    return df.reset_index()
