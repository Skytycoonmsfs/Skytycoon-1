# -*- coding: utf-8 -*-
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
T = ROOT / "templates"


def shell(icon: str, de: str, en: str, body: str) -> str:
    return (
        '{% extends "base.html" %}{% block title %}' + de + '{% endblock %}{% block body %}'
        '<style>.m216-panel{background:#12161f;border:1px solid #2a3545;border-radius:10px;'
        'padding:20px;margin-top:16px;}.m216-btn{background:#1976d2;color:#fff;border:0;'
        'padding:10px 18px;border-radius:8px;font-weight:700;cursor:pointer;}</style>'
        '<section style="max-width:1000px;margin:0 auto;padding:28px 16px;color:#e3e7ed;">'
        '<h2 style="color:#d4af37;">' + icon + ' {% if lang == "de" %}' + de + '{% else %}' + en + '{% endif %}</h2>'
        '<p style="color:#90a4ae;">CR: <strong style="color:#00ff66;">{{ "%.0f"|format(pilot_credits) }}</strong></p>'
        + body
        + "</section>{% endblock %}\n"
    )


PAGES = [
    (
        "alliance/hub.html",
        "🤝",
        "Allianz-Zentrale",
        "Alliance hub",
        "<motion id='m216-feed' class='m216-panel'>Live-Logbuch…</motion>"
        "<script>fetch('/api/v1/user/alliance/public_list',{credentials:'same-origin'})"
        ".then(r=>r.json()).then(d=>{document.getElementById('m216-feed').innerHTML="
        "'<pre style=color:#b0bec5;font-size:12px>'+JSON.stringify(d,null,2)+'</pre>';});</script>",
    ),
    (
        "fleet/hangar.html",
        "🔧",
        "Web-Hangar",
        "Web hangar",
        "<div class='m216-panel'><input id='rep-cost' type='number' value='2500'/> "
        "<button class='m216-btn' id='rep-go'>Repair</button><pre id='rep-out'></pre></div>"
        "<script>document.getElementById('rep-go').onclick=function(){"
        "fetch('/api/v1/hangar/repair',{method:'POST',headers:{'Content-Type':'application/json'},"
        "credentials:'same-origin',body:JSON.stringify({cost_credits:Number("
        "document.getElementById('rep-cost').value),health_after:100})})"
        ".then(r=>r.json()).then(d=>{document.getElementById('rep-out').textContent=JSON.stringify(d);});};</script>",
    ),
    (
        "flight/dispatcher.html",
        "🛫",
        "Live-Boarding",
        "Live boarding",
        "<div class='m216-panel'><p id='board-clock' style='font-size:2rem;color:#ffcc00;'>--:--:--</p></div>"
        "<script>setInterval(function(){document.getElementById('board-clock').textContent="
        "new Date().toISOString().substr(11,8);},1000);</script>",
    ),
    (
        "bank/loans.html",
        "🏦",
        "P2P-Banking",
        "P2P banking",
        "<div class='m216-panel'><p>Allianz-Kredite &amp; Kriegskasse.</p></div>",
    ),
    (
        "werft/auctions.html",
        "⚓",
        "Gebrauchtwerft",
        "Used yard",
        "<div id='auc-list' class='m216-panel'>Loading…</motion>"
        "<script>fetch('/api/v1/market/listings').then(r=>r.json()).then(d=>{"
        "document.getElementById('auc-list').innerHTML='<pre>'+JSON.stringify(d,null,2)+'</pre>';});</script>",
    ),
    (
        "market/dispatch.html",
        "🗺️",
        "SimBrief-Zentrale",
        "SimBrief",
        "<div class='m216-panel'><p>OFP im Flight Operations Center (Dashboard).</p></div>",
    ),
    (
        "market/properties.html",
        "🏢",
        "HQ & Immobilien",
        "HQ",
        "<div class='m216-panel'><p>HQ-Upgrades über Allianz-Hub.</p></div>",
    ),
    (
        "market/academy.html",
        "🎓",
        "Crew-Training",
        "Academy",
        "<motion class='m216-panel'><p>Crew-Level via Credits.</p></div>",
    ),
    (
        "market/weather.html",
        "🌦️",
        "Premium-Wetter",
        "Weather",
        "<div class='m216-panel'><p>Radar-Wetter-Overlay freigeschaltet.</p></div>",
    ),
    (
        "market/msfs_link.html",
        "🔗",
        "SimConnect-Pipeline",
        "SimConnect",
        "<div class='m216-panel'><ul><li>SimBrief → FMS</li><li>Web-Tankung</li>"
        "<li>Hangar-Schaden → MSFS-Ausfall</li></ul></div>",
    ),
]

RADAR = """{% extends "base.html" %}{% block title %}Live-Radar{% endblock %}{% block body %}
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<section style="max-width:1100px;margin:0 auto;padding:24px 16px;color:#e3e7ed;">
<h2 style="color:#d4af37;">📡 Live-Radar</h2>
<div id="m216-map" style="height:500px;border-radius:8px;border:1px solid #1a2332;"></div>
</section>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
var map=L.map('m216-map').setView([50,10],4);
var layer=L.layerGroup().addTo(map);
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',{subdomains:'abcd',maxZoom:18}).addTo(map);
function tick(){fetch('/api/v1/radar/live').then(r=>r.json()).then(function(d){
  layer.clearLayers(); var ps=(d&&d.pilots)||[];
  ps.forEach(function(p){var la=p.lat,lo=p.lng||p.lon;if(la&&lo)L.marker([la,lo]).addTo(layer).bindPopup(p.pilot_name||'?');});
});} tick(); setInterval(tick,15000);
</script>
{% endblock %}
"""

JOBS = """{% extends "base.html" %}{% block title %}Flugbörse{% endblock %}{% block body %}
<section style="max-width:1000px;margin:0 auto;padding:28px 16px;color:#e3e7ed;">
<h2 style="color:#d4af37;">📋 {% if lang == 'de' %}Live-Flugbörse{% else %}Job board{% endif %}</h2>
<div id="jobs-list"></div>
</section>
<script>
fetch('/api/v1/jobs/available?icao=ALL',{credentials:'same-origin'}).then(r=>r.json()).then(d=>{
  var el=document.getElementById('jobs-list'); var jobs=(d&&d.jobs)||[];
  if(!jobs.length){el.innerHTML='<p style="color:#78909c;">—</p>';return;}
  el.innerHTML=jobs.slice(0,40).map(function(j){
    return '<div style="background:#12161f;border:1px solid #2a3545;padding:12px;margin:8px 0;border-radius:8px;">'+
    (j.departure_icao||'?')+' → '+(j.arrival_icao||'?')+' · '+(j.payout_credits||0)+' CR</motion>';
  }).join('');
});
</script>
{% endblock %}
"""

ADMIN = """{% extends "base.html" %}{% block title %}Admin Lizenzen{% endblock %}{% block body %}
<section style="max-width:640px;margin:0 auto;padding:32px 16px;color:#e3e7ed;">
<h2 style="color:#d4af37;">🔐 Admin Commander — Module</h2>
<input id="apw" type="password" placeholder="Admin password" style="width:100%;padding:10px;margin:8px 0;"/>
<input id="ahid" placeholder="hardware_id" style="width:100%;padding:10px;margin:8px 0;"/>
<input id="amod" placeholder="module_key e.g. mod_jobs" style="width:100%;padding:10px;margin:8px 0;"/>
<button id="agrant" style="background:#d4af37;color:#000;border:0;padding:12px;font-weight:700;width:100%;">Grant</button>
<pre id="aout" style="margin-top:12px;color:#90a4ae;"></pre>
</section>
<script>
document.getElementById('agrant').onclick=function(){
  fetch('/api/v1/admin/commander/licenses/grant',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({admin_password:document.getElementById('apw').value,hardware_id:document.getElementById('ahid').value,module_key:document.getElementById('amod').value})
  }).then(r=>r.json()).then(d=>{document.getElementById('aout').textContent=JSON.stringify(d,null,2);});
};
</script>
{% endblock %}
"""


def clean(s: str) -> str:
    return s.replace("<motion ", "<div ").replace("</motion>", "</div>")


(T / "market" / "radar.html").write_text(RADAR, encoding="utf-8")
(T / "market" / "jobs.html").write_text(clean(JOBS), encoding="utf-8")
(T / "admin").mkdir(parents=True, exist_ok=True)
(T / "admin" / "commander_licenses.html").write_text(ADMIN, encoding="utf-8")

for rel, icon, de, en, body in PAGES:
    p = T / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(clean(shell(icon, de, en, body)), encoding="utf-8")

print("generated", len(PAGES) + 3, "templates")
