#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SkyTycoon Pro – Deployment / Update-Manager (SSH + SFTP).

Meilenstein 148/149: optional systemd-Dienst (``skytycoon.service``), Nginx-Stopp,
Ports 80/443 freimachen, Let's Encrypt (optional).

Sicherheit: Zugangsdaten nur über Umgebungsvariablen oder ``.env.deploy``
(``env.deploy.example``). Keine Passwörter im Quelltext.

Die Datei ``.env.deploy`` wird automatisch gesucht: zuerst optional
``SKYTYCOON_DEPLOY_ENV_FILE``, dann ``./.env.deploy`` (aktuelles Arbeitsverzeichnis),
dann ``.env.deploy`` **neben** ``deploy_system.py`` (überschreibt — praktisch wenn du
das Skript per vollem Pfad startest, aber die Zugangsdaten im Projektordner liegen).

Optional statt Passwort: ``SKYTYCOON_DEPLOY_KEY_PATH`` (OpenSSH-Privatkey); Key-Passphrase
optional in ``SKYTYCOON_DEPLOY_KEY_PASSPHRASE`` oder gleich ``SKYTYCOON_DEPLOY_PASSWORD``.

Voraussetzung: pip install -r deploy_requirements.txt

Optional: ``SKYTYCOON_DEPLOY_NGINX_PROXY=1`` richtet Nginx als Reverse Proxy ein (Port 80/443
-> uvicorn auf ``127.0.0.1:HTTP_PORT``); dann ``SKYTYCOON_DEPLOY_STOP_NGINX=0`` setzen.
Mit ``SKYTYCOON_DEPLOY_SKIP_CERTBOT=0`` folgt ``certbot --nginx``. Optional
``SKYTYCOON_DEPLOY_CERTBOT_INCLUDE_WWW=0`` wenn ``www.`` noch kein DNS hat.

Typisch:
  set SKYTYCOON_DEPLOY_PASSWORD=...
  set SKYTYCOON_DEPLOY_USE_SYSTEMD=1
  python deploy_system.py

Nur prüfen, ob auf dem Server Dateien und Dienst da sind (ohne Upload):
  python deploy_system.py --verify
"""

from __future__ import annotations

import argparse
import os
import sys
import textwrap
from pathlib import Path


def _print_safe(msg: str, *, err: bool = False) -> None:
    """Windows-Konsole (cp1252): Remote-UTF-8-Ausgaben ohne Crash ausgeben."""
    stream = sys.stderr if err else sys.stdout
    try:
        print(msg, file=stream)
    except UnicodeEncodeError:
        enc = getattr(stream, "encoding", None) or "utf-8"
        try:
            stream.buffer.write((msg + "\n").encode(enc, errors="replace"))
        except Exception:
            stream.buffer.write((msg + "\n").encode("ascii", errors="replace"))


def _env_value_strip(raw: str) -> str:
    v = raw.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    return v


def _apply_env_deploy_file(path: Path) -> bool:
    """Lädt ``path`` nach ``os.environ`` (überschreibt bei doppeltem Key die letzte Datei gewinnt)."""
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8", errors="replace")
    if text.startswith("\ufeff"):
        text = text.lstrip("\ufeff")
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ[k.strip()] = _env_value_strip(v)
    return True


def _load_deploy_env_from_known_locations() -> tuple[list[Path], list[Path]]:
    """Reihenfolge: explizite Datei → CWD → Skriptverzeichnis (letztere überschreibt)."""
    script_dir = Path(__file__).resolve().parent
    candidates: list[Path] = []
    explicit = (os.environ.get("SKYTYCOON_DEPLOY_ENV_FILE") or "").strip()
    if explicit:
        candidates.append(Path(explicit).expanduser())
    candidates.append(Path.cwd() / ".env.deploy")
    candidates.append(script_dir / ".env.deploy")
    tried: list[Path] = []
    loaded: list[Path] = []
    seen: set[Path] = set()
    for p in candidates:
        try:
            rp = p.resolve()
        except OSError:
            tried.append(p)
            continue
        if rp in seen:
            continue
        seen.add(rp)
        tried.append(p)
        if _apply_env_deploy_file(p):
            loaded.append(p)
    return tried, loaded


def _run_ssh(ssh, cmd: str, *, relax: bool = False) -> bool:
    import paramiko  # noqa: PLC0415

    print(f"[EXEC] {cmd}")
    _stdin, stdout, stderr = ssh.exec_command(cmd)
    exit_status = stdout.channel.recv_exit_status()
    out_msg = stdout.read().decode("utf-8", errors="replace").strip()
    err_msg = stderr.read().decode("utf-8", errors="replace").strip()
    if out_msg:
        _print_safe(f"[STDOUT]: {out_msg}")
    if err_msg:
        _print_safe(f"[STDERR]: {err_msg}")
    if exit_status != 0:
        if relax:
            print(f"[WARN] Exit {exit_status} (ignoriert)")
            return True
        print(f"[FATAL] Exit {exit_status}")
        return False
    return True


def execute_ssh_commands(ssh, commands: list[str]) -> bool:
    for cmd in commands:
        if not _run_ssh(ssh, cmd, relax=False):
            return False
    return True


def execute_ssh_relaxed(ssh, commands: list[str]) -> None:
    for cmd in commands:
        _run_ssh(ssh, cmd, relax=True)


def verify_remote_deployment(ssh, remote: str, http_port: int) -> None:
    """Nur Diagnose: zeigt Remote-Dateien, Dienststatus und Log-Tail (kein Upload)."""
    print("[VERIFY] Remote-Prüfung (kein Deploy) …")
    cmds = [
        f"echo '--- Verzeichnis {remote} ---'",
        f"ls -la {remote} 2>&1 | head -80",
        "echo '--- server_backend.py ---'",
        f"test -f {remote}/server_backend.py && ls -la {remote}/server_backend.py "
        f"|| echo '[FEHLEND] {remote}/server_backend.py'",
        "echo '--- requirements.txt ---'",
        f"test -f {remote}/requirements.txt && ls -la {remote}/requirements.txt "
        f"|| echo '[FEHLEND] {remote}/requirements.txt'",
        "echo '--- systemctl skytycoon ---'",
        "sudo systemctl status skytycoon.service --no-pager -l 2>&1 || true",
        f"echo '--- tail {remote}/server.log ---'",
        f"tail -n 30 {remote}/server.log 2>&1 || true",
        f"echo '--- Lauschende Ports (u.a. {http_port}) ---'",
        "sudo ss -tlnp 2>/dev/null | head -40 || netstat -tlnp 2>/dev/null | head -40 || true",
        "echo '--- version.json (Datei im App-Root) ---'",
        f"test -f {remote}/version.json && cat {remote}/version.json "
        f"|| echo '[HINWEIS] Keine {remote}/version.json — Server nutzt ENV oder leere url.'",
        f"echo '--- GET /api/v1/public/version.json (127.0.0.1:{http_port}) ---'",
        f"curl -sS -m 8 http://127.0.0.1:{http_port}/api/v1/public/version.json 2>&1 || true",
    ]
    execute_ssh_relaxed(ssh, cmds)


def _upload_paypal_env_sftp(sftp, remote: str) -> None:
    """Schreibt paypal.env auf den Server (PAYPAL_CLIENT_SECRET aus .env.deploy)."""
    keys = (
        "PAYPAL_CLIENT_ID",
        "PAYPAL_CLIENT_SECRET",
        "PAYPAL_SECRET",
        "PAYPAL_MODE",
        "PAYPAL_SANDBOX",
        "PAYPAL_WEBHOOK_ID",
        "PAYPAL_PRODUCT_EUR",
        "PAYPAL_SKIP_WEBHOOK_VERIFY",
    )
    lines: list[str] = []
    for k in keys:
        v = (os.environ.get(k) or "").strip()
        if v:
            lines.append(f"{k}={v}")
    if not lines:
        print(
            "[HINWEIS] Keine PAYPAL_* Variablen in .env.deploy — "
            "paypal.env auf dem Server bleibt unverändert."
        )
        return
    content = "\n".join(lines) + "\n"
    tmp = f"/tmp/paypal.env.{os.getpid()}"
    with sftp.file(tmp, "w") as fh:
        fh.write(content)
    dest = f"{remote}/paypal.env"
    try:
        sftp.remove(dest)
    except OSError:
        pass
    sftp.rename(tmp, dest)
    print(f"[SFTP] paypal.env ({len(lines)} Variablen) -> {dest}")


def upload_directory_sftp(sftp, local_dir: Path, remote_dir: str) -> None:
    for root, _dirs, files in os.walk(local_dir):
        rel = os.path.relpath(root, str(local_dir))
        target_dir = remote_dir if rel == "." else f"{remote_dir}/{rel}".replace("\\", "/")
        try:
            sftp.mkdir(target_dir)
        except OSError:
            pass
        for name in files:
            lp = Path(root) / name
            rp = f"{target_dir}/{name}".replace("\\", "/")
            print(f"[SFTP] {lp} -> {rp}")
            sftp.put(str(lp), rp)


def _upload_systemd_unit(
    ssh,
    remote: str,
    domain: str,
    *,
    use_https: bool,
    http_port: int,
    bind_host: str = "0.0.0.0",
) -> bool:
    """Schreibt ``/etc/systemd/system/skytycoon.service`` auf dem Remote-Host."""

    uvicorn_bin = f"{remote}/venv/bin/uvicorn"
    if use_https and domain:
        listen_port = 443
        exec_start = (
            f"{uvicorn_bin} server_backend:app --host 0.0.0.0 --port {listen_port} "
            f"--ssl-keyfile /etc/letsencrypt/live/{domain}/privkey.pem "
            f"--ssl-certfile /etc/letsencrypt/live/{domain}/fullchain.pem"
        )
    else:
        listen_port = http_port
        exec_start = f"{uvicorn_bin} server_backend:app --host {bind_host} --port {listen_port}"

    unit = textwrap.dedent(
        f"""\
        [Unit]
        Description=SkyTycoon Pro FastAPI Full-Stack Web Server
        After=network.target

        [Service]
        Type=simple
        User=root
        WorkingDirectory={remote}
        Environment=PYTHONUNBUFFERED=1
        EnvironmentFile=-{remote}/smtp.env
        EnvironmentFile=-{remote}/paypal.env
        ExecStartPre=/bin/sh -c 'fuser -k {listen_port}/tcp 2>/dev/null || true; sleep 1'
        ExecStart={exec_start}
        Restart=always
        RestartSec=5
        StartLimitIntervalSec=120
        StartLimitBurst=10
        StandardOutput=append:{remote}/server.log
        StandardError=append:{remote}/server.log

        [Install]
        WantedBy=multi-user.target
        """
    ).strip()

    tmp = f"/tmp/skytycoon.service.{os.getpid()}"
    sftp = ssh.open_sftp()
    try:
        with sftp.file(tmp, "w") as fh:
            fh.write(unit)
    finally:
        sftp.close()

    cmds = [
        f"sudo mv {tmp} /etc/systemd/system/skytycoon.service",
        "sudo chmod 644 /etc/systemd/system/skytycoon.service",
        "sudo systemctl daemon-reload",
        "sudo systemctl enable skytycoon.service",
        "sudo systemctl restart skytycoon.service",
        "sudo systemctl status skytycoon.service --no-pager -l || true",
    ]
    return execute_ssh_commands(ssh, cmds)


def _install_nginx_reverse_proxy(
    ssh,
    *,
    domain: str,
    back_port: int,
    run_certbot: bool,
    certbot_include_www: bool,
) -> bool:
    """Nginx auf Port 80 (und optional certbot --nginx fuer HTTPS). Backend: 127.0.0.1:back_port."""
    d_safe = domain.replace("'", "").replace(";", "").strip()
    if not d_safe:
        print("[WARN] Kein gueltiger Domainname fuer Nginx-Proxy.")
        return False
    www = f"www.{d_safe}"
    conf = (
        textwrap.dedent(
            f"""\
            server {{
                listen 80;
                listen [::]:80;
                server_name {d_safe} {www};
                location / {{
                    proxy_pass http://127.0.0.1:{int(back_port)};
                    proxy_http_version 1.1;
                    proxy_set_header Host $host;
                    proxy_set_header X-Real-IP $remote_addr;
                    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
                    proxy_set_header X-Forwarded-Proto $scheme;
                    proxy_set_header Upgrade $http_upgrade;
                    proxy_set_header Connection "upgrade";
                    proxy_read_timeout 3600s;
                    proxy_send_timeout 3600s;
                }}
            }}
            """
        ).strip()
        + "\n"
    )

    tmp = f"/tmp/skytycoon.nginx.{os.getpid()}"
    site = "/etc/nginx/sites-available/skytycoon.info"
    sftp = ssh.open_sftp()
    try:
        with sftp.file(tmp, "w") as fh:
            fh.write(conf)
    finally:
        sftp.close()

    cmds = [
        "sudo DEBIAN_FRONTEND=noninteractive apt-get install -y nginx",
        f"sudo mv {tmp} {site}",
        "sudo rm -f /etc/nginx/sites-enabled/default",
        f"sudo ln -sf {site} /etc/nginx/sites-enabled/skytycoon.info",
        "sudo nginx -t",
        "sudo systemctl enable nginx",
        "sudo systemctl restart nginx",
    ]
    if not execute_ssh_commands(ssh, cmds):
        return False
    execute_ssh_relaxed(
        ssh,
        [
            "sudo ufw allow OpenSSH || true",
            "sudo ufw allow 80/tcp || true",
            "sudo ufw allow 443/tcp || true",
            f"sudo ufw allow {int(back_port)}/tcp || true",
        ],
    )
    if run_certbot:
        dom_args = f"-d {d_safe}"
        if certbot_include_www:
            dom_args += f" -d {www}"
        cer = (
            f"sudo certbot --nginx {dom_args} --non-interactive "
            "--agree-tos --register-unsafely-without-email --redirect"
        )
        if not _run_ssh(ssh, cer, relax=False):
            print(
                "[WARN] certbot --nginx fehlgeschlagen (DNS A/AAAA, Port 80 von aussen?). "
                "http:// sollte trotzdem per Nginx erreichbar sein.",
            )
    return True


def _paramiko_ssh_connect(
    ssh: object,
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    key_path: str,
    key_passphrase: str,
) -> None:
    import paramiko  # noqa: PLC0415

    base_kw = dict(
        hostname=host,
        port=port,
        username=user,
        timeout=45,
        allow_agent=False,
        look_for_keys=False,
    )
    kp = (key_path or "").strip()
    if kp:
        pth = Path(kp).expanduser()
        if not pth.is_file():
            raise FileNotFoundError(f"SKYTYCOON_DEPLOY_KEY_PATH nicht gefunden: {pth}")
        pp = (key_passphrase or "").strip() or None
        last_err: Exception | None = None
        for cls_name in ("Ed25519Key", "RSAKey", "ECDSAKey"):
            cls = getattr(paramiko, cls_name, None)
            if cls is None:
                continue
            try:
                pkey = cls.from_private_key_file(str(pth), password=pp)
                ssh.connect(pkey=pkey, **base_kw)
                return
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                continue
        raise last_err if last_err else RuntimeError("SSH-Key konnte nicht geladen werden.")
    if not (password or "").strip():
        raise ValueError("SKYTYCOON_DEPLOY_PASSWORD fehlt (Passwort-Login).")
    ssh.connect(password=password, **base_kw)


def main() -> int:
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            try:
                _stream.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError, AttributeError):
                pass

    parser = argparse.ArgumentParser(description="SkyTycoon Pro - Remote-Deploy (SSH/SFTP).")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Kein Upload/Pip: nur SSH-Diagnose (Remote-Dateien, systemctl, Log-Tail).",
    )
    args = parser.parse_args()

    _, loaded_paths = _load_deploy_env_from_known_locations()

    host = os.environ.get("SKYTYCOON_DEPLOY_HOST", "").strip()
    user = os.environ.get("SKYTYCOON_DEPLOY_USER", "").strip()
    password = os.environ.get("SKYTYCOON_DEPLOY_PASSWORD", "").strip()
    key_path = (os.environ.get("SKYTYCOON_DEPLOY_KEY_PATH") or "").strip()
    key_pass = (os.environ.get("SKYTYCOON_DEPLOY_KEY_PASSPHRASE") or password).strip()
    port = int(os.environ.get("SKYTYCOON_DEPLOY_PORT", "22"))
    remote = os.environ.get("SKYTYCOON_DEPLOY_REMOTE_DIR", "/home/skytycoon").rstrip("/")
    domain = os.environ.get("SKYTYCOON_DEPLOY_DOMAIN", "").strip()
    skip_cert = os.environ.get("SKYTYCOON_DEPLOY_SKIP_CERTBOT", "1").strip() in (
        "1",
        "true",
        "yes",
    )
    http_port = int(os.environ.get("SKYTYCOON_DEPLOY_HTTP_PORT", "8000"))
    use_systemd = os.environ.get("SKYTYCOON_DEPLOY_USE_SYSTEMD", "0").strip() in (
        "1",
        "true",
        "yes",
    )
    stop_nginx = os.environ.get("SKYTYCOON_DEPLOY_STOP_NGINX", "1").strip() in (
        "1",
        "true",
        "yes",
    )
    nginx_proxy = os.environ.get("SKYTYCOON_DEPLOY_NGINX_PROXY", "0").strip() in (
        "1",
        "true",
        "yes",
    )
    certbot_include_www = os.environ.get("SKYTYCOON_DEPLOY_CERTBOT_INCLUDE_WWW", "1").strip() in (
        "1",
        "true",
        "yes",
    )

    if not host or not user or (not password and not key_path):
        print(
            "[FEHLER] SKYTYCOON_DEPLOY_HOST und SKYTYCOON_DEPLOY_USER müssen gesetzt sein; "
            "dazu SKYTYCOON_DEPLOY_PASSWORD oder SKYTYCOON_DEPLOY_KEY_PATH.",
            file=sys.stderr,
        )
        print(
            "[HINWEIS] Lege ``.env.deploy`` im Ordner dieses Skripts an (Kopie von env.deploy.example) "
            "oder setze SKYTYCOON_DEPLOY_ENV_FILE.",
            file=sys.stderr,
        )
        if loaded_paths:
            print(f"[INFO] Eingelesene Datei(en): {', '.join(str(p) for p in loaded_paths)}", file=sys.stderr)
        else:
            print("[INFO] Keine .env.deploy-Datei mit gültigen Werten gefunden.", file=sys.stderr)
            print(f"[INFO] Gesucht unter anderem: {Path(__file__).resolve().parent / '.env.deploy'}", file=sys.stderr)
        return 2

    try:
        import paramiko  # noqa: PLC0415
    except ImportError:
        print("[FEHLER] paramiko fehlt: pip install -r deploy_requirements.txt", file=sys.stderr)
        return 3

    print("=" * 56)
    print("SkyTycoon Pro - Remote-Deploy")
    print(f"Ziel: {user}@{host}:{port} -> {remote}")
    print(f"systemd: {use_systemd!r} | nginx stop: {stop_nginx!r} | nginx proxy: {nginx_proxy!r} | certbot skip: {skip_cert!r}")
    print("=" * 56)

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        _paramiko_ssh_connect(
            ssh,
            host=host,
            port=port,
            user=user,
            password=password,
            key_path=key_path,
            key_passphrase=key_pass,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[KRITISCH] SSH: {exc}", file=sys.stderr)
        return 4

    if args.verify:
        try:
            verify_remote_deployment(ssh, remote, http_port)
        finally:
            ssh.close()
        print("\n[VERIFY FERTIG] Bei fehlender server_backend.py zuerst Deploy ohne --verify ausführen.")
        return 0

    sftp = ssh.open_sftp()
    try:
        init_cmds = [
            f"mkdir -p {remote}/templates",
            f"mkdir -p {remote}/static/images",
            f"mkdir -p {remote}/database",
            f"mkdir -p {remote}/user_backups",
            f"mkdir -p {remote}/server_logs",
        ]
        if not execute_ssh_commands(ssh, init_cmds):
            ssh.close()
            return 5

        here = Path(__file__).resolve().parent
        sb = here / "server_backend.py"
        rq = here / "server_requirements.txt"
        if sb.is_file():
            print("[SFTP] server_backend.py")
            sftp.put(str(sb), f"{remote}/server_backend.py")
            print(f"[OK] server_backend.py hochgeladen ({sb.stat().st_size} Bytes lokal).")
        m216 = here / "wirtschaft_m216_extension.py"
        if m216.is_file():
            print("[SFTP] wirtschaft_m216_extension.py")
            sftp.put(str(m216), f"{remote}/wirtschaft_m216_extension.py")
            print(f"[OK] wirtschaft_m216_extension.py hochgeladen ({m216.stat().st_size} Bytes lokal).")
        if rq.is_file():
            print("[SFTP] server_requirements.txt -> requirements.txt")
            sftp.put(str(rq), f"{remote}/requirements.txt")
            print(f"[OK] requirements.txt auf dem Server aktualisiert ({rq.stat().st_size} Bytes lokal).")
        mp = here / "main.py"
        if mp.is_file():
            execute_ssh_commands(ssh, [f"mkdir -p {remote}/client_source"])
            print("[SFTP] main.py -> client_source/main.py (Referenz-Stand fuer Support/Updates)")
            sftp.put(str(mp), f"{remote}/client_source/main.py")
            print(f"[OK] main.py Snapshot ({mp.stat().st_size} Bytes lokal).")
        tpl = here / "templates"
        if tpl.is_dir():
            upload_directory_sftp(sftp, tpl, f"{remote}/templates")
        elif sb.is_file():
            print(
                "[HINWEIS] Kein lokaler Ordner ./templates – "
                "Server legt Standard-Templates beim Start an."
            )
        st = here / "static"
        if st.is_dir():
            print("[SFTP] static/ (Bilder, Assets)")
            upload_directory_sftp(sftp, st, f"{remote}/static")

        cc = here / "cert_checker.py"
        if cc.is_file():
            sftp.put(str(cc), f"{remote}/cert_checker.py")
        vj = here / "version.json"
        if vj.is_file():
            print("[SFTP] version.json (Client-Update-Manifest -> App-Root)")
            sftp.put(str(vj), f"{remote}/version.json")
            print(f"[OK] version.json hochgeladen ({vj.stat().st_size} Bytes lokal).")
        _upload_paypal_env_sftp(sftp, remote)
    finally:
        sftp.close()

    pip = f"{remote}/venv/bin/pip"
    setup = [
        "sudo apt-get update -y",
        "sudo DEBIAN_FRONTEND=noninteractive apt-get install -y python3-pip python3-venv certbot",
        f"test -d {remote}/venv || python3 -m venv {remote}/venv",
        f"{pip} install --upgrade pip",
        f"{pip} install -r {remote}/requirements.txt",
    ]
    if not execute_ssh_commands(ssh, setup):
        ssh.close()
        return 6

    use_https_unit = bool(domain) and not skip_cert
    if use_systemd and nginx_proxy:
        use_https_unit = False

    if use_systemd:
        # Meilenstein 149: Nginx / Port-Konflikte
        if stop_nginx and not nginx_proxy:
            execute_ssh_relaxed(
                ssh,
                [
                    "sudo systemctl stop nginx || true",
                    "sudo systemctl disable nginx || true",
                ],
            )
        execute_ssh_relaxed(
            ssh,
            [
                "sudo fuser -k 80/tcp || true",
                "sudo fuser -k 443/tcp || true",
                f"sudo fuser -k {http_port}/tcp || true",
                "sudo pkill -f '[u]vicorn server_backend:app' || true",
                "sudo pkill -f '[p]ython.*server_backend:app' || true",
                f"sudo pkill -f '[p]ython3.*{http_port}' || true",
                "sleep 2",
                f"sudo fuser -k {http_port}/tcp || true",
                "sudo systemctl stop skytycoon || true",
            ],
        )

        if use_https_unit:
            execute_ssh_relaxed(
                ssh,
                [
                    "sudo fuser -k 80/tcp || true",
                    "sudo fuser -k 443/tcp || true",
                ],
            )
            ssl_cmd = (
                f"sudo certbot certonly --standalone --non-interactive --agree-tos "
                f"--register-unsafely-without-email -d {domain} -d www.{domain}"
            )
            if not _run_ssh(ssh, ssl_cmd, relax=False):
                print(
                    "[WARN] Certbot fehlgeschlagen (DNS/Port?). "
                    "systemd-Unit wird mit HTTP-Port ohne TLS eingerichtet.",
                )
                use_https_unit = False

        execute_ssh_relaxed(
            ssh,
            [f"chmod 600 {remote}/paypal.env 2>/dev/null || true"],
        )
        if not _upload_systemd_unit(
            ssh,
            remote,
            domain,
            use_https=use_https_unit,
            http_port=http_port,
            bind_host="127.0.0.1" if nginx_proxy else "0.0.0.0",
        ):
            ssh.close()
            return 7
        if nginx_proxy and domain:
            print("[INFO] Nginx reverse proxy (Port 80 -> uvicorn) wird eingerichtet …")
            _install_nginx_reverse_proxy(
                ssh,
                domain=domain,
                back_port=http_port,
                run_certbot=not skip_cert,
                certbot_include_www=certbot_include_www,
            )
    else:
        # Legacy: nohup (ohne systemd)
        uvicorn = f"{remote}/venv/bin/uvicorn"
        execute_ssh_relaxed(
            ssh,
            [
                f"sudo fuser -k {http_port}/tcp || true",
                "sudo fuser -k 443/tcp || true",
            ],
        )
        launch_http = (
            f"cd {remote} && nohup {uvicorn} server_backend:app "
            f"--host 0.0.0.0 --port {http_port} > {remote}/server.log 2>&1 &"
        )
        launch_https = ""
        if domain and not skip_cert:
            launch_https = (
                f"cd {remote} && nohup {uvicorn} server_backend:app --host 0.0.0.0 --port 443 "
                f"--ssl-keyfile /etc/letsencrypt/live/{domain}/privkey.pem "
                f"--ssl-certfile /etc/letsencrypt/live/{domain}/fullchain.pem "
                f"> {remote}/server.log 2>&1 &"
            )
            ssl_cmd = (
                f"sudo certbot certonly --standalone --non-interactive --agree-tos "
                f"--register-unsafely-without-email -d {domain} -d www.{domain}"
            )
            execute_ssh_relaxed(
                ssh,
                ["sudo fuser -k 80/tcp || true", "sudo fuser -k 443/tcp || true"],
            )
            _run_ssh(ssh, ssl_cmd, relax=True)
        final_launch = launch_https if (domain and not skip_cert and launch_https) else launch_http
        execute_ssh_commands(ssh, [final_launch, "sleep 2", "ps aux | grep '[u]vicorn' || true"])

    if domain:
        print("[INFO] Post-Deploy Healthcheck (localhost) …")
        execute_ssh_relaxed(
            ssh,
            [
                "sleep 3",
                f"curl -sS -m 12 -o /dev/null -w '%{{http_code}}' http://127.0.0.1:{http_port}/api/v1/health || echo FAIL",
                f"curl -sS -m 12 -o /dev/null -w '%{{http_code}}' http://127.0.0.1:{http_port}/api/v1/public/version.json || echo FAIL",
                f"curl -sS -m 12 -o /dev/null -w '%{{http_code}}' http://127.0.0.1:{http_port}/ || echo FAIL",
            ],
        )

    ssh.close()

    print("\n[FERTIG]")
    print("Log (Unit / nohup):", f"{remote}/server.log")
    if use_systemd:
        print("Dienst: sudo systemctl status skytycoon.service")
        if nginx_proxy and domain:
            print(f"Oeffentlich (HTTP):  http://{domain}/")
            if not skip_cert:
                print(f"HTTPS (nach certbot): https://{domain}/")
            else:
                print(
                    "[HINWEIS] SKYTYCOON_DEPLOY_SKIP_CERTBOT=1: kein TLS. "
                    "Browser versuchen oft https:// — setzen Sie SKIP_CERTBOT=0 und DNS A auf diesen Server.",
                )
            print(
                "[HINWEIS] IONOS/Firewall: Ports 80/443 von aussen erlauben (Cloud-Panel + ggf. ufw status).",
            )
        elif use_https_unit and domain:
            print(f"HTTPS: https://{domain}/")
        else:
            print(f"HTTP:  http://{host}:{http_port}/")
    elif domain and not skip_cert:
        print(f"HTTPS: https://{domain}/")
    else:
        print(f"HTTP:  http://{host}:{http_port}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
