"""Download PDF attachments, extract text, and upload to Cloudflare R2.

Reads from attachments table, downloads PDFs to temp files,
extracts text using PyMuPDF, uploads to R2, and updates the database.

Usage:
    python scripts/download_pdfs.py              # All pending PDFs
    python scripts/download_pdfs.py --limit 5    # Test with 5 PDFs
    python scripts/download_pdfs.py --ministry meti  # Specific ministry
"""
import argparse
import os
import re
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from tqdm import tqdm
from urllib3.util.retry import Retry

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_DIR = Path(__file__).parent.parent
DB_PATH = PROJECT_DIR / "dev.db"

# Load environment variables
load_dotenv(PROJECT_DIR / ".env.local")

# Set up requests session with retry
session = requests.Session()
session.headers.update({
    "User-Agent": "GovDocIndex/1.0 (research project)",
    "Accept-Language": "ja,en;q=0.9",
})
retry = Retry(total=3, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504])
session.mount("https://", HTTPAdapter(max_retries=retry))
session.mount("http://", HTTPAdapter(max_retries=retry))


def get_r2_client():
    """Create a boto3 S3 client configured for Cloudflare R2."""
    import boto3

    account_id = os.environ["R2_ACCOUNT_ID"]
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def sanitize_filename(name: str) -> str:
    """Create a safe filename from a string."""
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = name.strip(". ")
    return name[:100] if name else "unnamed"


def extract_text_from_pdf(pdf_path: Path) -> tuple[str, int]:
    """Extract text and page count from a PDF file using PyMuPDF."""
    import fitz  # PyMuPDF

    text_parts = []
    try:
        doc = fitz.open(str(pdf_path))
        page_count = len(doc)
        for page in doc:
            text_parts.append(page.get_text())
        doc.close()
    except Exception as e:
        print(f"  PyMuPDF error for {pdf_path.name}: {e}")
        return "", 0

    text = "\n".join(text_parts).strip()
    return text, page_count


def main():
    parser = argparse.ArgumentParser(description="Download PDFs, extract text, upload to R2")
    parser.add_argument("--limit", type=int, default=0, help="Max number of PDFs to download (0=unlimited)")
    parser.add_argument("--ministry", type=str, default=None, help="Only download PDFs for this ministry slug")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"Database not found: {DB_PATH}")
        sys.exit(1)

    # Validate R2 environment variables
    required_env = ["R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME"]
    missing = [v for v in required_env if not os.environ.get(v)]
    if missing:
        print(f"Missing required environment variables: {', '.join(missing)}")
        print("Please set them in .env.local")
        sys.exit(1)

    bucket = os.environ["R2_BUCKET_NAME"]
    s3 = get_r2_client()

    conn = sqlite3.connect(str(DB_PATH), timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")

    # Get pending PDF attachments with ministry/committee info
    query = """
        SELECT a.id, a.url, a.title, a.file_type,
               m.slug as ministry_slug, c.slug as committee_slug
        FROM attachments a
        JOIN documents d ON a.document_id = d.id
        JOIN committees c ON d.committee_id = c.id
        JOIN ministries m ON c.ministry_id = m.id
        WHERE a.is_downloaded = 0 AND a.file_type = 'pdf'
    """
    if args.ministry:
        query += f" AND m.slug = '{args.ministry}'"
    query += " ORDER BY d.meeting_date DESC"
    if args.limit > 0:
        query += f" LIMIT {args.limit}"

    attachments = conn.execute(query).fetchall()

    if not attachments:
        print("No pending PDFs to download.")
        conn.close()
        return

    print(f"Found {len(attachments)} PDFs to download.")
    print(f"Uploading to R2 bucket: {bucket}")

    downloaded = 0
    errors = 0

    for att in tqdm(attachments, desc="Downloading", file=sys.stdout):
        sanitized = sanitize_filename(att["title"])
        r2_key = f"{att['ministry_slug']}/{att['committee_slug']}/{att['id']}_{sanitized}.pdf"

        try:
            time.sleep(1)  # Rate limiting
            resp = session.get(att["url"], timeout=60)
            resp.raise_for_status()

            file_size = len(resp.content)

            # Write to temp file for text extraction
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(resp.content)
                tmp_path = Path(tmp.name)

            try:
                # Extract text from temp file
                text_content, page_count = extract_text_from_pdf(tmp_path)

                # Upload to R2
                s3.upload_file(
                    str(tmp_path),
                    bucket,
                    r2_key,
                    ExtraArgs={"ContentType": "application/pdf"},
                )

                # Update database — store R2 key in local_path
                conn.execute(
                    """UPDATE attachments
                       SET local_path = ?, file_size = ?, page_count = ?,
                           text_content = ?, is_downloaded = 1,
                           updated_at = datetime('now')
                       WHERE id = ?""",
                    (r2_key, file_size, page_count, text_content, att["id"]),
                )
                conn.commit()
                downloaded += 1
            finally:
                # Always delete temp file
                tmp_path.unlink(missing_ok=True)

        except Exception as e:
            errors += 1
            tqdm.write(f"  Error downloading {att['url']}: {e}")
            if errors > 50:
                tqdm.write("Too many errors, stopping.")
                break

    conn.close()

    print(f"\n{'='*50}")
    print(f"Downloaded & uploaded to R2: {downloaded}")
    print(f"Errors: {errors}")


if __name__ == "__main__":
    main()
