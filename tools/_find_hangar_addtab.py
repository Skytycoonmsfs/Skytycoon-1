import json
from pathlib import Path

p = Path(
    r"C:\Users\schmi\.cursor\projects\c-Users-schmi-Desktop-Neuer-Ordner-2"
    r"\agent-transcripts\898daed6-4cdb-46c0-a810-971721807db4"
    r"\898daed6-4cdb-46c0-a810-971721807db4.jsonl"
)
hits = []
for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
    if "hangar_inner_tabs.addTab" not in line:
        continue
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        continue
    for part in obj.get("message", {}).get("content", []):
        inp = part.get("input", {})
        for key in ("old_string", "new_string"):
            s = inp.get(key) or ""
            if "hangar_inner_tabs.addTab" in s:
                hits.append((i, key, len(s), s[:2500]))
out = Path(__file__).resolve().parent.parent / "_hangar_addtab_hits.txt"
with out.open("w", encoding="utf-8") as f:
    for i, key, ln, snip in hits:
        f.write(f"\n=== line {i} {key} len={ln} ===\n{snip}\n")
print("hits", len(hits), "->", out)
