import os
import streamlit as st
from supabase import create_client
from datetime import datetime

st.set_page_config(
    page_title="Romania Job Monitor",
    page_icon="🇷🇴",
    layout="wide",
)

@st.cache_resource
def get_supabase():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = get_supabase()

# ── Header ────────────────────────────────────────────────────────────────────

st.title("🇷🇴 Romania Remote Job Monitor")
st.caption(f"Only remote/online positions · Updated automatically 4x/day")

# ── Sidebar filters ───────────────────────────────────────────────────────────

st.sidebar.header("Filters")

sources = ["All", "ejobs.ro", "bestjobs.ro", "hipo.ro", "remotive.com", "jobicy.com", "jobscollider.com"]
selected_source = st.sidebar.selectbox("Source", sources)

show_only_new = st.sidebar.checkbox("Show only new", value=True)

search_text = st.sidebar.text_input("Search in title", "")

# ── Load jobs ─────────────────────────────────────────────────────────────────

query = supabase.table("jobs").select("*").order("date_found", desc=True)

if selected_source != "All":
    query = query.eq("source", selected_source)
if show_only_new:
    query = query.eq("is_new", True)

result = query.limit(200).execute()
jobs = result.data or []

if search_text:
    jobs = [j for j in jobs if search_text.lower() in (j.get("title") or "").lower()]

# ── Stats ─────────────────────────────────────────────────────────────────────

total_result = supabase.table("jobs").select("id", count="exact").execute()
new_result = supabase.table("jobs").select("id", count="exact").eq("is_new", True).execute()

col1, col2, col3 = st.columns(3)
col1.metric("Total jobs found", total_result.count or 0)
col2.metric("New (unseen)", new_result.count or 0)
col3.metric("Showing now", len(jobs))

st.divider()

# ── Mark all as seen ─────────────────────────────────────────────────────────

if st.button("✅ Mark all as seen"):
    supabase.table("jobs").update({"is_new": False}).eq("is_new", True).execute()
    st.rerun()

# ── Job cards ─────────────────────────────────────────────────────────────────

if not jobs:
    st.info("No jobs found. Try changing filters or wait for the next scraper run.")
else:
    for job in jobs:
        is_new = job.get("is_new", False)
        title = job.get("title", "No title")
        company = job.get("company", "")
        location = job.get("location", "")
        source = job.get("source", "")
        url = job.get("url", "")
        description = job.get("description", "")
        date_found = job.get("date_found", "")
        date_posted = job.get("date_posted", "")

        # Format date
        try:
            dt = datetime.fromisoformat(date_found.replace("Z", "+00:00"))
            date_str = dt.strftime("%d %b %Y, %H:%M")
        except:
            date_str = date_found[:10] if date_found else ""

        badge = "🆕 " if is_new else ""

        with st.expander(f"{badge}{title} — {company}", expanded=is_new):
            col_a, col_b, col_c = st.columns([2, 2, 1])
            col_a.markdown(f"**Source:** {source}")
            col_b.markdown(f"**Found:** {date_str}")
            col_c.markdown(f"**Location:** {location or 'Remote'}")

            if description:
                st.markdown("**Description:**")
                st.markdown(description[:1500] + ("..." if len(description) > 1500 else ""))

            if url:
                st.markdown(f"[🔗 Open job posting]({url})")

            if is_new:
                if st.button("Mark as seen", key=f"seen_{job['id']}"):
                    supabase.table("jobs").update({"is_new": False}).eq("id", job["id"]).execute()
                    st.rerun()
