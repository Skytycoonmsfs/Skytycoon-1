import json
from pathlib import Path

p = Path(
    r"C:\Users\schmi\.cursor\projects\c-Users-schmi-Desktop-Neuer-Ordner-2"
    r"\agent-transcripts\70a4318b-90ce-4efd-b0e5-42936c122a11"
    r"\70a4318b-90ce-4efd-b0e5-42936c122a11.jsonl"
)
keys = ("job_root.addWidget", "_stack_job_board.addWidget", "job_board_tabs.addTab")
for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
    if not any(k in line for k in keys):
        continue
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        continue
    for part in obj.get("message", {}).get("content", []):
        inp = part.get("input", {})
        for key in ("old_string", "new_string"):
            s = inp.get(key) or ""
            if "job_root.addWidget(self.job_board_tabs" in s or (
                "job_root.addWidget" in s and "_stack_job_board" in s
            ):
                out = Path(__file__).resolve().parent.parent / f"_70a_job_{i}_{key}.txt"
                out.write_text(s, encoding="utf-8")
                print("wrote", out.name, len(s))
