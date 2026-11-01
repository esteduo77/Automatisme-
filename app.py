import os
import sqlite3
import secrets
import ipaddress
import socket
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from apscheduler.schedulers.background import BackgroundScheduler

DB_PATH = os.getenv("DATABASE_PATH", "nexus.db")
APP_PASSWORD = os.getenv("APP_PASSWORD", "")
scheduler = BackgroundScheduler(timezone="UTC")

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            interval_minutes INTEGER NOT NULL DEFAULT 60,
            enabled INTEGER NOT NULL DEFAULT 1,
            last_status TEXT,
            last_checked TEXT,
            last_error TEXT
        )""")

def safe_target(url):
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Utilisez une URL HTTPS publique, sans identifiants.")
    host = parsed.hostname
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise ValueError("Nom de domaine introuvable.")
    for item in addresses:
        ip = ipaddress.ip_address(item[4][0])
        if not ip.is_global:
            raise ValueError("Les adresses privées ou locales ne sont pas autorisées.")
    return url

def check_task(task_id):
    with db() as c:
        task = c.execute("SELECT * FROM tasks WHERE id=? AND enabled=1", (task_id,)).fetchone()
    if not task:
        return
    status, error = "OK", None
    try:
        url = safe_target(task["url"])
        with httpx.Client(timeout=15, follow_redirects=False, headers={"User-Agent": "NexusMonitor/1.0"}) as client:
            response = client.get(url)
        status = str(response.status_code)
        if response.status_code >= 400:
            error = f"Le site a répondu HTTP {response.status_code}"
    except Exception as exc:
        status, error = "ERREUR", str(exc)[:500]
    with db() as c:
        c.execute("UPDATE tasks SET last_status=?, last_checked=?, last_error=? WHERE id=?",
                  (status, datetime.now(timezone.utc).isoformat(), error, task_id))

def schedule_task(task_id, interval):
    job_id = f"monitor-{task_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    scheduler.add_job(check_task, "interval", minutes=interval, args=[task_id], id=job_id, replace_existing=True)

@asynccontextmanager
async def lifespan(app):
    init_db()
    scheduler.start()
    with db() as c:
        rows = c.execute("SELECT id, interval_minutes FROM tasks WHERE enabled=1").fetchall()
    for row in rows:
        schedule_task(row["id"], row["interval_minutes"])
    yield
    scheduler.shutdown(wait=False)

app = FastAPI(title="NEXUS AI AUTOMATION", version="1.0.0", lifespan=lifespan)

def authorized(request: Request):
    if not APP_PASSWORD:
        return False
    supplied = request.cookies.get("nexus_session", "")
    expected = secrets.token_hex(1)  # constant-time comparison uses configured password hash below
    import hmac, hashlib
    token = hmac.new(APP_PASSWORD.encode(), b"nexus-dashboard", hashlib.sha256).hexdigest()
    return hmac.compare_digest(supplied, token)

def page(body, request=None):
    if request is None or not authorized(request):
        return HTMLResponse("""<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
        <title>NEXUS — Connexion</title><style>body{font:16px system-ui;background:#101827;color:#edf2f7;max-width:440px;margin:12vh auto;padding:24px}input,button{padding:12px;margin:8px 0;width:100%;box-sizing:border-box;border-radius:8px;border:1px solid #475569}button{background:#2563eb;color:white}</style>
        <h1>NEXUS AI AUTOMATION</h1><p>Connectez-vous au tableau de bord.</p><form method="post" action="/login"><input type="password" name="password" placeholder="Mot de passe" required><button>Se connecter</button></form></html>""")
    return HTMLResponse(body)

@app.get("/health")
def health():
    return {"status": "ok", "service": "NEXUS AI AUTOMATION"}

@app.post("/login")
def login(password: str = Form(...)):
    import hmac, hashlib
    if not APP_PASSWORD or not hmac.compare_digest(password, APP_PASSWORD):
        return HTMLResponse("Mot de passe incorrect ou APP_PASSWORD non configuré.", status_code=401)
    token = hmac.new(APP_PASSWORD.encode(), b"nexus-dashboard", hashlib.sha256).hexdigest()
    response = RedirectResponse("/", status_code=303)
    response.set_cookie("nexus_session", token, httponly=True, secure=True, samesite="strict", max_age=86400)
    return response

@app.post("/logout")
def logout():
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie("nexus_session")
    return response

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    if not authorized(request):
        return page("")
    with db() as c:
        tasks = c.execute("SELECT * FROM tasks ORDER BY id DESC").fetchall()
    rows = "".join(
        f"<tr><td>{t['id']}</td><td>{html_escape(t['name'])}</td><td><a href='{html_escape(t['url'])}' target='_blank' rel='noopener noreferrer'>{html_escape(t['url'])}</a></td><td>{t['interval_minutes']} min</td><td>{html_escape(t['last_status'] or 'En attente')}</td><td>{html_escape(t['last_checked'] or '—')}</td><td><form method='post' action='/tasks/{t['id']}/run'><button>Tester</button></form><form method='post' action='/tasks/{t['id']}/delete'><button class='danger'>Supprimer</button></form></td></tr>"
        for t in tasks
    )
    body = f"""<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
    <title>NEXUS AI AUTOMATION</title><style>
    *{{box-sizing:border-box}}body{{font:15px system-ui;background:#0b1220;color:#e5e7eb;margin:0;padding:28px}}main{{max-width:1100px;margin:auto}}h1{{font-size:28px}}.muted{{color:#9ca3af}}section,.panel{{background:#151f31;border:1px solid #29364b;border-radius:14px;padding:20px;margin:18px 0}}input{{padding:11px;border-radius:8px;border:1px solid #475569;background:#0b1220;color:white;margin:5px}}button{{padding:9px 13px;border:0;border-radius:8px;background:#2563eb;color:white;cursor:pointer;margin:3px}}.danger{{background:#9f3030}}table{{width:100%;border-collapse:collapse}}td,th{{padding:10px;border-bottom:1px solid #29364b;text-align:left;overflow-wrap:anywhere}}a{{color:#93c5fd}}@media(max-width:700px){{.tablewrap{{overflow-x:auto}}input{{width:100%}}}}</style>
    <main><h1>NEXUS AI AUTOMATION</h1><p class='muted'>Centre de surveillance et d’automatisation — version initiale sécurisée</p>
    <section><h2>Ajouter une surveillance de site</h2><form method='post' action='/tasks/create'>
    <input name='name' placeholder='Nom du site' required maxlength='80'><input name='url' placeholder='https://exemple.com' required>
    <input name='interval_minutes' type='number' min='5' max='10080' value='60' required><button>Ajouter</button></form>
    <p class='muted'>Surveillance HTTPS uniquement. Intervalle de 5 minutes à 7 jours. Les adresses privées et locales sont bloquées.</p></section>
    <section><h2>Surveillances ({len(tasks)})</h2><div class='tablewrap'><table><thead><tr><th>ID</th><th>Nom</th><th>URL</th><th>Fréquence</th><th>Dernier statut</th><th>Dernier contrôle</th><th>Actions</th></tr></thead><tbody>{rows or '<tr><td colspan=7>Aucune surveillance configurée.</td></tr>'}</tbody></table></div></section>
    <section><h2>État du système</h2><p>API : opérationnelle · Planificateur : actif · Stockage : SQLite</p><p class='muted'>Cette première version surveille les sites et planifie les contrôles. Les actions externes, envois de messages et intégrations nécessiteront une configuration dédiée.</p><form method='post' action='/logout'><button class='danger'>Déconnexion</button></form></section></main></html>"""
    return page(body, request)

def html_escape(value):
    import html
    return html.escape(str(value), quote=True)

@app.post("/tasks/create")
def create_task(request: Request, name: str = Form(...), url: str = Form(...), interval_minutes: int = Form(60)):
    if not authorized(request):
        return RedirectResponse("/", status_code=303)
    if not 5 <= interval_minutes <= 10080:
        return HTMLResponse("Fréquence invalide (5 à 10080 minutes).", status_code=400)
    try:
        safe_target(url)
    except ValueError as exc:
        return HTMLResponse(html_escape(exc), status_code=400)
    with db() as c:
        cur = c.execute("INSERT INTO tasks(name,url,interval_minutes) VALUES(?,?,?)",
                        (name[:80], url, interval_minutes))
        task_id = cur.lastrowid
    schedule_task(task_id, interval_minutes)
    return RedirectResponse("/", status_code=303)

@app.post("/tasks/{task_id}/run")
def run_task(task_id: int, request: Request):
    if not authorized(request):
        return RedirectResponse("/", status_code=303)
    check_task(task_id)
    return RedirectResponse("/", status_code=303)

@app.post("/tasks/{task_id}/delete")
def delete_task(task_id: int, request: Request):
    if not authorized(request):
        return RedirectResponse("/", status_code=303)
    job_id = f"monitor-{task_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    with db() as c:
        c.execute("DELETE FROM tasks WHERE id=?", (task_id,))
    return RedirectResponse("/", status_code=303)
