"""Test the kokkai.ndl.go.jp API response structure."""
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

url = "https://kokkai.ndl.go.jp/api/meeting_list?from=2024-01-01&until=2024-01-31&recordPacking=json&maximumRecords=3"
with urllib.request.urlopen(url) as resp:
    data = json.loads(resp.read().decode("utf-8", errors="replace"))

print("Top-level keys:", list(data.keys()))
print("numberOfRecords:", data.get("numberOfRecords"))
print("numberOfReturn:", data.get("numberOfReturn"))
print("startRecord:", data.get("startRecord"))

if "meetingRecord" in data:
    rec = data["meetingRecord"][0]
    print("\nRecord keys:", list(rec.keys()))
    for k, v in rec.items():
        if k == "speechRecord":
            print(f"  speechRecord: [{len(v)} items]")
        else:
            val_str = str(v)[:100]
            print(f"  {k}: {val_str}")
