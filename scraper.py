import os
import requests
from bs4 import BeautifulSoup
import feedparser
from supabase import create_client
from datetime import datetime
import time
import re

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ── Keywords ────────────────────────────────────────────────────────────────

IT_KEYWORDS = [
    "it support", "technical support", "helpdesk", "help desk", "service desk",
    "it mentenanță", "it mentenanta", "it administrator", "it technician",
    "system administrator", "desktop support", "automation specialist",
    "no-code", "make.com", "workflow automation", "crm administrator",
    "monday.com", "ai integration", "chatbot", "process automation",
    "it consultant", "suport tehnic", "administrator sistem", "asistenta tehnica",
]

INSURANCE_KEYWORDS = [
    "claims specialist", "claims handler", "claims adjuster", "loss adjuster",
    "damage assessment", "underwriting support", "insurance operations",
    "policy administrator", "insurance back office", "claims processing",
    "specialist dosare daune", "lichidator daune", "inspector daune",
    "asigurări back office", "asigurari back office", "daune", "dosare asigurare",
    "department daune", "specialist daune",
]

ALL_KEYWORDS = IT_KEYWORDS + INSURANCE_KEYWORDS

REMOTE_KEYWORDS = [
    "remote", "online", "work from home", "wfh", "de acasă", "de acasa",
    "la distanță", "la distanta", "telemuncă", "telemunca", "hybrid", "hibrid",
    "remote-first", "fully remote", "100% remote",
]

ENGLISH_ADVANCED_KEYWORDS = [
    "fluent english", "advanced english", "english c1", "english c2",
    "native english", "proficient english", "english mandatory",
    "limba engleza - avansat", "engleza avansata", "engleza fluenta",
]

INSURANCE_AGENT_EXCLUDE = [
    "agent de asigurare", "insurance agent", "sales agent", "agent vanzari",
    "agent comercial", "vanzare asigurari", "prospectare clienti",
    "portofoliu clienti", "comision vanzari",
]


# ── Filters ──────────────────────────────────────────────────────────────────

def is_remote(text: str) -> bool:
    text = text.lower()
    return any(kw in text for kw in REMOTE_KEYWORDS)

def is_relevant(title: str, description: str) -> bool:
    combined = (title + " " + description).lower()
    return any(kw in combined for kw in ALL_KEYWORDS)

def requires_advanced_english(text: str) -> bool:
    text = text.lower()
    return any(kw in text for kw in ENGLISH_ADVANCED_KEYWORDS)

def is_insurance_agent_role(title: str, description: str) -> bool:
    combined = (title + " " + description).lower()
    return any(kw in combined for kw in INSURANCE_AGENT_EXCLUDE)

def should_skip(title: str, description: str, location: str = "") -> bool:
    combined = (title + " " + description + " " + location).lower()
    if not is_remote(combined):
        return True
    if not is_relevant(title, description):
        return True
    if requires_advanced_english(combined):
        return True
    if is_insurance_agent_role(title, description):
        return True
    return False


# ── Save to Supabase ─────────────────────────────────────────────────────────

def save_job(title, company, location, description, url, source, date_posted=None):
    if not url:
        return
    existing = supabase.table("jobs").select("id").eq("url", url).execute()
    if existing.data:
        return  # already exists

    supabase.table("jobs").insert({
        "title": title[:500] if title else "",
        "company": company[:255] if company else "",
        "location": location[:255] if location else "",
        "description": description[:5000] if description else "",
        "url": url,
        "source": source,
        "date_posted": date_posted,
        "is_new": True,
        "is_remote": True,
        "is_relevant": True,
    }).execute()
    print(f"  ✓ Saved: {title[:60]}")


# ── RSS Sources ──────────────────────────────────────────────────────────────

def scrape_rss(feed_url: str, source_name: str):
    print(f"\n[{source_name}] Fetching RSS...")
    try:
        feed = feedparser.parse(feed_url)
        count = 0
        for entry in feed.entries:
            title = entry.get("title", "")
            description = entry.get("summary", "") or entry.get("description", "")
            url = entry.get("link", "")
            company = entry.get("author", "")
            location = ""

            # Extract location from tags if available
            tags = entry.get("tags", [])
            for tag in tags:
                if hasattr(tag, "term"):
                    location += tag.term + " "

            clean_desc = re.sub(r"<[^>]+>", " ", description)

            if should_skip(title, clean_desc, location):
                continue

            date_posted = entry.get("published", "")
            save_job(title, company, location.strip(), clean_desc[:5000], url, source_name, date_posted)
            count += 1

        print(f"  → {count} new relevant jobs found")
    except Exception as e:
        print(f"  ERROR: {e}")


def scrape_remotive():
    scrape_rss("https://remotive.com/feed", "remotive.com")

def scrape_jobicy():
    print("\n[jobicy.com] Fetching API...")
    try:
        searches = ["support", "automation", "crm", "helpdesk", "insurance"]
        count = 0
        seen_ids = set()
        for tag in searches:
            url = f"https://jobicy.com/api/v2/remote-jobs?count=50&tag={tag}"
            r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            data = r.json()
            jobs = data.get("jobs", [])
            for job in jobs:
                job_id = job.get("id")
                if job_id in seen_ids:
                    continue
                seen_ids.add(job_id)
                title = job.get("jobTitle", "")
                company = job.get("companyName", "")
                location = job.get("jobGeo", "Anywhere")
                description = re.sub(r"<[^>]+>", " ", job.get("jobDescription", ""))
                url_job = job.get("url", "")
                date_posted = job.get("pubDate", "")
                if should_skip(title, description, location):
                    continue
                save_job(title, company, location, description, url_job, "jobicy.com", date_posted)
                count += 1
            time.sleep(1)
        print(f"  → {count} new relevant jobs found")
    except Exception as e:
        print(f"  ERROR: {e}")

def scrape_jobscollider():
    scrape_rss("https://jobscollider.com/remote-jobs/feed", "jobscollider.com")


# ── ejobs.ro ─────────────────────────────────────────────────────────────────

def scrape_ejobs():
    print("\n[ejobs.ro] Fetching...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ro-RO,ro;q=0.9,en;q=0.8",
    }
    searches = [
        "it support", "technical support", "helpdesk",
        "automation", "daune asigurari", "it administrator", "crm",
    ]
    count = 0
    for query in searches:
        try:
            url = f"https://www.ejobs.ro/locuri-de-munca/remote/?search={requests.utils.quote(query)}"
            r = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(r.text, "html.parser")

            # Try multiple selector patterns
            jobs = (
                soup.select("div[class*='job-item']") or
                soup.select("article[class*='job']") or
                soup.select("li[class*='job']") or
                soup.select("div[class*='JobCard']") or
                soup.select("div[data-cy='job-card']") or
                soup.select("a[href*='/job/']")
            )

            print(f"  [{query}] found {len(jobs)} raw items")

            for job in jobs[:20]:
                title_el = (
                    job.select_one("h2 a") or job.select_one("h3 a") or
                    job.select_one("a[class*='title']") or job.select_one("a[class*='job-title']") or
                    (job if job.name == "a" else None)
                )
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                job_url = title_el.get("href", "")
                if job_url and not job_url.startswith("http"):
                    job_url = "https://www.ejobs.ro" + job_url
                company_el = job.select_one("[class*='company']") or job.select_one("[class*='employer']")
                company = company_el.get_text(strip=True) if company_el else ""
                location_el = job.select_one("[class*='location']") or job.select_one("[class*='city']")
                location = location_el.get_text(strip=True) if location_el else "Remote"
                desc_el = job.select_one("p") or job.select_one("[class*='description']")
                description = desc_el.get_text(strip=True) if desc_el else title

                if should_skip(title, description, location):
                    continue
                save_job(title, company, location, description, job_url, "ejobs.ro")
                count += 1
            time.sleep(2)
        except Exception as e:
            print(f"  ERROR [{query}]: {e}")
    print(f"  → {count} new relevant jobs saved")


# ── bestjobs.ro ───────────────────────────────────────────────────────────────

def scrape_bestjobs():
    print("\n[bestjobs.ro] Fetching...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ro-RO,ro;q=0.9",
    }
    searches = ["it-support", "technical-support", "helpdesk", "automation", "daune", "crm"]
    count = 0
    for query in searches:
        try:
            url = f"https://www.bestjobs.eu/ro/locuri-de-munca?remote=1&search_text={requests.utils.quote(query)}"
            r = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(r.text, "html.parser")

            jobs = (
                soup.select("div[class*='card']") or
                soup.select("article") or
                soup.select("li[class*='job']") or
                soup.select("div[class*='job']")
            )
            print(f"  [{query}] found {len(jobs)} raw items")

            for job in jobs[:20]:
                title_el = (
                    job.select_one("h2 a") or job.select_one("h3 a") or
                    job.select_one("a[class*='title']") or job.select_one("a[class*='job']")
                )
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                if len(title) < 3:
                    continue
                job_url = title_el.get("href", "")
                if job_url and not job_url.startswith("http"):
                    job_url = "https://www.bestjobs.eu" + job_url
                company_el = job.select_one("[class*='company']") or job.select_one("[class*='employer']")
                company = company_el.get_text(strip=True) if company_el else ""
                location_el = job.select_one("[class*='location']") or job.select_one("[class*='city']")
                location = location_el.get_text(strip=True) if location_el else "Remote"
                desc_el = job.select_one("p") or job.select_one("[class*='description']")
                description = desc_el.get_text(strip=True) if desc_el else title

                if should_skip(title, description, location):
                    continue
                save_job(title, company, location, description, job_url, "bestjobs.ro")
                count += 1
            time.sleep(2)
        except Exception as e:
            print(f"  ERROR [{query}]: {e}")
    print(f"  → {count} new relevant jobs saved")


# ── hipo.ro ───────────────────────────────────────────────────────────────────

def scrape_hipo():
    print("\n[hipo.ro] Fetching...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ro-RO,ro;q=0.9",
    }
    searches = ["it support", "technical support", "helpdesk", "automation", "daune"]
    count = 0
    for query in searches:
        try:
            url = f"https://www.hipo.ro/locuri-de-munca/cautare/{requests.utils.quote(query)}/?work_type=remote"
            r = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(r.text, "html.parser")

            jobs = (
                soup.select("div[class*='job']") or
                soup.select("article") or
                soup.select("li[class*='job']")
            )
            print(f"  [{query}] found {len(jobs)} raw items")

            for job in jobs[:20]:
                title_el = (
                    job.select_one("h2 a") or job.select_one("h3 a") or
                    job.select_one("a[class*='title']") or job.select_one("a[class*='name']")
                )
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                if len(title) < 3:
                    continue
                job_url = title_el.get("href", "")
                if job_url and not job_url.startswith("http"):
                    job_url = "https://www.hipo.ro" + job_url
                company_el = job.select_one("[class*='company']") or job.select_one("[class*='employer']")
                company = company_el.get_text(strip=True) if company_el else ""
                location_el = job.select_one("[class*='location']") or job.select_one("[class*='city']")
                location = location_el.get_text(strip=True) if location_el else "Remote"
                desc_el = job.select_one("p") or job.select_one("[class*='description']")
                description = desc_el.get_text(strip=True) if desc_el else title

                if should_skip(title, description, location):
                    continue
                save_job(title, company, location, description, job_url, "hipo.ro")
                count += 1
            time.sleep(2)
        except Exception as e:
            print(f"  ERROR [{query}]: {e}")
    print(f"  → {count} new relevant jobs saved")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"=== Job Monitor started at {datetime.now().strftime('%Y-%m-%d %H:%M')} ===")
    scrape_remotive()
    scrape_jobicy()
    scrape_jobscollider()
    scrape_ejobs()
    scrape_bestjobs()
    scrape_hipo()
    print("\n=== Done ===")