"""Unified data update pipeline for GovDoc.

Orchestrates the full update cycle:
  1. Scrape ministry websites (scrape_all.py)
  2. Import Kokkai API data (import_kokkai.py)
  3. Crawl attachment links (crawl_attachments.py)
  4. Download PDFs & extract text (download_pdfs.py)
  5. Sync to Turso (sync_to_turso.ts)
  6. Rebuild FTS index (migrate_fts.ts)

Each step is optional and can be skipped via CLI flags.
Results are logged to logs/update_YYYYMMDD_HHMMSS.json.

Usage:
    python scripts/update_pipeline.py                    # Full pipeline
    python scripts/update_pipeline.py --steps scrape,kokkai  # Specific steps only
    python scripts/update_pipeline.py --skip-sync        # Skip Turso sync & FTS
    python scripts/update_pipeline.py --dry-run          # Show what would run
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_DIR = Path(__file__).parent.parent
DB_PATH = PROJECT_DIR / "dev.db"
LOGS_DIR = PROJECT_DIR / "logs"

# When TURSO_DATABASE_URL is set, scrapers write directly to Turso,
# so sync step is unnecessary and fts uses update_fts.ts.
USING_TURSO = bool(os.environ.get("TURSO_DATABASE_URL"))

ALL_STEPS = ["scrape", "kokkai", "crawl", "download", "sync", "fts"]

STEP_DESCRIPTIONS = {
    "scrape": "Scrape ministry websites",
    "kokkai": "Import Kokkai API data",
    "crawl": "Crawl attachment links",
    "download": "Download PDFs & extract text",
    "sync": "Sync to Turso",
    "fts": "Update FTS index",
}


def get_db_stats() -> dict:
    """Get current database statistics."""
    from db import connect_db
    stats = {}
    try:
        conn = connect_db()
        stats["documents"] = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        stats["documents_by_source"] = {
            row[0]: row[1]
            for row in conn.execute(
                "SELECT source, COUNT(*) FROM documents GROUP BY source"
            ).fetchall()
        }
        stats["attachments"] = conn.execute("SELECT COUNT(*) FROM attachments").fetchone()[0]
        stats["attachments_downloaded"] = conn.execute(
            "SELECT COUNT(*) FROM attachments WHERE is_downloaded = 1"
        ).fetchone()[0]
        stats["attachments_with_text"] = conn.execute(
            "SELECT COUNT(*) FROM attachments WHERE text_content IS NOT NULL AND length(text_content) > 0"
        ).fetchone()[0]
        stats["committees"] = conn.execute("SELECT COUNT(*) FROM committees").fetchone()[0]
        conn.close()
    except Exception as e:
        stats["error"] = str(e)
    return stats


def run_step(name: str, cmd: list[str], cwd: Path, timeout_minutes: int = 60) -> dict:
    """Run a pipeline step as a subprocess."""
    result = {
        "step": name,
        "description": STEP_DESCRIPTIONS.get(name, name),
        "command": " ".join(cmd),
        "started_at": datetime.now().isoformat(),
        "status": "running",
    }

    print(f"\n{'='*60}")
    print(f"Step: {name} — {STEP_DESCRIPTIONS.get(name, '')}")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'='*60}")

    start = time.time()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout_minutes * 60,
            encoding="utf-8",
            errors="replace",
        )
        elapsed = time.time() - start
        result["elapsed_seconds"] = round(elapsed, 1)
        result["exit_code"] = proc.returncode
        result["finished_at"] = datetime.now().isoformat()

        # Keep last 100 lines of output
        stdout_lines = proc.stdout.strip().split("\n") if proc.stdout else []
        stderr_lines = proc.stderr.strip().split("\n") if proc.stderr else []
        result["stdout_tail"] = stdout_lines[-100:]
        result["stderr_tail"] = stderr_lines[-50:] if stderr_lines else []

        if proc.returncode == 0:
            result["status"] = "success"
            print(f"  Completed in {elapsed:.1f}s")
            # Print last few lines of output
            for line in stdout_lines[-5:]:
                print(f"  {line}")
        else:
            result["status"] = "failed"
            print(f"  FAILED (exit code {proc.returncode}) after {elapsed:.1f}s")
            for line in stderr_lines[-10:]:
                print(f"  stderr: {line}")

    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        result["status"] = "timeout"
        result["elapsed_seconds"] = round(elapsed, 1)
        result["finished_at"] = datetime.now().isoformat()
        print(f"  TIMEOUT after {elapsed:.1f}s")

    except Exception as e:
        elapsed = time.time() - start
        result["status"] = "error"
        result["error"] = str(e)
        result["elapsed_seconds"] = round(elapsed, 1)
        result["finished_at"] = datetime.now().isoformat()
        print(f"  ERROR: {e}")

    return result


def build_step_commands(steps: list[str]) -> list[tuple[str, list[str], int]]:
    """Build (step_name, command, timeout_minutes) tuples for each step."""
    python = sys.executable
    scripts_dir = PROJECT_DIR / "scripts"
    commands = []

    for step in steps:
        if step == "scrape":
            commands.append((step, [python, str(scripts_dir / "scrape_all.py")], 120))
        elif step == "kokkai":
            commands.append((step, [python, str(scripts_dir / "import_kokkai.py")], 60))
        elif step == "crawl":
            commands.append((step, [python, str(scripts_dir / "crawl_attachments.py")], 120))
        elif step == "download":
            commands.append((step, [python, str(scripts_dir / "download_pdfs.py")], 180))
        elif step == "sync":
            commands.append((step, ["npx", "tsx", str(scripts_dir / "sync_to_turso.ts")], 30))
        elif step == "fts":
            commands.append((step, ["npx", "tsx", str(scripts_dir / "update_fts.ts")], 15))

    return commands


def main():
    parser = argparse.ArgumentParser(description="GovDoc unified update pipeline")
    parser.add_argument(
        "--steps",
        type=str,
        default=None,
        help=f"Comma-separated steps to run (default: all). Options: {','.join(ALL_STEPS)}",
    )
    parser.add_argument(
        "--skip-sync",
        action="store_true",
        help="Skip Turso sync and FTS rebuild (local DB only)",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Skip PDF download step (scrape + crawl only)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would run without executing",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue to next step even if a step fails",
    )
    args = parser.parse_args()

    # Determine which steps to run
    if args.steps:
        steps = [s.strip() for s in args.steps.split(",")]
        invalid = [s for s in steps if s not in ALL_STEPS]
        if invalid:
            print(f"Unknown steps: {', '.join(invalid)}")
            print(f"Valid steps: {', '.join(ALL_STEPS)}")
            sys.exit(1)
    else:
        steps = list(ALL_STEPS)

    # When writing directly to Turso, sync step is unnecessary
    if USING_TURSO:
        steps = [s for s in steps if s != "sync"]
        print("(Turso direct mode: sync step skipped, scrapers write to Turso directly)")

    if args.skip_sync:
        steps = [s for s in steps if s not in ("sync", "fts")]
    if args.skip_download:
        steps = [s for s in steps if s != "download"]

    step_commands = build_step_commands(steps)

    # Dry run
    if args.dry_run:
        print("DRY RUN — would execute the following steps:\n")
        for name, cmd, timeout in step_commands:
            print(f"  [{name}] {' '.join(cmd)} (timeout: {timeout}m)")
        return

    # Prepare log
    LOGS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOGS_DIR / f"update_{timestamp}.json"

    pipeline_start = datetime.now()
    print(f"GovDoc Update Pipeline — {pipeline_start.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Steps: {', '.join(steps)}")
    print(f"Log: {log_path}")

    # Snapshot DB stats before
    stats_before = get_db_stats()
    print(f"\nDB before: {stats_before.get('documents', '?')} docs, "
          f"{stats_before.get('attachments', '?')} attachments, "
          f"{stats_before.get('attachments_with_text', '?')} with text")

    # Run steps
    step_results = []
    overall_status = "success"

    for name, cmd, timeout in step_commands:
        result = run_step(name, cmd, PROJECT_DIR, timeout)
        step_results.append(result)

        if result["status"] != "success":
            overall_status = "partial" if args.continue_on_error else "failed"
            if not args.continue_on_error:
                print(f"\nPipeline stopped at step '{name}'. Use --continue-on-error to skip failures.")
                break

    # Snapshot DB stats after
    stats_after = get_db_stats()

    # Compute deltas
    deltas = {}
    for key in ["documents", "attachments", "attachments_downloaded", "attachments_with_text", "committees"]:
        before = stats_before.get(key, 0)
        after = stats_after.get(key, 0)
        if isinstance(before, int) and isinstance(after, int):
            deltas[key] = after - before

    pipeline_end = datetime.now()
    elapsed_total = (pipeline_end - pipeline_start).total_seconds()

    # Summary
    print(f"\n{'='*60}")
    print(f"Pipeline {overall_status.upper()} — {elapsed_total:.1f}s total")
    print(f"{'='*60}")

    print(f"\nDB after:  {stats_after.get('documents', '?')} docs, "
          f"{stats_after.get('attachments', '?')} attachments, "
          f"{stats_after.get('attachments_with_text', '?')} with text")

    if any(v != 0 for v in deltas.values()):
        print("\nChanges:")
        for key, delta in deltas.items():
            if delta != 0:
                sign = "+" if delta > 0 else ""
                print(f"  {key}: {sign}{delta}")
    else:
        print("\nNo data changes detected.")

    print(f"\nStep results:")
    for r in step_results:
        status_icon = {"success": "OK", "failed": "NG", "timeout": "TO", "error": "ER"}.get(r["status"], "??")
        elapsed = r.get("elapsed_seconds", 0)
        print(f"  [{status_icon}] {r['step']:12s} {elapsed:>8.1f}s")

    # Write log
    log_data = {
        "pipeline_started_at": pipeline_start.isoformat(),
        "pipeline_finished_at": pipeline_end.isoformat(),
        "elapsed_seconds": round(elapsed_total, 1),
        "overall_status": overall_status,
        "steps_requested": steps,
        "stats_before": stats_before,
        "stats_after": stats_after,
        "deltas": deltas,
        "step_results": step_results,
    }
    log_path.write_text(json.dumps(log_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nLog saved: {log_path}")


if __name__ == "__main__":
    main()
