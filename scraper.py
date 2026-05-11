import os
import requests
from bs4 import BeautifulSoup
import feedparser
from supabase import create_client
from datetime import datetime
import time
import re
import unicodedata
import json

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

def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.lower()
    # Normalize Romanian diacritics so "acasă" matches "acasa"
    return "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))

def is_remote(text: str) -> bool:
    normalized = normalize_text(text)
    return any(normalize_text(kw) in normalized for kw in REMOTE_KEYWORDS)

def is_relevant(title: str, description: str) -> bool:
    combined = (title + " " + description).lower()
    return any(kw in combined for kw in ALL_KEYWORDS)

def requires_advanced_english(text: str) -> bool:
    text = text.lower()
    return any(kw in text for kw in ENGLISH_ADVANCED_KEYWORDS)

def is_insurance_agent_role(title: str, description: str) -> bool:
    combined = (title + " " + description).lower()
    return any(kw in combined for kw in INSURANCE_AGENT_EXCLUDE)

def should_skip(title: str, description: str, location: str = "", force_remote: bool = False) -> bool:
    combined = (title + " " + description + " " + location).lower()
    if not force_remote and not is_remote(combined):
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

def scrape_rss(feed_url: str, source_name: str, force_remote: bool = False):
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

            if should_skip(title, clean_desc, location, force_remote=force_remote):
                continue

            date_posted = entry.get("published", "")
            save_job(title, company, location.strip(), clean_desc[:5000], url, source_name, date_posted)
            count += 1

        print(f"  → {count} new relevant jobs found")
    except Exception as e:
        print(f"  ERROR: {e}")


def scrape_remotive():
    scrape_rss("https://remotive.com/feed", "remotive.com", force_remote=True)

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
                if should_skip(title, description, location, force_remote=True):
                    continue
                save_job(title, company, location, description, url_job, "jobicy.com", date_posted)
                count += 1
            time.sleep(1)
        print(f"  → {count} new relevant jobs found")
    except Exception as e:
        print(f"  ERROR: {e}")

def scrape_jobscollider():
    scrape_rss("https://jobscollider.com/remote-jobs/feed", "jobscollider.com", force_remote=True)


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
    skip_stats = {"not_remote": 0, "not_relevant": 0, "advanced_english": 0, "agent_role": 0, "other": 0}
    for query in searches:
        try:
            url = f"https://www.ejobs.ro/locuri-de-munca/remote/?search={requests.utils.quote(query)}"
            r = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(r.text, "html.parser")
            jobs = []
            for script in soup.select("script[type='application/ld+json']"):
                raw = (script.string or script.get_text() or "").strip()
                if not raw:
                    continue
                try:
                    payload = json.loads(raw)
                except Exception:
                    continue

                items = payload if isinstance(payload, list) else [payload]
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    elements = item.get("itemListElement", [])
                    if not isinstance(elements, list):
                        continue
                    for el in elements:
                        if not isinstance(el, dict):
                            continue
                        sub = el.get("item", {}) if isinstance(el.get("item", {}), dict) else {}
                        title = sub.get("name", "") or el.get("name", "")
                        job_url = sub.get("id", "") or el.get("url", "")
                        if title and job_url and "ejobs.ro/user/locuri-de-munca/" in job_url:
                            jobs.append({"title": title, "url": job_url})

            # Fallback: extract from inline JSON-like blocks if ld+json didn't include list items
            if not jobs:
                pattern = r'"name":"(.*?)","id":"(https:\\/\\/www\.ejobs\.ro\\/user\\/locuri-de-munca\\/[^"]+)"'
                for match in re.finditer(pattern, r.text):
                    raw_title = match.group(1)
                    raw_url = match.group(2)
                    try:
                        title = json.loads(f"\"{raw_title}\"")
                    except Exception:
                        title = raw_title
                    job_url = raw_url.replace("\\/", "/")
                    if title and job_url:
                        jobs.append({"title": title, "url": job_url})

            unique = {}
            for j in jobs:
                unique[j["url"]] = j
            jobs = list(unique.values())
            print(f"  [{query}] found {len(jobs)} json-ld jobs")

            for job in jobs:
                title = job["title"].strip()
                job_url = job["url"].strip()
                if not title or not job_url:
                    continue
                location = "Remote"
                description = title
                combined = (title + " " + description + " " + location).lower()
                if not is_remote(combined):
                    skip_stats["not_remote"] += 1
                    continue
                if not is_relevant(title, description):
                    skip_stats["not_relevant"] += 1
                    continue
                if requires_advanced_english(combined):
                    skip_stats["advanced_english"] += 1
                    continue
                if is_insurance_agent_role(title, description):
                    skip_stats["agent_role"] += 1
                    continue
                save_job(title, "", location, description, job_url, "ejobs.ro")
                count += 1
            time.sleep(2)
        except Exception as e:
            print(f"  ERROR [{query}]: {e}")
    print(f"  → {count} new relevant jobs saved")
    print(f"  skip stats: {skip_stats}")


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
            links = soup.select("a[href*='/ro/locuri-de-munca/']")
            print(f"  [{query}] found {len(links)} candidate links")

            for link in links:
                title = link.get_text(strip=True)
                if len(title) < 3:
                    continue
                job_url = link.get("href", "")
                if job_url and not job_url.startswith("http"):
                    job_url = "https://www.bestjobs.eu" + job_url
                company = ""
                location = "Remote"
                description = title

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
            links = soup.select("a[href*='/locuri-de-munca/']")
            print(f"  [{query}] found {len(links)} candidate links")

            for link in links:
                title = link.get_text(strip=True)
                if len(title) < 3:
                    continue
                job_url = link.get("href", "")
                if job_url and not job_url.startswith("http"):
                    job_url = "https://www.hipo.ro" + job_url
                company = ""
                location = "Remote"
                description = title

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
