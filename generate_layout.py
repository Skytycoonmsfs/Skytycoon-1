import json
import os

addon_path = "skytycoon-ingame-panel"
layout_file = os.path.join(addon_path, "layout.json")

entries = []

# Scanne alle Dateien im Addon-Ordner für den MSFS-Kern
for root, dirs, files in os.walk(addon_path):
    for file in files:
        if file in ["layout.json", "manifest.json"]:
            if file == "layout.json":
                continue

        full_path = os.path.join(root, file)
        rel_path = os.path.relpath(full_path, addon_path).replace("\\", "/")

        stat = os.stat(full_path)
        size = stat.st_size

        # Exakter Windows-Filetime-Zeitstempel (wichtig für MSFS-Kaltstart)
        filetime = int((stat.st_mtime + 11644473600) * 10000000)

        entries.append(
            {
                "path": rel_path,
                "size": size,
                "date": filetime,
            }
        )

layout_content = {"content": entries}

with open(layout_file, "w", encoding="utf-8") as f:
    json.dump(layout_content, f, indent=2)

print(f"[SUCCESS] layout.json wurde mit {len(entries)} Dateien perfekt für MSFS kalibriert!")
