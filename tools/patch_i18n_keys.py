import json
from pathlib import Path

p = Path(__file__).resolve().parents[1] / "locales" / "translations.json"
data = json.loads(p.read_text(encoding="utf-8"))
new_de = {
    "blackbox.archive_title": (
        "Flugschreiber Archiv: Touchdown, G-Kräfte, Wind und Treibstoff "
        "- synchron mit skytycoon.info:"
    ),
    "blackbox.flight": "Flug",
    "blackbox.landing": "Landung",
    "blackbox.gforce": "G-Kraft",
    "blackbox.fuel": "Treibstoff",
    "blackbox.rating": "Bewertung",
    "tracking.archive_title": "Historisches Flight-Tracking-Archiv",
    "dash.infra": "Globale Infrastruktur",
    "dash.operate": (
        'Sie betreiben aktuell <span style="color:#d4af37;font-weight:800">{n}</span> '
        "aktive Niederlassungen weltweit."
    ),
    "dash.finance": "Finanzen: Guthaben {bal}. {loan}",
    "sim.connected": "SimConnect verbunden",
    "sim.disconnected_fmt": "SimConnect: nicht verbunden – {reason}",
    "sim.loaded_ac": "Geladenes Flugzeug",
    "sim.loaded_ac_fmt": "Geladenes Flugzeug (TITLE): {title}",
    "sim.pax_happy": "Passagier-Zufriedenheit: 100 %",
    "sim.pax_happy_fmt": "Passagier-Zufriedenheit: {s:.1f} %",
    "sim.active_job": "Aktiver Auftrag (Flug-Börse)",
    "sim.no_job": "Kein angenommener Auftrag.",
    "gsx.pushback": "Automatischer Pushback-Callout",
    "gsx.catering": "Catering-Validierung erzwingen",
    "alliance.tab.hubs": "Allianz-Hubs",
    "alliance.tab.research": "Allianz-Forschung",
    "alliance.contribute": "Beitrag leisten",
    "alliance.apply_btn": "Antrag stellen",
}
new_en = {
    "blackbox.archive_title": (
        "Flight recorder archive: touchdown, G-forces, wind and fuel "
        "— synced with skytycoon.info:"
    ),
    "blackbox.flight": "Flight",
    "blackbox.landing": "Landing",
    "blackbox.gforce": "G-force",
    "blackbox.fuel": "Fuel",
    "blackbox.rating": "Rating",
    "tracking.archive_title": "Historical flight tracking archive",
    "dash.infra": "Global infrastructure",
    "dash.operate": (
        'You currently operate <span style="color:#d4af37;font-weight:800">{n}</span> '
        "active branches worldwide."
    ),
    "dash.finance": "Finance balance: {bal}. {loan}",
    "sim.connected": "SimConnect connected",
    "sim.disconnected_fmt": "SimConnect: not connected – {reason}",
    "sim.loaded_ac": "Loaded aircraft",
    "sim.loaded_ac_fmt": "Loaded aircraft (TITLE): {title}",
    "sim.pax_happy": "Passenger satisfaction: 100 %",
    "sim.pax_happy_fmt": "Passenger satisfaction: {s:.1f} %",
    "sim.active_job": "Active job (flight exchange)",
    "sim.no_job": "No accepted job.",
    "gsx.pushback": "Automatic pushback callout",
    "gsx.catering": "Enforce catering validation",
    "alliance.tab.hubs": "Alliance Hubs",
    "alliance.tab.research": "Alliance Research",
    "alliance.contribute": "Contribute",
    "alliance.apply_btn": "Apply",
}
data["de"].update(new_de)
data["en"].update(new_en)
p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("patched", len(new_de), "keys")
