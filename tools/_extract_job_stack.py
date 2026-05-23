import json
from pathlib import Path

p = Path(
    r"C:\Users\schmi\.cursor\projects\c-Users-schmi-Desktop-Neuer-Ordner-2"
    r"\agent-transcripts\898daed6-4cdb-46c0-a810-971721807db4"
    r"\898daed6-4cdb-46c0-a810-971721807db4.jsonl"
)
for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
    if i not in (2530, 2648):
        continue
    obj = json.loads(line)
    for part in obj.get("message", {}).get("content", []):
        inp = part.get("input", {})
        s = inp.get("old_string") or inp.get("new_string") or ""
        if "_stack_job_board" in s or "job_root.addWidget" in s:
            Path(__file__).resolve().parent.parent.joinpath(
                f"_job_stack_line{i}.txt"
            ).write_text(s, encoding="utf-8")
            print(i, len(s))
