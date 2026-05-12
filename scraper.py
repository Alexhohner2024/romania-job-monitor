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
import gspread
try:
    import google.generativeai as genai
    _genai_available = True
except ImportError:
    _genai_available = False

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", "").strip()
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
STRICT_GEO_FILTER = os.environ.get("STRICT_GEO_FILTER", "0").strip().lower() in {"1", "true", "yes"}

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

# Exclude vacancies requiring non-English languages (Dutch, German, etc.).
FOREIGN_LANGUAGE_EXCLUDE = [
    " with dutch", "dutch ", "limba olandeza", "olandeza",
    " with german", "german ", "limba germana", "germana",
    " with french", "french ", "limba franceza", "franceza",
    " with italian", "italian ", "limba italiana", "italiana",
    " with spanish", "spanish ", "limba spaniola", "spaniola",
    " with portuguese", "portuguese ", "limba portugheza", "portugheza",
    " with hungarian", "hungarian ", "limba maghiara", "maghiara",
    " with polish", "polish ", "limba poloneza", "poloneza",
    " with czech", "czech ", "limba ceha", "ceha",
    " with slovak", "slovak ", "limba slovaca", "slovaca",
    " with turkish", "turkish ", "limba turca", "turca",
]

INSURANCE_AGENT_EXCLUDE = [
    "agent de asigurare", "insurance agent", "sales agent", "agent vanzari",
    "agent comercial", "vanzare asigurari", "prospectare clienti",
    "portofoliu clienti", "comision vanzari",
]

SHEET_HEADERS = [
    "date_found",
    "source",
    "title",
    "company",
    "location",
    "salary",
    "short_description_ru",
    "url",
]


def extract_salary_value(text: str) -> str:
    """Extract salary from text, supporting $50k, €3000, RON 5000, ranges, etc."""
    if not text:
        return ""

    # Detect currency symbol/word
    currency = ""
    if "$" in text or re.search(r"\bUSD\b", text, re.I):
        currency = "USD"
    elif "€" in text or re.search(r"\bEUR\b", text, re.I):
        currency = "EUR"
    elif re.search(r"\bRON\b|\bLEI\b", text, re.I):
        currency = "RON"
    elif "£" in text or re.search(r"\bGBP\b", text, re.I):
        currency = "GBP"

    # Strip currency symbols and normalize separators
    clean = re.sub(r"[$€£]", "", text)
    clean = clean.replace(",", "").replace("\u00a0", "").replace("\u202f", "")

    # Expand k/K suffix: 50k → 50000
    def expand_k(m):
        val = float(m.group(1))
        return str(int(val * 1000))
    clean = re.sub(r"(\d+(?:\.\d+)?)[kK]\b", expand_k, clean)

    # Range: 2900 - 6000
    m_range = re.search(r"\b(\d{3,6})\s*[-–]\s*(\d{3,6})\b", clean)
    if m_range:
        result = f"{m_range.group(1)}-{m_range.group(2)}"
        return f"{result} {currency}".strip() if currency else result

    # Single value: 4500
    m_single = re.search(r"\b(\d{3,6})\b", clean)
    if m_single:
        result = m_single.group(1)
        return f"{result} {currency}".strip() if currency else result

    return ""


def build_short_description_ru(title: str, location: str, salary: str) -> str:
    """Generate a short Russian job description using Gemini API, with template fallback."""
    loc = location or "Remote"
    salary_part = salary if salary else "не указана"
    fallback = f"💼 {title}. 🌍 Локация: {loc}. 💰 Зарплата: {salary_part}."

    if not GEMINI_API_KEY or not _genai_available:
        return fallback

    model_candidates = [
        "gemini-2.0-flash",
        "gemini-1.5-flash",
        "gemini-1.5-flash-latest",
    ]

    try:
        genai.configure(api_key=GEMINI_API_KEY)
        prompt = (
            f"Переведи название вакансии на русский язык и напиши одно короткое предложение "
            f"(до 80 символов), описывающее эту работу на русском языке. "
            f"Вакансия: '{title}'. Локация: '{loc}'. Зарплата: '{salary_part}'.\n"
            f"Ответь строго в одну строку в формате (без лишних слов, без переносов):\n"
            f"💼 <название на русском>. <1 предложение о работе>. 🌍 Локация: {loc}. 💰 Зарплата: {salary_part}."
        )

        for model_name in model_candidates:
            try:
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(prompt)
                result = (response.text or "").strip()
                if result and len(result) > 10:
                    print(f"  🔤 Translated ({model_name}): {result[:90]}")
                    return result
            except Exception as model_error:
                print(f"  WARN [gemini:{model_name}]: {model_error}")
                continue
    except Exception as e:
        print(f"  WARN [gemini]: {e}")

    return fallback


class GoogleSheetWriter:
    def __init__(self):
        self.enabled = bool(GOOGLE_SHEET_ID and GOOGLE_SERVICE_ACCOUNT_JSON)
        self.worksheet = None
        self.existing_urls = set()
        self.initialized = False

    def init(self):
        if self.initialized or not self.enabled:
            return
        creds = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
        client = gspread.service_account_from_dict(creds)
        sh = client.open_by_key(GOOGLE_SHEET_ID)
        self.worksheet = sh.sheet1

        values = self.worksheet.get_all_values()
        if not values:
            self.worksheet.append_row(SHEET_HEADERS, value_input_option="USER_ENTERED")
        elif values[0] != SHEET_HEADERS:
            # Existing data without headers: insert header row at top.
            self.worksheet.insert_row(SHEET_HEADERS, index=1, value_input_option="USER_ENTERED")
            values = self.worksheet.get_all_values()

        url_col_idx = 8  # 1-based index of "url" in SHEET_HEADERS
        for row in values[1:]:
            if len(row) >= url_col_idx and row[url_col_idx - 1]:
                self.existing_urls.add(row[url_col_idx - 1].strip())
        self.initialized = True

    def append_if_new(self, job: dict):
        if not self.enabled:
            return
        self.init()
        url = (job.get("url") or "").strip()
        if not url or url in self.existing_urls:
            if not url:
                print("  ℹ️  Skip Google Sheet: empty url")
            else:
                print(f"  ℹ️  Skip Google Sheet (duplicate url): {url[:100]}")
            return
        row = [
            job.get("date_found", ""),
            job.get("source", ""),
            job.get("title", ""),
            job.get("company", ""),
            job.get("location", ""),
            job.get("salary", ""),
            job.get("short_description_ru", ""),
            url,
        ]
        self.worksheet.append_row(row, value_input_option="USER_ENTERED")
        self.existing_urls.add(url)
        print(f"  📄 Added to Google Sheet: {job.get('title', '')[:60]}")


sheet_writer = GoogleSheetWriter()


def extract_text_snippet(html: str, max_len: int = 1200) -> str:
    if not html:
        return ""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len]


def fetch_ejobs_job_details(job_url: str, headers: dict) -> tuple[str, str]:
    """Return (description_snippet, location) from eJobs job page."""
    try:
        r = requests.get(job_url, headers=headers, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")

        description = ""
        location = "Remote"

        # Prefer JobPosting schema if available.
        for script in soup.select("script[type='application/ld+json']"):
            raw = (script.string or script.get_text() or "").strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except Exception:
                continue

            candidates = payload if isinstance(payload, list) else [payload]
            for node in candidates:
                if not isinstance(node, dict):
                    continue
                if node.get("@type") == "JobPosting":
                    desc_html = node.get("description", "")
                    if desc_html:
                        description = extract_text_snippet(desc_html)

                    job_loc = node.get("jobLocation", {})
                    if isinstance(job_loc, list) and job_loc:
                        job_loc = job_loc[0]
                    if isinstance(job_loc, dict):
                        address = job_loc.get("address", {})
                        if isinstance(address, dict):
                            location = (
                                address.get("addressLocality", "")
                                or address.get("addressRegion", "")
                                or address.get("addressCountry", "")
                                or location
                            )
                    if description:
                        return description, location

        # Fallback: meta description snippet.
        if not description:
            meta_desc = soup.select_one("meta[name='description']")
            if meta_desc:
                description = extract_text_snippet(meta_desc.get("content", ""))

        return description, location
    except Exception as e:
        print(f"  WARN [ejobs-detail]: {e}")
        return "", "Remote"


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


# Locations allowed for global (force_remote) sources
_ALLOWED_GEO = {"worldwide", "anywhere", "global", "remote", "romania", "international", "eu", "europe"}

def is_geo_allowed(location: str) -> bool:
    """For global sources: allow only Romania, worldwide/anywhere, or unspecified location."""
    if not location or not location.strip():
        return True
    loc = normalize_text(location)
    if "romania" in loc:
        return True
    return any(term in loc for term in _ALLOWED_GEO)

def is_relevant(title: str, description: str) -> bool:
    combined = (title + " " + description).lower()
    return any(kw in combined for kw in ALL_KEYWORDS)

def requires_advanced_english(text: str) -> bool:
    text = text.lower()
    return any(kw in text for kw in ENGLISH_ADVANCED_KEYWORDS)

def is_insurance_agent_role(title: str, description: str) -> bool:
    combined = (title + " " + description).lower()
    return any(kw in combined for kw in INSURANCE_AGENT_EXCLUDE)


def requires_foreign_language(title: str, description: str) -> bool:
    combined = f" {title} {description} ".lower()
    return any(kw in combined for kw in FOREIGN_LANGUAGE_EXCLUDE)

def should_skip(title: str, description: str, location: str = "", force_remote: bool = False) -> bool:
    combined = (title + " " + description + " " + location).lower()
    if not force_remote and not is_remote(combined):
        return True
    # For global sources (force_remote=True), only allow Romania / worldwide / anywhere
    if force_remote and STRICT_GEO_FILTER and not is_geo_allowed(location):
        return True
    if not is_relevant(title, description):
        return True
    if requires_advanced_english(combined):
        return True
    if requires_foreign_language(title, description):
        return True
    if is_insurance_agent_role(title, description):
        return True
    return False


# ── Save to Supabase ─────────────────────────────────────────────────────────

def save_job(title, company, location, description, url, source, date_posted=None):
    if not url:
        return
    salary = extract_salary_value(f"{title} {description}")
    short_description_ru = build_short_description_ru(title, location or "Remote", salary)
    date_found = datetime.utcnow().isoformat() + "Z"

    job_payload = {
        "date_found": date_found,
        "source": source,
        "title": title[:500] if title else "",
        "company": company[:255] if company else "",
        "location": location[:255] if location else "",
        "salary": salary,
        "short_description_ru": short_description_ru,
        "url": url,
    }

    # Google Sheet dedupe is independent: "only new relative to sheet"
    try:
        sheet_writer.append_if_new(job_payload)
    except Exception as e:
        print(f"  WARN [sheets]: {e}")

    existing = supabase.table("jobs").select("id").eq("url", url).execute()
    if existing.data:
        print(f"  ℹ️  Skip Supabase (duplicate url): {url[:100]}")
        return  # already exists

    supabase.table("jobs").insert({
        "title": job_payload["title"],
        "company": job_payload["company"],
        "location": job_payload["location"],
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
        searches = [
            "support", "customer-support", "technical-support", "it-support",
            "automation", "crm", "helpdesk", "service-desk", "insurance",
            "claims", "operations",
        ]
        count = 0
        seen_ids = set()
        for tag in searches:
            url = f"https://jobicy.com/api/v2/remote-jobs?count=100&tag={tag}"
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
    skip_stats = {"not_remote": 0, "not_relevant": 0, "advanced_english": 0, "foreign_language": 0, "agent_role": 0, "other": 0}
    for query in searches:
        try:
            jobs = []
            anchor_samples = []
            for page in range(1, 4):
                page_suffix = "" if page == 1 else f"/pagina{page}"
                url = f"https://www.ejobs.ro/locuri-de-munca/remote{page_suffix}/?search={requests.utils.quote(query)}"
                r = requests.get(url, headers=headers, timeout=15)
                soup = BeautifulSoup(r.text, "html.parser")

                for a in soup.select("a[href]"):
                    href = (a.get("href") or "").strip()
                    text = a.get_text(" ", strip=True)
                    if href and text and ("locuri-de-munca" in href or "remote" in href):
                        anchor_samples.append((href, text))
                        if len(anchor_samples) >= 5:
                            break

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
                        candidate_lists = []

                        direct_elements = item.get("itemListElement", [])
                        if isinstance(direct_elements, list):
                            candidate_lists.append(direct_elements)

                        main_entity = item.get("mainEntity", {})
                        if isinstance(main_entity, dict) and isinstance(main_entity.get("itemListElement"), list):
                            candidate_lists.append(main_entity.get("itemListElement", []))

                        graph_nodes = item.get("@graph", [])
                        if isinstance(graph_nodes, list):
                            for node in graph_nodes:
                                if isinstance(node, dict) and isinstance(node.get("itemListElement"), list):
                                    candidate_lists.append(node.get("itemListElement", []))
                                node_main_entity = node.get("mainEntity", {}) if isinstance(node, dict) else {}
                                if isinstance(node_main_entity, dict) and isinstance(node_main_entity.get("itemListElement"), list):
                                    candidate_lists.append(node_main_entity.get("itemListElement", []))

                        for elements in candidate_lists:
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
            if query == searches[0] and anchor_samples:
                print("  DEBUG ejobs anchor samples:")
                for href, text in anchor_samples:
                    print(f"    - {href} | {text[:90]}")

            for job in jobs:
                title = job["title"].strip()
                job_url = job["url"].strip()
                if not title or not job_url:
                    continue

                description, detected_location = fetch_ejobs_job_details(job_url, headers)
                description = description or title
                location = detected_location or "Remote"

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
                if requires_foreign_language(title, description):
                    skip_stats["foreign_language"] += 1
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
            if query == searches[0]:
                print("  DEBUG bestjobs link samples:")
                for link in links[:5]:
                    href = (link.get("href") or "").strip()
                    text = link.get_text(" ", strip=True)
                    print(f"    - {href} | {text[:90]}")

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
            if query == searches[0]:
                print("  DEBUG hipo link samples:")
                for link in links[:5]:
                    href = (link.get("href") or "").strip()
                    text = link.get_text(" ", strip=True)
                    print(f"    - {href} | {text[:90]}")

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
