"""Streamlit dashboard: weekly active students, weekly activity rate, learning time, and a question box for the agent."""
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import queries
from agent import ask

st.set_page_config(page_title="User Activity", layout="wide")
st.title("User Activity")

# The query is slow-ish and the data never changes while the app runs, so cache it.
weekly = st.cache_data(ttl=3600)(queries.weekly_metrics)
w = weekly()


def weekly_line(columns: dict[str, str], y_title: str, percent: bool = False) -> go.Figure:
    """One line per column over the weeks. `columns` maps column name -> legend label."""
    fig = px.line(w, x="week", y=list(columns), labels={"week": "Week (Monday)", "value": y_title, "variable": ""})
    fig.for_each_trace(lambda t: t.update(name=columns[t.name]))
    if percent:
        fig.update_yaxes(tickformat=".1%")
    return fig


# 1. Weekly Active Students (WAU)
st.header("Weekly Active Students (WAU)")
peak = w.loc[w["wau"].idxmax()]
c1, c2 = st.columns(2)
c1.metric("Average per week", f"{w['wau'].mean():,.0f}")
c2.metric("Peak week", f"{int(peak['wau']):,}", f"week of {peak['week']:%d/%m/%Y}", delta_color="off")
st.plotly_chart(weekly_line({"wau": "Active students"}, "Students"), width="stretch")
st.caption("Unique students with at least one weekly_activity row in the week. Answers: How many students are active?")

# 2. Weekly Activity Rate
st.header("Weekly Activity Rate")
peak = w.loc[w["rate"].idxmax()]
c1, c2 = st.columns(2)
c1.metric("Average per week", f"{w['rate'].mean():.1%}")
c2.metric("Peak week", f"{peak['rate']:.1%}", f"week of {peak['week']:%d/%m/%Y}", delta_color="off")
st.plotly_chart(weekly_line({"rate": "Activity rate"}, "Active / eligible", percent=True), width="stretch")
st.caption(
    "Active students / eligible students. Eligible = signed up on or before the end of that week. "
    "Answers: How broadly students are engaged?"
)

# 3. Average Learning Time per Active Student
st.header("Average Learning Time per Active Student")
c1, c2 = st.columns(2)
c1.metric("Average (mean) minutes per week", f"{w['avg_minutes'].mean():,.0f}")
c2.metric("Median minutes per week", f"{w['median_minutes'].mean():,.0f}")
st.plotly_chart(weekly_line({"avg_minutes": "Average", "median_minutes": "Median"}, "Minutes watched"), width="stretch")
st.caption(
    "Minutes watched per active student per week. The median is shown too, because a few very active students pull the average up. "
    "Answers: How deeply they engage?"
)

# 4. Ask the agent
st.header("Ask the agent")
question = st.text_input("Your question", placeholder="Which country has the highest activation rate?")
if st.button("Ask") and question.strip():
    with st.spinner("Thinking..."):
        try:
            answer, sql_used = ask(question)
            st.subheader("Answer")
            st.write(answer)
            with st.expander("SQL the agent ran"):
                for q in sql_used:
                    st.code(q, language="sql")
        except Exception as error:
            st.error(f"The agent could not answer: {error}")
