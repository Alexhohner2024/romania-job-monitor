import json
import os

import gspread


FOREIGN_LANGUAGE_MARKERS = [
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

ALLOWED_REMOTE_LOCATION_TOKENS = [
    "remote",
    "anywhere",
    "worldwide",
    "romania",
    "europe",
    "eu",
    "international",
]


def needs_removal(title: str, description: str) -> bool:
    combined = f" {title} {description} ".lower()
    return any(marker in combined for marker in FOREIGN_LANGUAGE_MARKERS)


def is_location_allowed(location: str, title: str, description: str) -> bool:
    loc = (location or "").strip().lower()
    combined = f" {title} {description} ".lower()

    if not loc:
        return any(token in combined for token in ALLOWED_REMOTE_LOCATION_TOKENS)

    return any(token in loc for token in ALLOWED_REMOTE_LOCATION_TOKENS)


def main() -> None:
    sheet_id = os.environ.get("GOOGLE_SHEET_ID", "").strip()
    service_account_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not sheet_id or not service_account_json:
        raise RuntimeError("Missing GOOGLE_SHEET_ID or GOOGLE_SERVICE_ACCOUNT_JSON")

    creds = json.loads(service_account_json)
    client = gspread.service_account_from_dict(creds)
    ws = client.open_by_key(sheet_id).sheet1

    values = ws.get_all_values()
    if not values:
        print("Sheet is empty")
        return

    header = values[0]
    rows = values[1:]

    try:
        title_idx = header.index("title")
    except ValueError:
        title_idx = 2
    try:
        desc_idx = header.index("short_description_ru")
    except ValueError:
        desc_idx = 6
    try:
        location_idx = header.index("location")
    except ValueError:
        location_idx = 4

    to_delete = []
    for i, row in enumerate(rows, start=2):
        title = row[title_idx] if len(row) > title_idx else ""
        description = row[desc_idx] if len(row) > desc_idx else ""
        location = row[location_idx] if len(row) > location_idx else ""
        if needs_removal(title, description) or not is_location_allowed(location, title, description):
            to_delete.append((i, title))

    if not to_delete:
        print("No rows matched foreign-language cleanup")
        return

    for row_index, _title in reversed(to_delete):
        ws.delete_rows(row_index)

    print(f"Deleted rows: {len(to_delete)}")
    for _, title in to_delete[:20]:
        print(f"- {title[:120]}")


if __name__ == "__main__":
    main()
