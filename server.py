#!/usr/bin/env python3
"""
Pi Lyrics - Web Management Server
Upload PDFs, reorder them, delete them, insert blank slides via a browser UI.
Runs on port 5000.
"""

import os
import json
import shutil
import re
import time
import secrets
from pathlib import Path
from flask import (Flask, request, jsonify, send_from_directory,
                   render_template_string, abort, session, redirect, url_for)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import fitz  # PyMuPDF — used for page-count and blank-slide generation

BASE_DIR   = Path(__file__).parent
PDF_DIR    = BASE_DIR / "pdfs"
ORDER_FILE = BASE_DIR / "order.json"
CONTROL_FILE = BASE_DIR / "control.json"
STATE_FILE   = BASE_DIR / "state.json"
USERS_FILE   = BASE_DIR / "users.json"
SECRET_FILE  = BASE_DIR / "secret.key"

PDF_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024  # 64 MB max upload
if SECRET_FILE.exists():
    app.secret_key = SECRET_FILE.read_text().strip()
else:
    app.secret_key = secrets.token_hex(32)
    SECRET_FILE.write_text(app.secret_key)
    try:
        os.chmod(SECRET_FILE, 0o600)
    except Exception:
        pass
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")


def read_users():
    if USERS_FILE.exists():
        try:
            data = json.loads(USERS_FILE.read_text())
            if "users" in data and "owner" in data:
                return data
        except Exception:
            pass
    return {"owner": None, "users": {}}


def write_users(data):
    USERS_FILE.write_text(json.dumps(data, indent=2))
    try:
        os.chmod(USERS_FILE, 0o600)
    except Exception:
        pass


def has_users():
    return bool(read_users()["users"])


def current_user():
    username = session.get("username")
    if not username:
        return None
    return read_users()["users"].get(username)


def current_username():
    return session.get("username")


def is_admin_user(username=None):
    username = username or current_username()
    if not username:
        return False
    user = read_users()["users"].get(username)
    return bool(user and user.get("approved") and user.get("role") in ("admin", "owner"))


def auth_response():
    if request.path.startswith("/api/"):
        return jsonify({"error": "Authentication required"}), 401
    return redirect(url_for("login", next=request.path))


def safe_next_url(value):
    return value if value and value.startswith("/") and not value.startswith("//") else None


@app.before_request
def require_login():
    public = {"login", "register", "setup", "logout"}
    if request.endpoint in public:
        return None
    if not has_users():
        return redirect(url_for("setup"))
    user = current_user()
    if not user or not user.get("approved"):
        session.clear()
        return auth_response()
    return None


AUTH_HTML = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Pi Lyrics - {{ title }}</title>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;600;800&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet">
<style>
:root{--bg:#0d0f14;--surface:#161920;--border:#252830;--accent:#ffc83d;--text:#e8eaf0;--muted:#6b7280;--danger:#ef4444;--success:#22c55e}
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--bg);color:var(--text);font-family:'DM Sans',sans-serif;padding:24px}
.panel{width:min(420px,100%);background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:28px;box-shadow:0 20px 60px rgba(0,0,0,.35)}
.logo{font-family:'Syne',sans-serif;font-weight:800;font-size:1.45rem;margin-bottom:4px}.logo span{color:var(--accent)}
h1{font-family:'Syne',sans-serif;font-size:1rem;margin:0 0 20px;color:var(--muted);font-weight:600}
label{display:block;color:var(--muted);font-size:.82rem;margin:14px 0 6px}
input{width:100%;background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:7px;padding:10px 12px;font:inherit;outline:none}input:focus{border-color:var(--accent)}
button,.link-btn{display:inline-flex;justify-content:center;align-items:center;margin-top:18px;width:100%;border:0;border-radius:7px;padding:10px 12px;background:var(--accent);color:var(--bg);font-weight:700;font:inherit;text-decoration:none;cursor:pointer}
.secondary{background:transparent;color:var(--muted);border:1px solid var(--border)}.msg{margin:0 0 12px;color:var(--danger);font-size:.88rem}.ok{color:var(--success)}.hint{color:var(--muted);font-size:.82rem;line-height:1.45;margin-top:14px}
</style></head><body><div class="panel"><div class="logo">Pi <span>Lyrics</span></div><h1>{{ title }}</h1>{% if message %}<p class="msg {{ 'ok' if ok else '' }}">{{ message }}</p>{% endif %}{{ body|safe }}</div></body></html>"""


def auth_page(title, body, message="", ok=False):
    return render_template_string(AUTH_HTML, title=title, body=body, message=message, ok=ok)


@app.route("/setup", methods=["GET", "POST"])
def setup():
    if has_users():
        return redirect(url_for("login"))
    message = ""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not USERNAME_RE.match(username):
            message = "Use 3-32 letters, numbers, dots, dashes, or underscores."
        elif len(password) < 8:
            message = "Password must be at least 8 characters."
        else:
            write_users({"owner": username, "users": {username: {"password": generate_password_hash(password), "role": "owner", "approved": True}}})
            session["username"] = username
            return redirect(url_for("index"))
    body = """
    <form method="post"><label>Owner username</label><input name="username" autocomplete="username" required autofocus>
    <label>Password</label><input name="password" type="password" autocomplete="new-password" required minlength="8">
    <button type="submit">Create Owner Account</button></form><p class="hint">This first account becomes the protected owner account.</p>"""
    return auth_page("Create Owner Account", body, message)


@app.route("/login", methods=["GET", "POST"])
def login():
    if not has_users():
        return redirect(url_for("setup"))
    message = ""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = read_users()["users"].get(username)
        if user and user.get("approved") and check_password_hash(user.get("password", ""), password):
            session["username"] = username
            return redirect(safe_next_url(request.args.get("next")) or url_for("index"))
        message = "Your account is waiting for admin approval." if user and not user.get("approved") else "Invalid username or password."
    body = """
    <form method="post"><label>Username</label><input name="username" autocomplete="username" required autofocus>
    <label>Password</label><input name="password" type="password" autocomplete="current-password" required>
    <button type="submit">Log In</button></form><a class="link-btn secondary" href="/register">Request Access</a>"""
    return auth_page("Log In", body, message)


@app.route("/register", methods=["GET", "POST"])
def register():
    if not has_users():
        return redirect(url_for("setup"))
    message = ""
    ok = False
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        data = read_users()
        if not USERNAME_RE.match(username):
            message = "Use 3-32 letters, numbers, dots, dashes, or underscores."
        elif len(password) < 8:
            message = "Password must be at least 8 characters."
        elif username in data["users"]:
            message = "That username already exists."
        else:
            data["users"][username] = {"password": generate_password_hash(password), "role": "user", "approved": False}
            write_users(data)
            message = "Account requested. An admin can approve it."
            ok = True
    body = """
    <form method="post"><label>Username</label><input name="username" autocomplete="username" required autofocus>
    <label>Password</label><input name="password" type="password" autocomplete="new-password" required minlength="8">
    <button type="submit">Request Access</button></form><a class="link-btn secondary" href="/login">Back to Login</a>"""
    return auth_page("Request Access", body, message, ok)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

ADMIN_HTML = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Pi Lyrics - Admin</title>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;600;800&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet">
<style>
:root{--bg:#0d0f14;--surface:#161920;--border:#252830;--accent:#ffc83d;--text:#e8eaf0;--muted:#6b7280;--danger:#ef4444;--success:#22c55e}
*{box-sizing:border-box}body{margin:0;min-height:100vh;background:var(--bg);color:var(--text);font-family:'DM Sans',sans-serif}
header{display:flex;align-items:center;gap:14px;padding:22px 28px;background:var(--surface);border-bottom:1px solid var(--border)}
.logo{font-family:'Syne',sans-serif;font-weight:800;font-size:1.35rem}.logo span{color:var(--accent)}.spacer{flex:1}a{color:var(--accent);text-decoration:none}
main{max-width:860px;margin:0 auto;padding:30px 22px}h1{font-family:'Syne',sans-serif;font-size:1.1rem;margin:0 0 18px}.msg{color:var(--success);margin-bottom:14px}
.row{display:grid;grid-template-columns:1fr auto;gap:12px;align-items:center;background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:14px 16px;margin-bottom:10px}
.name{font-weight:700}.meta{color:var(--muted);font-size:.82rem;margin-top:2px}.actions{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}
button{border:1px solid var(--border);border-radius:7px;padding:7px 10px;background:transparent;color:var(--text);font:inherit;cursor:pointer}.primary{background:var(--accent);color:var(--bg);border-color:var(--accent);font-weight:700}.danger{color:var(--danger)}.disabled{color:var(--muted)}
@media(max-width:640px){.row{grid-template-columns:1fr}.actions{justify-content:flex-start}}
</style></head><body><header><div class="logo">Pi <span>Lyrics</span></div><div class="spacer"></div><a href="/">Slides</a><a href="/logout">Logout</a></header>
<main><h1>User Admin</h1>{% if message %}<div class="msg">{{ message }}</div>{% endif %}
{% for username, user in users.items() %}
<div class="row"><div><div class="name">{{ username }}</div><div class="meta">{{ user.role }} · {{ 'approved' if user.approved else 'pending approval' }}{% if username == owner %} · owner{% endif %}</div></div>
<div class="actions">
{% if username == owner %}<span class="disabled">Protected owner</span>{% elif not user.approved %}<form method="post"><input type="hidden" name="username" value="{{ username }}"><button class="primary" name="action" value="approve">Approve</button></form>{% endif %}
{% if username != owner and user.approved and user.role != 'admin' %}<form method="post"><input type="hidden" name="username" value="{{ username }}"><button name="action" value="make_admin">Make Admin</button></form>{% endif %}
{% if username != owner and user.approved and user.role == 'admin' %}<form method="post"><input type="hidden" name="username" value="{{ username }}"><button name="action" value="make_user">Make User</button></form>{% endif %}
{% if username != owner %}<form method="post"><input type="hidden" name="username" value="{{ username }}"><button class="danger" name="action" value="delete">Delete</button></form>{% endif %}
</div></div>{% endfor %}</main></body></html>"""


@app.route("/admin", methods=["GET", "POST"])
def admin():
    if not is_admin_user():
        abort(403)
    data = read_users()
    message = ""
    if request.method == "POST":
        username = request.form.get("username", "")
        action = request.form.get("action", "")
        if username == data.get("owner"):
            message = "Owner account cannot be changed."
        elif username in data["users"]:
            if action == "approve":
                data["users"][username]["approved"] = True
                message = f"Approved {username}."
            elif action == "make_admin":
                data["users"][username]["role"] = "admin"
                data["users"][username]["approved"] = True
                message = f"{username} is now an admin."
            elif action == "make_user":
                data["users"][username]["role"] = "user"
                message = f"{username} is now a regular user."
            elif action == "delete":
                del data["users"][username]
                message = f"Deleted {username}."
            write_users(data)
    return render_template_string(ADMIN_HTML, users=data["users"], owner=data.get("owner"), message=message)


# ── Order helpers ─────────────────────────────────────────────────────────────

def read_order():
    existing = set(p.name for p in PDF_DIR.glob("*.pdf"))
    if ORDER_FILE.exists():
        try:
            saved = json.loads(ORDER_FILE.read_text())
            ordered = [f for f in saved if f in existing]
            for f in sorted(existing):
                if f not in ordered:
                    ordered.append(f)
            return ordered
        except Exception:
            pass
    return sorted(existing)


def write_order(lst):
    ORDER_FILE.write_text(json.dumps(lst, indent=2))


def pdf_page_count(filename):
    """Return page count for a PDF in PDF_DIR."""
    try:
        doc = fitz.open(str(PDF_DIR / filename))
        n   = doc.page_count
        doc.close()
        return n
    except Exception:
        return 1


def remove_digits_from_filename(filename):
    stem, ext = os.path.splitext(filename)
    stem = re.sub(r"\d+", "", stem)
    return (stem or "upload") + ext


# ── API endpoints ─────────────────────────────────────────────────────────────

@app.route("/api/files", methods=["GET"])
def api_list():
    return jsonify(read_order())


@app.route("/api/pagecounts", methods=["GET"])
def api_pagecounts():
    """Return a dict of {filename: page_count} for all files in the queue."""
    counts = {f: pdf_page_count(f) for f in read_order()}
    return jsonify(counts)


@app.route("/api/upload", methods=["POST"])
def api_upload():
    if "files" not in request.files:
        return jsonify({"error": "No files part"}), 400
    uploaded = []
    for f in request.files.getlist("files"):
        if f.filename == "":
            continue
        name = remove_digits_from_filename(secure_filename(f.filename))
        if not name.lower().endswith(".pdf"):
            continue
        dest = PDF_DIR / name
        f.save(str(dest))
        uploaded.append(name)
    order = read_order()
    write_order(order)
    return jsonify({"uploaded": uploaded, "order": read_order()})


@app.route("/api/blank", methods=["POST"])
def api_blank():
    """
    Create a blank white PDF slide and insert it at the given position.
    Body JSON: { "after": <index or -1 to append>, "label": "<optional name>" }
    """
    data     = request.get_json() or {}
    label    = data.get("label", "").strip()
    after    = int(data.get("after", -1))   # -1 = append

    # Find a unique filename
    base = secure_filename(label) if label else ""
    if not base:
        base = "blank"
    candidate = base + ".pdf"
    counter   = 1
    while (PDF_DIR / candidate).exists():
        candidate = f"{base}_{counter}.pdf"
        counter  += 1

    # Generate a black A4 PDF with centered label text
    doc  = fitz.open()
    page = doc.new_page(width=595, height=842)   # A4 portrait in points
    page.draw_rect(page.rect, color=(0, 0, 0), fill=(0, 0, 0))
    font_size = 40
    text_rect = fitz.Rect(0, page.rect.height / 2 - font_size, page.rect.width, page.rect.height / 2 + font_size)
    page.insert_textbox(
        text_rect,
        label or base,
        fontsize=font_size,
        fontname="helv",
        color=(1, 200 / 255, 61 / 255),
        align=fitz.TEXT_ALIGN_CENTER,
    )
    doc.save(str(PDF_DIR / candidate))
    doc.close()

    # Insert into order
    order = read_order()
    order = [f for f in order if f != candidate]
    if after < 0 or after >= len(order):
        order.append(candidate)
    else:
        order.insert(after + 1, candidate)
    write_order(order)
    return jsonify({"created": candidate, "order": read_order()})


@app.route("/api/order", methods=["POST"])
def api_order():
    data = request.get_json()
    if not data or "order" not in data:
        return jsonify({"error": "Missing order"}), 400
    existing  = set(p.name for p in PDF_DIR.glob("*.pdf"))
    new_order = [f for f in data["order"] if f in existing]
    write_order(new_order)
    return jsonify({"order": new_order})


@app.route("/api/delete/<filename>", methods=["DELETE"])
def api_delete(filename):
    name = secure_filename(filename)
    path = PDF_DIR / name
    if not path.exists():
        return jsonify({"error": "Not found"}), 404
    path.unlink()
    order = [f for f in read_order() if f != name]
    write_order(order)
    return jsonify({"deleted": name, "order": order})


@app.route("/api/rename", methods=["POST"])
def api_rename():
    data = request.get_json()
    old_raw = data.get("old", "")
    existing = set(p.name for p in PDF_DIR.glob("*.pdf"))
    old = old_raw if old_raw in existing else secure_filename(old_raw)
    new = secure_filename(data.get("new", ""))
    if not old or not new:
        return jsonify({"error": "Missing names"}), 400
    if not new.lower().endswith(".pdf"):
        new += ".pdf"
    src = PDF_DIR / old
    dst = PDF_DIR / new
    order = read_order()
    if not src.exists():
        return jsonify({"error": "File not found"}), 404
    if dst.exists():
        return jsonify({"error": "Name already taken"}), 409
    src.rename(dst)
    order = [(new if f == old else f) for f in order]
    write_order(order)
    return jsonify({"renamed": new, "order": order})


@app.route("/api/status", methods=["GET"])
def api_status():
    try:
        return jsonify(json.loads(STATE_FILE.read_text()))
    except Exception:
        return jsonify({"file": None, "index": -1, "page": 0, "pages": 0, "total": 0})


@app.route("/api/control", methods=["POST"])
def api_control():
    data = request.get_json() or {}
    action = data.get("action")
    if action not in ("next", "prev"):
        return jsonify({"error": "Invalid action"}), 400
    command = {"action": action, "id": time.time()}
    CONTROL_FILE.write_text(json.dumps(command))
    return jsonify(command)


@app.route("/pdfs/<filename>")
def serve_pdf(filename):
    return send_from_directory(str(PDF_DIR), secure_filename(filename))


# ── Web UI ────────────────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Pi Lyrics — Slide Manager</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;600;800&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet">
<style>
  :root {
    --bg:      #0d0f14;
    --surface: #161920;
    --border:  #252830;
    --accent:  #ffc83d;
    --accent2: #ff6b35;
    --text:    #e8eaf0;
    --muted:   #6b7280;
    --danger:  #ef4444;
    --success: #22c55e;
    --radius:  10px;
  }
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'DM Sans', sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    padding: 0 0 60px;
  }

  /* Header */
  header {
    display: flex; align-items: center; gap: 18px;
    padding: 24px 32px 20px;
    border-bottom: 1px solid var(--border);
    background: var(--surface);
    position: sticky; top: 0; z-index: 100;
  }
  .logo { font-family: 'Syne', sans-serif; font-weight: 800; font-size: 1.5rem; }
  .logo span { color: var(--accent); }
  .spacer { flex: 1; }
  .subtitle { color: var(--muted); font-size: .85rem; }
  .account-nav { display: flex; align-items: center; gap: 10px; font-size: .82rem; color: var(--muted); }
  .account-nav a { color: var(--accent); text-decoration: none; }
  .status-dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--success);
    box-shadow: 0 0 6px var(--success);
    animation: pulse 2s infinite;
  }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }

  main { max-width: 860px; margin: 0 auto; padding: 32px 24px; }

  /* Upload zone */
  .upload-zone {
    border: 2px dashed var(--border);
    border-radius: var(--radius);
    padding: 40px 32px;
    text-align: center;
    cursor: pointer;
    transition: border-color .2s, background .2s;
    background: var(--surface);
    margin-bottom: 32px;
  }
  .upload-zone:hover, .upload-zone.dragover {
    border-color: var(--accent);
    background: rgba(255,200,61,.04);
  }
  .upload-zone .icon { font-size: 2.5rem; margin-bottom: 12px; }
  .upload-zone h3 { font-family: 'Syne', sans-serif; font-size: 1.1rem; margin-bottom: 6px; }
  .upload-zone p { color: var(--muted); font-size: .85rem; }
  .upload-zone input { display: none; }
  .progress-bar {
    height: 4px; background: var(--border); border-radius: 2px;
    margin-top: 16px; overflow: hidden; display: none;
  }
  .progress-fill {
    height: 100%; background: linear-gradient(90deg, var(--accent), var(--accent2));
    width: 0; transition: width .3s; border-radius: 2px;
  }

  /* Section header */
  .section-hdr {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 16px; gap: 12px; flex-wrap: wrap;
  }
  .section-hdr h2 { font-family: 'Syne', sans-serif; font-weight: 600; font-size: 1rem; }
  .section-hdr-left { display: flex; align-items: center; gap: 12px; }
  .badge {
    background: rgba(255,200,61,.15); color: var(--accent);
    font-size: .75rem; font-weight: 500;
    padding: 2px 10px; border-radius: 99px;
  }

  /* Blank slide button */
  .btn-blank {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 7px 14px; border-radius: 8px; font-size: .82rem;
    font-family: 'DM Sans', sans-serif; font-weight: 500;
    background: rgba(255,200,61,.1); color: var(--accent);
    border: 1px solid rgba(255,200,61,.25);
    cursor: pointer; transition: background .15s, border-color .15s;
  }
  .btn-blank:hover { background: rgba(255,200,61,.18); border-color: rgba(255,200,61,.5); }

  /* Blank slide dialog */
  .blank-dialog-overlay {
    display: none; position: fixed; inset: 0;
    background: rgba(0,0,0,.65); z-index: 200;
    align-items: center; justify-content: center;
  }
  .blank-dialog-overlay.open { display: flex; }
  .blank-dialog {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 14px; padding: 28px 28px 24px;
    width: 360px; max-width: 95vw;
    box-shadow: 0 20px 60px rgba(0,0,0,.6);
  }
  .blank-dialog h3 {
    font-family: 'Syne', sans-serif; font-size: 1rem;
    margin-bottom: 18px; color: var(--text);
  }
  .blank-dialog label { font-size: .82rem; color: var(--muted); display: block; margin-bottom: 6px; }
  .blank-dialog input, .blank-dialog select {
    width: 100%; background: var(--bg); border: 1px solid var(--border);
    color: var(--text); border-radius: 7px; padding: 8px 12px;
    font-size: .9rem; font-family: inherit; margin-bottom: 16px; outline: none;
  }
  .blank-dialog input:focus, .blank-dialog select:focus { border-color: var(--accent); }
  .blank-dialog-actions { display: flex; gap: 10px; justify-content: flex-end; margin-top: 4px; }

  /* File list */
  #file-list { display: flex; flex-direction: column; gap: 10px; }
  .file-item {
    display: flex; align-items: center; gap: 12px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 14px 16px;
    transition: border-color .15s, box-shadow .15s;
    cursor: grab;
    position: relative;
  }
  .file-item:hover { border-color: #353840; box-shadow: 0 2px 12px rgba(0,0,0,.4); }
  .file-item.dragging { opacity: .4; }
  .file-item.drag-over { border-color: var(--accent); background: rgba(255,200,61,.05); }
  .file-item.is-current { border-color: var(--accent); background: rgba(255,200,61,.08); }
  .file-item.is-current .file-idx { color: var(--accent); }
  .file-item.is-blank { border-color: #2a2d36; }
  .file-item.is-blank.is-current { border-color: var(--accent); }
  .file-item.is-blank .file-icon { opacity: .4; }

  .drag-handle {
    color: var(--muted); font-size: 1.1rem; cursor: grab;
    padding: 0 4px; flex-shrink: 0;
    touch-action: none;
    user-select: none;
    -webkit-user-select: none;
    -webkit-touch-callout: none;
  }
  .file-idx {
    font-family: 'Syne', sans-serif; font-weight: 800;
    font-size: .8rem; color: var(--muted); min-width: 24px;
    text-align: center;
  }
  .file-icon { font-size: 1.4rem; flex-shrink: 0; }
  .file-info { flex: 1; min-width: 0; }
  .file-name-row { display: flex; align-items: center; gap: 8px; }
  .file-name {
    font-weight: 500; font-size: .95rem;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    cursor: pointer;
  }
  .file-name:hover { color: var(--accent); }
  .page-badge {
    flex-shrink: 0;
    font-size: .7rem; font-weight: 500;
    background: rgba(255,255,255,.07); color: var(--muted);
    border: 1px solid var(--border);
    padding: 1px 7px; border-radius: 99px;
    white-space: nowrap;
  }
  .file-name-input {
    background: var(--bg); border: 1px solid var(--accent);
    color: var(--text); border-radius: 6px; padding: 3px 8px;
    font-size: .95rem; font-family: inherit; width: 100%;
    outline: none;
  }
  .file-meta { font-size: .76rem; color: var(--muted); margin-top: 2px; }

  .file-actions { display: flex; gap: 6px; flex-shrink: 0; }
  .btn {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 6px 12px; border-radius: 7px; font-size: .8rem;
    font-family: 'DM Sans', sans-serif; font-weight: 500;
    border: none; cursor: pointer; transition: opacity .15s, transform .1s;
  }
  .btn:active { transform: scale(.97); }
  .btn-ghost {
    background: transparent; color: var(--muted);
    border: 1px solid var(--border);
  }
  .btn-ghost:hover { color: var(--text); border-color: #3a3d47; }
  .btn-danger { background: rgba(239,68,68,.12); color: var(--danger); border: 1px solid transparent; }
  .btn-danger:hover { background: rgba(239,68,68,.2); }
  .btn-primary {
    background: var(--accent); color: #0d0f14;
    font-weight: 600;
  }
  .btn-primary:hover { opacity: .88; }

  /* Empty state */
  .empty-state {
    text-align: center; padding: 56px 24px; color: var(--muted);
  }
  .empty-state .icon { font-size: 3rem; margin-bottom: 16px; }
  .empty-state p { font-size: .9rem; }

  /* Toast */
  #toast {
    position: fixed; bottom: 24px; right: 24px;
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 10px; padding: 12px 20px;
    font-size: .88rem; box-shadow: 0 8px 24px rgba(0,0,0,.5);
    opacity: 0; transform: translateY(8px);
    transition: all .25s; pointer-events: none; z-index: 999;
    max-width: 320px;
  }
  #toast.show { opacity: 1; transform: translateY(0); }
  #toast.success { border-color: var(--success); color: var(--success); }
  #toast.error   { border-color: var(--danger);  color: var(--danger); }

  /* Display controls */
  .display-controls {
    margin-top: 40px; background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 20px 24px;
    display: flex; align-items: center; justify-content: space-between; gap: 16px;
  }
  .current-display { min-width: 0; }
  .current-display h3 { font-family: 'Syne', sans-serif; font-size: .9rem; margin-bottom: 6px; color: var(--muted); }
  .current-display-name {
    color: var(--accent); font-weight: 600; font-size: 1rem;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .current-display-meta { color: var(--muted); font-size: .78rem; margin-top: 3px; }
  .nav-controls { display: flex; gap: 10px; flex-shrink: 0; }
  .btn-nav {
    min-width: 96px; justify-content: center;
    background: rgba(255,200,61,.1); color: var(--accent);
    border: 1px solid rgba(255,200,61,.25);
  }
  .btn-nav:hover { background: rgba(255,200,61,.18); border-color: rgba(255,200,61,.5); }
  .help { display: none; }
  @media (max-width: 640px) {
    .display-controls { align-items: stretch; flex-direction: column; }
    .nav-controls { display: grid; grid-template-columns: 1fr 1fr; }
    .btn-nav { width: 100%; min-width: 0; }
  }
</style>
</head>
<body>

<header>
  <div>
    <div class="logo">Pi <span>Lyrics</span></div>
    <div class="subtitle">Slide Manager</div>
  </div>
  <div class="spacer"></div>
  <div class="account-nav">
    <span>{{ username }}</span>
    {% if is_admin %}<a href="/admin">Admin</a>{% endif %}
    <a href="/logout">Logout</a>
  </div>
  <div class="status-dot" title="Server running"></div>
</header>

<main>

  <!-- Upload -->
  <div class="upload-zone" id="drop-zone">
    <div class="icon">📂</div>
    <h3>Drop PDF files here</h3>
    <p>or click to browse — multiple files supported</p>
    <input type="file" id="file-input" multiple accept=".pdf"/>
    <div class="progress-bar" id="progress-bar">
      <div class="progress-fill" id="progress-fill"></div>
    </div>
  </div>

  <!-- List -->
  <div class="section-hdr">
    <div class="section-hdr-left">
      <h2>Slide Queue</h2>
      <span class="badge" id="count-badge">0 slides</span>
    </div>
    <button class="btn-blank" id="add-blank-btn">＋ Blank Slide</button>
  </div>
  <div id="file-list"></div>

  <!-- Display controls -->
  <div class="display-controls">
    <div class="current-display">
      <h3>Now Showing</h3>
      <div class="current-display-name" id="current-display-name">Display not connected</div>
      <div class="current-display-meta" id="current-display-meta">Use the controls to navigate the display</div>
    </div>
    <div class="nav-controls">
      <button class="btn btn-nav" id="prev-btn">← Previous</button>
      <button class="btn btn-nav" id="next-btn">Next →</button>
    </div>
  </div>

  <!-- Help -->
  <div class="help">
    <h3>REMOTE / KEYBOARD SHORTCUTS ON DISPLAY</h3>
    <ul>
      <li><span class="key">→</span> / <span class="key">↓</span> / <span class="key">Space</span> — Next page / slide</li>
      <li><span class="key">←</span> / <span class="key">↑</span> — Previous page / slide</li>
      <li><span class="key">PgDn</span> / <span class="key">PgUp</span> — Also work</li>
      <li>Multi-page PDFs: keys step through pages before advancing to next slide</li>
      <li>Drag rows here to reorder queue</li>
      <li>Click a filename to rename it</li>
    </ul>
  </div>

</main>

<!-- Blank slide dialog -->
<div class="blank-dialog-overlay" id="blank-dialog-overlay">
  <div class="blank-dialog">
    <h3>➕ Insert Blank Slide</h3>
    <label for="blank-label">Label (optional)</label>
    <input type="text" id="blank-label" placeholder="e.g. Intermission, Break…" maxlength="60"/>
    <label for="blank-position">Insert after</label>
    <select id="blank-position">
      <option value="-1">— end of queue —</option>
    </select>
    <div class="blank-dialog-actions">
      <button class="btn btn-ghost" id="blank-cancel">Cancel</button>
      <button class="btn btn-primary" id="blank-confirm">Insert</button>
    </div>
  </div>
</div>

<div id="toast"></div>

<script>
let files      = [];
let pageCounts = {};   // { filename: pageCount }
let dragSrc    = null;
let renaming   = false;
let currentStatus = {file: null, index: -1, page: 0, pages: 0, total: 0};

// ── Toast ─────────────────────────────────────────────────────────────────────
function toast(msg, type='success', dur=2800) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = `show ${type}`;
  clearTimeout(t._tid);
  t._tid = setTimeout(() => t.className = '', dur);
}

// ── API helpers ───────────────────────────────────────────────────────────────
async function api(url, opts={}) {
  const r = await fetch(url, opts);
  if (!r.ok) { const e = await r.json().catch(()=>({})); throw new Error(e.error||r.statusText); }
  return r.json();
}

function displayName(name) {
  if (!name) return '';
  const bare = name.toLowerCase().endsWith('.pdf') ? name.slice(0, -4) : name;
  return bare.replace(/_/g, ' ');
}

// ── Render list ───────────────────────────────────────────────────────────────
function render() {
  const list = document.getElementById('file-list');
  const currentName = document.getElementById('current-display-name');
  const currentMeta = document.getElementById('current-display-meta');
  document.getElementById('count-badge').textContent =
    `${files.length} slide${files.length===1?'':'s'}`;
  if (currentStatus.file) {
    currentName.textContent = displayName(currentStatus.file);
    currentMeta.textContent = `${currentStatus.index + 1} / ${currentStatus.total}` +
      (currentStatus.pages > 1 ? `, page ${currentStatus.page + 1} / ${currentStatus.pages}` : '');
  } else {
    currentName.textContent = 'Display not connected';
    currentMeta.textContent = 'Use the controls to navigate the display';
  }

  if (files.length === 0) {
    list.innerHTML = `<div class="empty-state">
      <div class="icon">🎞️</div>
      <p>No PDFs yet. Upload some files above.</p>
    </div>`;
    return;
  }

  list.innerHTML = files.map((f, i) => {
    const isBlank  = f.startsWith('blank') || f.includes('blank');
    const isCurrent = f === currentStatus.file;
    const pages    = pageCounts[f] || 1;
    const pageBadge = pages > 1
      ? `<span class="page-badge" title="${pages} pages">${pages} pp</span>`
      : '';
    const icon = pages > 1 ? '📑' : (isBlank ? '⬜' : '📄');
    return `
    <div class="file-item${isBlank ? ' is-blank' : ''}${isCurrent ? ' is-current' : ''}" draggable="true" data-name="${f}" data-idx="${i}">
      <span class="drag-handle" title="Drag to reorder">⠿</span>
      <span class="file-idx">${i+1}</span>
      <span class="file-icon">${icon}</span>
      <div class="file-info">
        <div class="file-name-row">
          <div class="file-name" title="Click to rename" data-name="${f}">${f}</div>
          ${pageBadge}
        </div>
      </div>
      <div class="file-actions">
        <a class="btn btn-ghost" href="/pdfs/${encodeURIComponent(f)}" target="_blank" title="Preview">👁 View</a>
        <button class="btn btn-danger" onclick="deleteFile('${f.replace(/'/g,"\\'")}')">✕</button>
      </div>
    </div>`;
  }).join('');

  // Drag-and-drop
  list.querySelectorAll('.file-item').forEach(el => {
    el.addEventListener('dragstart', e => {
      dragSrc = el.dataset.name;
      el.classList.add('dragging');
    });
    el.addEventListener('dragend', () => el.classList.remove('dragging'));
    el.addEventListener('dragover', e => { e.preventDefault(); el.classList.add('drag-over'); });
    el.addEventListener('dragleave', () => el.classList.remove('drag-over'));
    el.addEventListener('drop', async e => {
      e.preventDefault();
      el.classList.remove('drag-over');
      if (!dragSrc || dragSrc === el.dataset.name) return;
      const from = files.indexOf(dragSrc);
      const to   = files.indexOf(el.dataset.name);
      files.splice(to, 0, files.splice(from, 1)[0]);
      render();
      try {
        await saveOrder();
        toast('Order saved');
      } catch(err) { toast(err.message, 'error'); }
    });
  });

  // Touch reorder for mobile browsers
  list.querySelectorAll('.drag-handle').forEach(handle => {
    handle.addEventListener('pointerdown', e => {
      if (e.pointerType !== 'touch') return;
      const item = handle.closest('.file-item');
      if (!item) return;
      e.preventDefault();
      handle.setPointerCapture(e.pointerId);
      dragSrc = item.dataset.name;
      const startY = e.clientY;
      const oldTransition = item.style.transition;
      item.classList.add('dragging');
      item.style.zIndex = '1000';
      item.style.transition = 'none';
      item.style.pointerEvents = 'none';
      item.style.boxShadow = '0 12px 30px rgba(0,0,0,.55)';

      const move = evt => {
        evt.preventDefault();
        item.style.transform = `translateY(${evt.clientY - startY}px) scale(1.02)`;
        list.querySelectorAll('.file-item.drag-over').forEach(el => el.classList.remove('drag-over'));
        const target = document.elementFromPoint(evt.clientX, evt.clientY)?.closest('.file-item');
        if (target && target.dataset.name !== dragSrc) target.classList.add('drag-over');
      };

      const end = async evt => {
        handle.removeEventListener('pointermove', move);
        handle.removeEventListener('pointerup', end);
        handle.removeEventListener('pointercancel', end);
        const target = document.elementFromPoint(evt.clientX, evt.clientY)?.closest('.file-item');
        item.classList.remove('dragging');
        item.style.transform = '';
        item.style.zIndex = '';
        item.style.transition = oldTransition;
        item.style.pointerEvents = '';
        item.style.boxShadow = '';
        list.querySelectorAll('.file-item.drag-over').forEach(el => el.classList.remove('drag-over'));
        if (!target || !dragSrc || target.dataset.name === dragSrc) return;
        const from = files.indexOf(dragSrc);
        const to = files.indexOf(target.dataset.name);
        files.splice(to, 0, files.splice(from, 1)[0]);
        render();
        try {
          await saveOrder();
          toast('Order saved');
        } catch(err) { toast(err.message, 'error'); }
      };

      handle.addEventListener('pointermove', move);
      handle.addEventListener('pointerup', end);
      handle.addEventListener('pointercancel', end);
    });
    handle.addEventListener('contextmenu', e => e.preventDefault());
  });

  // Inline rename
  list.querySelectorAll('.file-name').forEach(el => {
    el.addEventListener('click', e => startRename(el, e));
  });
}

async function saveOrder() {
  return api('/api/order', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({order: files})
  });
}

function caretIndexFromPoint(el, clientX) {
  const text = el.dataset.name || '';
  const style = getComputedStyle(el);
  const canvas = caretIndexFromPoint._canvas || (caretIndexFromPoint._canvas = document.createElement('canvas'));
  const ctx = canvas.getContext('2d');
  ctx.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
  const x = Math.max(0, clientX - el.getBoundingClientRect().left);
  for (let i = 0; i < text.length; i++) {
    const mid = ctx.measureText(text.slice(0, i) + text[i]).width - ctx.measureText(text[i]).width / 2;
    if (x < mid) return i;
  }
  return text.length;
}

function inputCaretIndexFromPoint(inp, clientX) {
  const style = getComputedStyle(inp);
  const canvas = inputCaretIndexFromPoint._canvas || (inputCaretIndexFromPoint._canvas = document.createElement('canvas'));
  const ctx = canvas.getContext('2d');
  ctx.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
  const paddingLeft = parseFloat(style.paddingLeft) || 0;
  const x = Math.max(0, clientX - inp.getBoundingClientRect().left - paddingLeft + inp.scrollLeft);
  for (let i = 0; i < inp.value.length; i++) {
    const mid = ctx.measureText(inp.value.slice(0, i) + inp.value[i]).width - ctx.measureText(inp.value[i]).width / 2;
    if (x < mid) return i;
  }
  return inp.value.length;
}

function startRename(el, event) {
  renaming = true;
  const oldName = el.dataset.name;
  const caretPos = event ? caretIndexFromPoint(el, event.clientX) : oldName.length;
  let committed = false;
  const item = el.closest('.file-item');
  const inp = document.createElement('input');
  inp.className = 'file-name-input';
  inp.value = oldName;
  el.replaceWith(inp);
  if (item) item.draggable = false;
  inp.focus();
  requestAnimationFrame(() => inp.setSelectionRange(caretPos, caretPos));
  inp.addEventListener('pointerup', e => {
    e.stopPropagation();
    const pos = inputCaretIndexFromPoint(inp, e.clientX);
    inp.setSelectionRange(pos, pos);
  });
  async function commit() {
    if (committed) return;
    committed = true;
    let newName = inp.value.trim();
    if (!newName || newName === oldName) { renaming = false; await loadFiles(); return; }
    if (!newName.toLowerCase().endsWith('.pdf')) newName += '.pdf';
    try {
      const d = await api('/api/rename', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({old: oldName, new: newName})
      });
      files = d.order;
      renaming = false;
      render();
      toast(`Renamed to ${newName}`);
    } catch(err) {
      renaming = false;
      toast(err.message, 'error');
      await loadFiles();
    }
  }
  inp.addEventListener('blur', commit);
  inp.addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); inp.blur(); }
    if (e.key === 'Escape') { renaming = false; committed = true; inp.removeEventListener('blur', commit); loadFiles(); }
  });
}

// ── Load ──────────────────────────────────────────────────────────────────────
async function loadFiles() {
  if (renaming) return;
  try {
    [files, pageCounts, currentStatus] = await Promise.all([
      api('/api/files'),
      api('/api/pagecounts'),
      api('/api/status')
    ]);
    render();
  } catch(err) { toast('Could not load files', 'error'); }
}

async function loadStatus() {
  if (renaming) return;
  try {
    currentStatus = await api('/api/status');
    render();
  } catch(err) {}
}

async function controlDisplay(action) {
  try {
    await api('/api/control', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({action})
    });
    setTimeout(loadStatus, 150);
  } catch(err) { toast(err.message, 'error'); }
}

// ── Delete ────────────────────────────────────────────────────────────────────
async function deleteFile(name) {
  if (!confirm(`Delete "${name}"?`)) return;
  try {
    const d = await api(`/api/delete/${encodeURIComponent(name)}`, {method:'DELETE'});
    files = d.order; render();
    toast(`Deleted ${name}`);
  } catch(err) { toast(err.message, 'error'); }
}

// ── Upload ────────────────────────────────────────────────────────────────────
const dropZone    = document.getElementById('drop-zone');
const fileInput   = document.getElementById('file-input');
const progressBar = document.getElementById('progress-bar');
const progressFill = document.getElementById('progress-fill');

dropZone.addEventListener('click', () => fileInput.click());
dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('dragover'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
dropZone.addEventListener('drop', e => {
  e.preventDefault(); dropZone.classList.remove('dragover');
  uploadFiles(e.dataTransfer.files);
});
fileInput.addEventListener('change', () => uploadFiles(fileInput.files));

async function uploadFiles(fileList) {
  if (!fileList.length) return;
  const form = new FormData();
  let count = 0;
  for (const f of fileList) {
    if (f.name.toLowerCase().endsWith('.pdf')) { form.append('files', f); count++; }
  }
  if (!count) { toast('Only PDF files are accepted', 'error'); return; }

  progressBar.style.display = 'block';
  progressFill.style.width = '30%';

  try {
    const xhr = new XMLHttpRequest();
    await new Promise((res, rej) => {
      xhr.upload.onprogress = e => {
        if (e.lengthComputable)
          progressFill.style.width = (30 + 65 * e.loaded / e.total) + '%';
      };
      xhr.onload = () => {
        if (xhr.status < 300) res(JSON.parse(xhr.responseText));
        else rej(new Error(xhr.statusText));
      };
      xhr.onerror = () => rej(new Error('Network error'));
      xhr.open('POST', '/api/upload');
      xhr.send(form);
    });
    progressFill.style.width = '100%';
    await loadFiles();
    toast(`Uploaded ${count} file${count>1?'s':''}`);
    setTimeout(() => { progressBar.style.display='none'; progressFill.style.width='0'; }, 600);
  } catch(err) {
    toast(err.message, 'error');
    progressBar.style.display = 'none';
  }
  fileInput.value = '';
}

// ── Blank Slide dialog ────────────────────────────────────────────────────────
const overlay      = document.getElementById('blank-dialog-overlay');
const addBlankBtn  = document.getElementById('add-blank-btn');
const blankCancel  = document.getElementById('blank-cancel');
const blankConfirm = document.getElementById('blank-confirm');
const blankLabel   = document.getElementById('blank-label');
const blankPos     = document.getElementById('blank-position');
const prevBtn      = document.getElementById('prev-btn');
const nextBtn      = document.getElementById('next-btn');

prevBtn.addEventListener('click', () => controlDisplay('prev'));
nextBtn.addEventListener('click', () => controlDisplay('next'));

function openBlankDialog() {
  // Populate position select
  blankPos.innerHTML = '<option value="-1">— end of queue —</option>' +
    files.map((f, i) => `<option value="${i}">After: ${f}</option>`).join('');
  blankLabel.value = '';
  overlay.classList.add('open');
  blankLabel.focus();
}

function closeBlankDialog() {
  overlay.classList.remove('open');
}

addBlankBtn.addEventListener('click', openBlankDialog);
blankCancel.addEventListener('click', closeBlankDialog);
overlay.addEventListener('click', e => { if (e.target === overlay) closeBlankDialog(); });

blankLabel.addEventListener('keydown', e => {
  if (e.key === 'Enter') blankConfirm.click();
  if (e.key === 'Escape') closeBlankDialog();
});

blankConfirm.addEventListener('click', async () => {
  const label = blankLabel.value.trim();
  const after = parseInt(blankPos.value, 10);
  closeBlankDialog();
  try {
    const d = await api('/api/blank', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({label, after})
    });
    files = d.order;
    await loadFiles();
    toast(`Blank slide inserted: ${d.created}`);
  } catch(err) { toast(err.message, 'error'); }
});

// ── Poll for changes every 5s ─────────────────────────────────────────────────
loadFiles();
setInterval(loadStatus, 1000);
setInterval(loadFiles, 5000);
</script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML, username=current_username(), is_admin=is_admin_user())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
