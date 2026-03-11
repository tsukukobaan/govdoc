"""Import recent National Diet meeting records from kokkai.ndl.go.jp API."""
import json
import sys
import time
import urllib.request
from datetime import datetime
from hashlib import md5
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from db import connect_db

API_BASE = "https://kokkai.ndl.go.jp/api/meeting_list"
MAX_RECORDS_PER_REQUEST = 100
REQUEST_INTERVAL = 3  # seconds between requests

# Fetch meetings from this year onward (NISTEP data covers up to ~2017)
START_YEAR = 2017
END_YEAR = 2026


def fetch_meetings(from_date: str, until_date: str, start_record: int = 1) -> dict:
    """Fetch meeting list from kokkai API."""
    params = (
        f"?from={from_date}&until={until_date}"
        f"&recordPacking=json"
        f"&maximumRecords={MAX_RECORDS_PER_REQUEST}"
        f"&startRecord={start_record}"
    )
    url = API_BASE + params
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def main():
    conn = connect_db()
    cursor = conn.cursor()

    # Get or create the "国会" ministry
    cursor.execute("SELECT id FROM ministries WHERE slug = 'diet'")
    row = cursor.fetchone()
    if not row:
        print("Ministry 'diet' not found in DB")
        return
    diet_ministry_id = row[0]

    # Committee cache: nameOfHouse + nameOfMeeting -> committee_id
    committee_cache: dict[str, int] = {}
    cursor.execute("SELECT id, name, slug FROM committees WHERE ministry_id = ?", (diet_ministry_id,))
    for r in cursor.fetchall():
        committee_cache[r[1]] = r[0]

    # Track existing kokkai_api documents to avoid duplicates
    cursor.execute("SELECT source_id FROM documents WHERE source = 'kokkai_api'")
    existing_ids = {r[0] for r in cursor.fetchall()}
    print(f"Existing kokkai_api documents: {len(existing_ids)}")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total_inserted = 0
    total_skipped = 0

    for year in range(START_YEAR, END_YEAR + 1):
        # Fetch by half-year to stay within reasonable result sizes
        for half in [(f"{year}-01-01", f"{year}-06-30"), (f"{year}-07-01", f"{year}-12-31")]:
            from_date, until_date = half
            start_record = 1
            period_count = 0

            while True:
                print(f"  Fetching {from_date} ~ {until_date}, start={start_record}...", end=" ")
                try:
                    data = fetch_meetings(from_date, until_date, start_record)
                except Exception as e:
                    print(f"ERROR: {e}")
                    time.sleep(5)
                    break

                total_records = data.get("numberOfRecords", 0)
                records = data.get("meetingRecord", [])
                print(f"got {len(records)}/{total_records}")

                if not records:
                    break

                for rec in records:
                    issue_id = rec.get("issueID", "")
                    if not issue_id:
                        continue

                    # Skip duplicates
                    if issue_id in existing_ids:
                        total_skipped += 1
                        continue
                    existing_ids.add(issue_id)

                    # Build committee name
                    house = rec.get("nameOfHouse", "")
                    meeting_name = rec.get("nameOfMeeting", "")
                    committee_name = f"{house} {meeting_name}".strip()

                    if not committee_name:
                        continue

                    # Get or create committee
                    if committee_name not in committee_cache:
                        slug = md5(committee_name.encode("utf-8")).hexdigest()[:8]
                        cursor.execute(
                            """INSERT INTO committees (ministry_id, name, slug, category, is_active, document_count, created_at, updated_at)
                               VALUES (?, ?, ?, 'committee', 1, 0, ?, ?)""",
                            (diet_ministry_id, committee_name, slug, now, now),
                        )
                        committee_cache[committee_name] = cursor.lastrowid

                    committee_id = committee_cache[committee_name]

                    # Build title
                    issue = rec.get("issue", "")
                    image_kind = rec.get("imageKind", "会議録")
                    title = f"{committee_name} {issue} {image_kind}".strip()

                    # URL
                    meeting_url = rec.get("meetingURL", "")
                    if not meeting_url:
                        meeting_url = f"https://kokkai.ndl.go.jp/txt/{issue_id}"

                    # Date
                    date_str = rec.get("date", "")
                    meeting_date = f"{date_str}T00:00:00.000Z" if date_str else None

                    # Insert
                    cursor.execute(
                        """INSERT INTO documents (committee_id, title, url, meeting_date, doc_type, source, source_id, created_at, updated_at)
                           VALUES (?, ?, ?, ?, 'minutes', 'kokkai_api', ?, ?, ?)""",
                        (committee_id, title, meeting_url, meeting_date, issue_id, now, now),
                    )
                    total_inserted += 1
                    period_count += 1

                # Check if there are more records
                next_pos = data.get("nextRecordPosition")
                if not next_pos or next_pos > total_records:
                    break
                start_record = next_pos
                time.sleep(REQUEST_INTERVAL)

            conn.commit()
            if period_count > 0:
                print(f"    -> {period_count} records inserted for {from_date} ~ {until_date}")
            time.sleep(REQUEST_INTERVAL)

    # Update document counts
    cursor.execute(
        """UPDATE committees SET document_count = (
            SELECT COUNT(*) FROM documents WHERE documents.committee_id = committees.id
        ) WHERE ministry_id = ?""",
        (diet_ministry_id,),
    )
    conn.commit()

    print(f"\nImport complete!")
    print(f"  Inserted: {total_inserted}")
    print(f"  Skipped (duplicates): {total_skipped}")

    cursor.execute("SELECT COUNT(*) FROM documents WHERE source = 'kokkai_api'")
    print(f"  Total kokkai_api documents: {cursor.fetchone()[0]}")

    conn.close()


if __name__ == "__main__":
    main()
