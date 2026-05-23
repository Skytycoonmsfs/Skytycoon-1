"""One-off: extract _install_six_main_hub_tabs from agent transcript."""
import json
import re
from pathlib import Path

p = Path(
    r"C:\Users\schmi\.cursor\projects\c-Users-schmi-Desktop-Neuer-Ordner-2"
    r"\agent-transcripts\898daed6-4cdb-46c0-a810-971721807db4"
    r"\898daed6-4cdb-46c0-a810-971721807db4.jsonl"
)
out = Path(__file__).resolve().parent.parent / "_hub_install_extract.txt"
chunks = []
for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
    if "_install_six_main_hub_tabs" not in line and "def _install_six_main_hub" not in line:
        continue
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        continue
    msg = obj.get("message", {})
    for part in msg.get("content", []):
        if part.get("type") != "tool_use":
            continue
        inp = part.get("input", {})
        for key in ("new_string", "old_string"):
            s = inp.get(key) or ""
            if "def _install_six_main_hub_tabs" in s:
                chunks.append(f"=== line {i} {key} ===\n{s}\n")
            elif "_install_six_main_hub_tabs" in s and len(s) > 200:
                chunks.append(f"=== line {i} {key} (snippet) ===\n{s[:4000]}\n")

out.write_text("\n".join(chunks) if chunks else "nothing found", encoding="utf-8")
print("wrote", out, "parts", len(chunks))
