from pathlib import Path

p = Path(__file__).resolve().parents[1] / "templates" / "dashboard.html"
s = p.read_text(encoding="utf-8")
if "market/license_shop" in s:
    print("already patched")
    raise SystemExit(0)
block = """
  <div class="dash-ext" style="border-color:#d4af37;margin-bottom:24px;">
    <h4 style="color:#d4af37;margin:0 0 12px;">🌐 {% if lang == 'de' %}Wirtschaftsmodule (Credits){% else %}Economy modules (credits){% endif %}</h4>
    <p style="color:#78909c;font-size:13px;margin:0 0 14px;">{% if lang == 'de' %}Neuer Tab — Hauptspiel (25 €) weiter per PayPal.{% else %}New tab — main game (€25) still via PayPal.{% endif %}</p>
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px;font-size:13px;">
      <a href="/market/license_shop" target="_blank" rel="noopener" style="padding:10px;background:#0b0f19;border:1px solid #2a3545;border-radius:8px;color:#d4af37;font-weight:700;">🛒 Credit-Shop</a>
      <a href="/market/jobs" target="_blank" rel="noopener" style="padding:10px;background:#0b0f19;border:1px solid #2a3545;border-radius:8px;">📋 Jobs</a>
      <a href="/alliance/hub" target="_blank" rel="noopener" style="padding:10px;background:#0b0f19;border:1px solid #2a3545;border-radius:8px;">🤝 Alliance</a>
      <a href="/fleet/hangar" target="_blank" rel="noopener" style="padding:10px;background:#0b0f19;border:1px solid #2a3545;border-radius:8px;">🔧 Hangar</a>
      <a href="/flight/dispatcher" target="_blank" rel="noopener" style="padding:10px;background:#0b0f19;border:1px solid #2a3545;border-radius:8px;">🛫 Boarding</a>
      <a href="/bank/loans" target="_blank" rel="noopener" style="padding:10px;background:#0b0f19;border:1px solid #2a3545;border-radius:8px;">🏦 Banking</a>
      <a href="/werft/auctions" target="_blank" rel="noopener" style="padding:10px;background:#0b0f19;border:1px solid #2a3545;border-radius:8px;">⚓ Werft</a>
      <a href="/market/dispatch" target="_blank" rel="noopener" style="padding:10px;background:#0b0f19;border:1px solid #2a3545;border-radius:8px;">🗺️ SimBrief</a>
      <a href="/market/radar" target="_blank" rel="noopener" style="padding:10px;background:#0b0f19;border:1px solid #2a3545;border-radius:8px;">📡 Radar</a>
      <a href="/market/properties" target="_blank" rel="noopener" style="padding:10px;background:#0b0f19;border:1px solid #2a3545;border-radius:8px;">🏢 HQ</a>
      <a href="/market/academy" target="_blank" rel="noopener" style="padding:10px;background:#0b0f19;border:1px solid #2a3545;border-radius:8px;">🎓 Academy</a>
      <a href="/market/weather" target="_blank" rel="noopener" style="padding:10px;background:#0b0f19;border:1px solid #2a3545;border-radius:8px;">🌦️ Weather</a>
      <a href="/market/msfs_link" target="_blank" rel="noopener" style="padding:10px;background:#0b0f19;border:1px solid #2a3545;border-radius:8px;">🔗 SimConnect</a>
    </div>
  </div>

"""
s = s.replace("  <!-- Live FIDS -->", block + "  <!-- Live FIDS -->", 1)
p.write_text(s, encoding="utf-8")
print("dashboard patched")
