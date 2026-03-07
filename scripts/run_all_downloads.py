"""Run download_pdfs.py for all ministries with parallel execution.

Manages multiple ministry downloads with limited concurrency to avoid
SQLite contention. Designed to run as a detached process on Windows.

Usage:
    python scripts/run_all_downloads.py
    python scripts/run_all_downloads.py --workers 4
"""
import subprocess
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent
DB_PATH = PROJECT_DIR / "dev.db"
LOG_DIR = PROJECT_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

MASTER_LOG = LOG_DIR / "download_master.log"


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(MASTER_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def get_remaining():
    """Get remaining PDF counts per ministry."""
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    rows = conn.execute("""
        SELECT m.slug, COUNT(*) as cnt
        FROM attachments a
        JOIN documents d ON a.document_id = d.id
        JOIN committees c ON d.committee_id = c.id
        JOIN ministries m ON c.ministry_id = m.id
        WHERE a.is_downloaded = 0 AND a.file_type = 'pdf'
        GROUP BY m.slug
        ORDER BY cnt ASC
    """).fetchall()
    conn.close()
    return [(r[0], r[1]) for r in rows]


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4, help="Max parallel workers")
    args = parser.parse_args()

    log(f"=== Download master started (max {args.workers} workers) ===")

    remaining = get_remaining()
    if not remaining:
        log("No pending PDFs.")
        return

    total = sum(c for _, c in remaining)
    log(f"Total remaining: {total} PDFs across {len(remaining)} ministries")
    for slug, cnt in remaining:
        log(f"  {slug}: {cnt}")

    # Sort: smallest first so they finish quickly and free up worker slots
    queue = [slug for slug, _ in remaining]
    active = {}  # slug -> Popen

    while queue or active:
        # Start new workers if capacity available
        while queue and len(active) < args.workers:
            slug = queue.pop(0)
            log_file = LOG_DIR / f"download_{slug}.log"
            with open(log_file, "w", encoding="utf-8") as lf:
                proc = subprocess.Popen(
                    [sys.executable, str(PROJECT_DIR / "scripts" / "download_pdfs.py"),
                     "--ministry", slug],
                    stdout=lf,
                    stderr=subprocess.STDOUT,
                    cwd=str(PROJECT_DIR),
                )
            active[slug] = proc
            log(f"Started {slug} (PID {proc.pid})")

        # Wait and check for completed processes
        time.sleep(10)
        completed = []
        for slug, proc in active.items():
            ret = proc.poll()
            if ret is not None:
                completed.append(slug)
                log(f"Finished {slug} (exit code {ret})")

        for slug in completed:
            del active[slug]

        # Log status every 5 minutes
        if int(time.time()) % 300 < 11:
            remaining_now = get_remaining()
            total_now = sum(c for _, c in remaining_now)
            active_slugs = ", ".join(active.keys())
            log(f"Status: {total_now} remaining, active=[{active_slugs}], queue={len(queue)}")

    log("=== All downloads complete ===")

    # Final summary
    remaining_final = get_remaining()
    total_final = sum(c for _, c in remaining_final)
    if total_final == 0:
        log("All PDFs downloaded successfully!")
    else:
        log(f"{total_final} PDFs still remaining (likely errors)")
        for slug, cnt in remaining_final:
            log(f"  {slug}: {cnt}")


if __name__ == "__main__":
    main()
