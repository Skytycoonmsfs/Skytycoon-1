"""Extract job_board / hangar blocks from transcript before flat change."""
import json
from pathlib import Path

p = Path(
    r"C:\Users\schmi\.cursor\projects\c-Users-schmi-Desktop-Neuer-Ordner-2"
    r"\agent-transcripts\898daed6-4cdb-46c0-a810-971721807db4"
    r"\898daed6-4cdb-46c0-a810-971721807db4.jsonl"
)
out = Path(__file__).resolve().parent.parent / "_job_hangar_extract.txt"
for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
    if i < 2640 or i > 2655:
        continue
    if "job_board_tabs" not in line and "hangar_inner_tabs" not in line:
        continue
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        continue
    for part in obj.get("message", {}).get("content", []):
        if part.get("type") != "tool_use":
            continue
        inp = part.get("input", {})
        for key in ("old_string", "new_string"):
            s = inp.get(key) or ""
            if "job_board_tabs" in s and len(s) > 500:
                out.write_text(
                    f"line {i} {key} len={len(s)}\n\n{s}\n",
                    encoding="utf-8",
                )
                print("wrote", out, "from", key)
                raise SystemExit

print("not found")
