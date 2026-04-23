#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import http.server
import socketserver
import urllib.parse
import secrets
import time
import html
import hashlib
import os

PORT = 8080

# --- Demo-only initial user (do NOT use in production) ---
DEMO_USERNAME = "admin"
DEMO_PASSWORD = "redflags!"

# In-memory user store: { username_lower: {"username": str, "salt": bytes, "pwd": bytes, "created": ts} }
USERS = {}

# In-memory session store: { session_id: {"username": str, "created": ts} }
SESSIONS = {}

# In-memory incidents: { username_lower: [ {id:int, ts:float, character:str, severity:int, tags:list[str], notes:str} ] }
INCIDENTS = {}

MAX_POST_BYTES = 16 * 1024  # 16 KiB

# ---------- Password hashing (demo) ----------

def hash_password(password: str, salt: bytes = None):
    """Hash password with scrypt; returns (salt, hash)."""
    if salt is None:
        salt = os.urandom(16)
    pwd = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=64)
    return salt, pwd

def verify_password(password: str, salt: bytes, expected_hash: bytes) -> bool:
    try:
        computed = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=64)
        return secrets.compare_digest(computed, expected_hash)
    except Exception:
        return False

def ensure_demo_user():
    if DEMO_USERNAME.lower() not in USERS:
        salt, pwd = hash_password(DEMO_PASSWORD)
        USERS[DEMO_USERNAME.lower()] = {
            "username": DEMO_USERNAME,
            "salt": salt,
            "pwd": pwd,
            "created": time.time(),
        }

# ---------- HTML Templates ----------

def red_flag_svg(size=28, fill="#ff2b2b", extra_class=""):
    """A simple red flag SVG icon."""
    return f'''
    <svg class="{extra_class}" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M6 2v20M6 3h9.2a1 1 0 0 1 .63 1.78L13 8l2.83 2.22A1 1 0 0 1 15.2 12H6"
            stroke="{fill}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
    '''

def page_shell(title, body, extra_head=""):
    """Global page shell with vibrant background and floating flags."""
    flags = "".join(
        red_flag_svg(size=36, fill="#ff2b2b", extra_class=f"flag flag-{i}")
        for i in range(1, 10)
    )
    # Randomized CSS for the floating flags
    random_css = ''.join(
        f'.flag-{i} {{ left: {i*9 % 100}vw; animation-delay: -{i*1.7:.1f}s; animation-duration: {10 + (i%5)}s; }}'
        for i in range(1, 10)
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{title}</title>
<link rel="icon" type="image/svg+xml" href="/favicon.svg"/>
<style>
  :root {{
    --bg1: #0f0c29;
    --bg2: #302b63;
    --bg3: #24243e;
    --card: rgba(255,255,255,0.10);
    --card-border: rgba(255,255,255,0.22);
    --text: #f7f7ff;
    --muted: #c7c7d1;
    --accent: #ff2b2b;
    --accent-2: #ff5f6d;
  }}

  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    min-height: 100dvh;
    font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, "Apple Color Emoji", "Segoe UI Emoji";
    color: var(--text);
    background: linear-gradient(135deg, var(--bg1), var(--bg2) 40%, var(--bg3));
    display: grid;
    place-items: center;
    overflow: hidden;
  }}

  /* Floating red flags background */
  .flags {{
    position: fixed;
    inset: 0;
    overflow: hidden;
    z-index: 0;
    pointer-events: none;
    opacity: 0.22;
  }}
  .flag {{
    position: absolute;
    animation: floatY 12s linear infinite, sway 4.5s ease-in-out infinite;
    filter: drop-shadow(0 6px 8px rgba(0,0,0,0.35));
  }}
  @keyframes floatY {{
    0% {{ transform: translateY(110vh) }}
    100% {{ transform: translateY(-20vh) }}
  }}
  @keyframes sway {{
    0%, 100% {{ transform: translateX(0) rotate(-4deg); }}
    50% {{ transform: translateX(16px) rotate(4deg); }}
  }}

  {random_css}

  .container {{
    position: relative;
    z-index: 1;
    width: min(92vw, 820px);
    margin: 4vh auto;
  }}

  .brand {{
    display: flex;
    align-items: center;
    gap: 12px;
    justify-content: center;
    margin-bottom: 18px;
    text-shadow: 0 2px 14px rgba(0,0,0,0.35);
  }}
  .brand-title {{
    font-weight: 800;
    letter-spacing: 0.4px;
    font-size: 1.15rem;
    text-transform: uppercase;
    color: #ffd1d6;
  }}

  .card {{
    backdrop-filter: blur(10px);
    background: var(--card);
    border: 1px solid var(--card-border);
    border-radius: 18px;
    padding: 22px;
    box-shadow: 0 10px 30px rgba(0,0,0,0.35), inset 0 0 0 1px rgba(255,255,255,0.06);
  }}

  .title {{
    margin: 4px 0 16px 0;
    font-size: 1.5rem;
    font-weight: 800;
    line-height: 1.1;
  }}
  .subtitle {{
    margin: 0 0 18px 0;
    color: var(--muted);
    font-size: 0.95rem;
  }}

  form {{
    display: grid;
    gap: 14px;
  }}
  label {{
    font-size: 0.9rem;
  }}
  .field {{
    display: grid;
    gap: 8px;
  }}
  input[type="text"], input[type="password"], textarea, select {{
    width: 100%;
    padding: 12px 14px;
    border-radius: 12px;
    border: 1px solid rgba(255,255,255,0.25);
    background: rgba(0,0,0,0.25);
    color: var(--text);
    outline: none;
    transition: border-color .15s, box-shadow .15s, background .15s;
  }}
  textarea {{ min-height: 90px; resize: vertical; }}
  input::placeholder, textarea::placeholder {{ color: #e9e9f3cc; }}
  input:focus, textarea:focus, select:focus {{
    border-color: var(--accent-2);
    box-shadow: 0 0 0 4px rgba(255,95,109,0.20);
    background: rgba(0,0,0,0.35);
  }}

  .btn {{
    cursor: pointer;
    padding: 12px 16px;
    border: none;
    border-radius: 12px;
    background: linear-gradient(135deg, var(--accent), var(--accent-2));
    color: white;
    font-weight: 700;
    letter-spacing: .3px;
    transition: transform .06s ease, box-shadow .2s ease;
    box-shadow: 0 10px 20px rgba(255, 43, 43, 0.3);
    text-align: center;
  }}
  .btn:hover {{ transform: translateY(-1px); }}
  .btn:active {{ transform: translateY(1px); }}

  .row {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    flex-wrap: wrap;
  }}

  .helper {{ font-size: 0.85rem; color: var(--muted); }}
  .error {{
    background: rgba(255, 43, 43, 0.15);
    border: 1px solid rgba(255, 43, 43, 0.45);
    color: #ffe8ea;
    padding: 10px 12px;
    border-radius: 12px;
    margin-bottom: 8px;
  }}

  .footer-note {{ margin-top: 14px; text-align: center; font-size: 0.85rem; color: var(--muted); }}
  .mini-flag {{ vertical-align: middle; margin-right: 6px; }}

  a.link {{ color: #ffd1d6; text-decoration: none; }}
  a.link:hover {{ text-decoration: underline; }}

  /* incidents */
  .incidents {{ display: grid; gap: 10px; margin-top: 10px; }}
  .incident {{ border-radius: 14px; padding: 14px; border: 1px solid rgba(255,255,255,0.18); background: rgba(255,255,255,0.06); }}
  .incident .top {{ display: flex; gap: 10px; align-items: baseline; justify-content: space-between; }}
  .tag {{ display: inline-block; padding: 3px 8px; border-radius: 999px; background: rgba(255,95,109,0.25); border: 1px solid rgba(255,95,109,0.5); margin-right: 6px; font-size: 0.8rem; }}
  .pill {{ display:inline-flex; align-items:center; gap:6px; padding:3px 8px; border-radius:999px; background: rgba(255,255,255,0.08); font-size:0.8rem; }}
</style>
{extra_head}
</head>
<body>
<div class="flags" aria-hidden="true">
  {flags}
</div>
<div class="container">
  {body}
</div>
</body>
</html>
"""

def login_page(error_msg=None, username_prefill=""):
    error_html = f'<div class="error">🚩 {html.escape(error_msg)}</div>' if error_msg else ""
    brand_icon = red_flag_svg(size=28, fill="#ff4d4d", extra_class="mini-flag")
    body = f"""
      <div class="brand">{brand_icon}<div class="brand-title">Drama Red Flag Tracker</div></div>
      <div class="card">
        <h1 class="title">Log In</h1>
        <p class="subtitle">Spot the 🚩 early—sign in to manage patterns before they become plot twists.</p>
        {error_html}
        <form action="/login" method="post" autocomplete="on" novalidate>
          <div class="field">
            <label for="username">Username</label>
            <input id="username" name="username" type="text" placeholder="Enter username" value="{html.escape(username_prefill)}" required>
          </div>
          <div class="field">
            <label for="password">Password</label>
            <input id="password" name="password" type="password" placeholder="Enter password" required>
          </div>
          <div class="row">
            <div class="helper">Hint: try <strong>admin</strong> / <strong>redflags!</strong></div>
            <button class="btn" type="submit">Sign in {red_flag_svg(size=20, fill="#fff")}</button>
          </div>
        </form>
        <div class="footer-note">New here? <a class="link" href="/register">Create an account</a>.</div>
      </div>
    """
    return page_shell("Login • Drama Red Flag Tracker", body)

def register_page(error_msg=None, username_prefill=""):
    error_html = f'<div class="error">🚩 {html.escape(error_msg)}</div>' if error_msg else ""
    brand_icon = red_flag_svg(size=28, fill="#ff4d4d", extra_class="mini-flag")
    body = f"""
      <div class="brand">{brand_icon}<div class="brand-title">Drama Red Flag Tracker</div></div>
      <div class="card">
        <h1 class="title">Create Account</h1>
        <p class="subtitle">Join to start tracking 🚩 indicators across scenarios.</p>
        {error_html}
        <form action="/register" method="post" autocomplete="on" novalidate>
          <div class="field">
            <label for="username">Username</label>
            <input id="username" name="username" type="text" placeholder="Choose a username" value="{html.escape(username_prefill)}" required>
          </div>
          <div class="field">
            <label for="password">Password</label>
            <input id="password" name="password" type="password" placeholder="Create a password" required>
          </div>
          <div class="field">
            <label for="password2">Confirm Password</label>
            <input id="password2" name="password2" type="password" placeholder="Re-enter password" required>
          </div>
          <div class="row">
            <div class="helper">Use at least 8 characters.</div>
            <button class="btn" type="submit">Create account</button>
          </div>
        </form>
        <div class="footer-note">Already have an account? <a class="link" href="/login">Log in</a>.</div>
      </div>
    """
    return page_shell("Register • Drama Red Flag Tracker", body)

def dashboard_page(username):
    safe_user = html.escape(username)
    body = f"""
      <div class="brand">{red_flag_svg(size=28, fill="#ff4d4d", extra_class="mini-flag")}<div class="brand-title">Drama Red Flag Tracker</div></div>
      <div class="card">
        <h1 class="title">Welcome, {safe_user}!</h1>
        <p class="subtitle">You’re in. Track 🚩 incidents across characters, conversations, and timelines.</p>
        <div class="row">
          <a class="btn" href="/incidents/new">Add incident</a>
          <a class="btn" href="/incidents">View incidents</a>
          <a class="btn" href="/logout">Log out</a>
        </div>
        <div class="helper" style="margin-top:10px;">Tip: Start by adding your first character + incident.</div>
      </div>
    """
    return page_shell("Dashboard • Drama Red Flag Tracker", body)

def incident_form_page(error_msg=None, values=None):
    vals = values or {}
    character = html.escape(vals.get("character", ""))
    severity = html.escape(str(vals.get("severity", "3")))
    tags = html.escape(vals.get("tags", "jealousy, gaslighting, blame-shifting"))
    notes = html.escape(vals.get("notes", ""))
    show = html.escape(vals.get("show", ""))
    category = html.escape(vals.get("category", ""))
    error_html = f'<div class="error">🚩 {html.escape(error_msg)}</div>' if error_msg else ""
    brand_icon = red_flag_svg(size=28, fill="#ff4d4d", extra_class="mini-flag")
    body = f"""
      <div class="brand">{brand_icon}<div class="brand-title">Drama Red Flag Tracker</div></div>
      <div class="card">
        <h1 class="title">Add Red Flag Incident</h1>
        <p class="subtitle">Capture the moment while it’s fresh.</p>
        {error_html}
        <form action="/incidents/new" method="post" novalidate>
          <div class="field">
            <label for="character">Character *</label>
            <input id="character" name="character" type="text" placeholder="e.g., Cassian" value="{character}" required>
          </div>
          <div class="field">
            <label for="severity">Severity (1 = mild, 5 = extreme) *</label>
            <select id="severity" name="severity" required>
              {"".join(f'<option value="{i}"{" selected" if str(i)==severity else ""}>{i}</option>' for i in range(1,6))}
            </select>
          </div>
          <div class="field">
            <label for="tags">Tags (comma-separated)</label>
            <input id="tags" name="tags" type="text" placeholder="e.g., jealousy, gaslighting" value="{tags}">
          </div>
          <div class="field">
            <label for="notes">Notes</label>
            <textarea id="notes" name="notes" placeholder="What happened? Include timing, context, quotes if needed.">{notes}</textarea>
          </div>
          <div class="field">
          <label for="show">Show</label>
          <input id="show" name="show" type="text" placeholder="e.g., House of the Dragon" value="{show}">
          </div>
          <div class="field">
          <label for="category">Category (comma-separated)</label>
          <input id="category" name="category" type="text" placeholder="e.g., romance, betrayal" value="{category}">
          </div>
          <div class="row">
            <a class="btn" href="/incidents" style="background:rgba(255,255,255,0.12); border:1px solid rgba(255,255,255,0.2);">Back to list</a>
            <button class="btn" type="submit">Save incident</button>
          </div>
        </form>
      </div>
    """
    return page_shell("New Incident • Drama Red Flag Tracker", body)

def incidents_list_page(username, incidents, filter_character=""):
    safe_user = html.escape(username)
    filt = filter_character.strip()
    filt_safe = html.escape(filt)
    subtitle = f"Viewing incidents for {safe_user}" + (f" • Filter: {filt_safe}" if filt else "")
    items_html = []
    if not incidents:
        items_html.append('<div class="helper">No incidents yet. Add your first one!</div>')
    else:
        for inc in incidents:
            t = time.strftime("%Y-%m-%d %H:%M", time.localtime(inc["ts"]))
            character = html.escape(inc["character"])
            notes = html.escape(inc.get("notes",""))
            tags = inc.get("tags", [])
            severity = inc.get("severity", 3)
            show = html.escape(inc.get("show", ""))
            categories = inc.get("categories", [])
            tag_html = " ".join(f'<span class="tag">{html.escape(tag)}</span>' for tag in tags)
            items_html.append(f"""
            <div style="margin-top:6px;">
            <span class="pill">📺 {show or "—"}</span>
            {" ".join(f'<span class="tag">{html.escape(c)}</span>' for c in categories)}
             </div>
              <div class="incident">
                <div class="top">
                  <div>
                    <span class="pill">🚩 Severity {severity}</span>
                    <strong style="margin-left:8px;">{character}</strong>
                  </div>
                  <div class="helper">{t}</div>
                </div>
                <div style="margin-top:8px;">{tag_html}</div>
                <div style="margin-top:8px; white-space:pre-wrap;">{notes}</div>
              </div>
            """)

    filter_form = f"""
      <form action="/incidents" method="get" style="grid-template-columns:1fr auto; align-items:end;">
        <div class="field">
          <label for="character">Filter by character</label>
          <input id="character" name="character" type="text" placeholder="e.g., Cassian" value="{filt_safe}">
        </div>
        <div class="field">
        <label for="show">Show</label>
         <input id="show" name="show" type="text" placeholder="e.g., House of the Dragon" value="{html.escape(show_filter)}">
         </div>
         <div class="field">
         <label for="category">Category</label>
         <input id="category" name="category" type="text" placeholder="e.g., betrayal" value="{html.escape(category_filter)}">
         </div>
        <div class="row" style="gap:8px;">
          <button class="btn" type="submit">Apply</button>
          <a class="btn" href="/incidents" style="background:rgba(255,255,255,0.12); border:1px solid rgba(255,255,255,0.2);">Clear</a>
          <a class="btn" href="/incidents/new">Add incident</a>
          <a class="btn" href="/dashboard">Dashboard</a>
        </div>
      </form>
    """

    body = f"""
      <div class="brand">{red_flag_svg(size=28, fill="#ff4d4d", extra_class="mini-flag")}<div class="brand-title">Drama Red Flag Tracker</div></div>
      <div class="card">
        <h1 class="title">Incidents</h1>
        <p class="subtitle">{subtitle}</p>
        {filter_form}
        <div class="incidents">
          {''.join(items_html)}
        </div>
      </div>
    """
    return page_shell("Incidents • Drama Red Flag Tracker", body)

# ---------- Utilities ----------

def parse_cookies(cookie_header):
    cookies = {}
    if not cookie_header:
        return cookies
    for part in cookie_header.split(";"):
        if "=" in part:
            k, v = part.strip().split("=", 1)
            cookies[k] = v
    return cookies

def get_authenticated_username(handler):
    cookies = parse_cookies(handler.headers.get("Cookie"))
    sid = cookies.get("session_id")
    if not sid:
        return None
    session = SESSIONS.get(sid)
    if not session:
        return None
    return session.get("username")

def create_session(handler, username: str):
    session_id = secrets.token_urlsafe(24)
    SESSIONS[session_id] = {"username": username, "created": time.time()}
    handler.send_header("Set-Cookie", f"session_id={session_id}; HttpOnly; Path=/; SameSite=Lax")  # add ; Secure when on HTTPS

def get_user_incidents(username: str):
    return INCIDENTS.setdefault(username.lower(), [])

# ---------- HTTP Handler ----------

class RedFlagHandler(http.server.BaseHTTPRequestHandler):
    server_version = "RedFlagHTTP/1.0"

    def do_GET(self):
        ensure_demo_user()

        if self.path == "/" or self.path.startswith("/login"):
            self.respond_html(login_page())
            return

        if self.path == "/register":
            self.respond_html(register_page())
            return

        if self.path == "/dashboard":
            username = get_authenticated_username(self)
            if not username:
                self.redirect("/")
                return
            self.respond_html(dashboard_page(username))
            return

        if self.path.startswith("/incidents"):
            username = get_authenticated_username(self)
            if not username:
                self.redirect("/")
                return

            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/incidents/new":
                self.respond_html(incident_form_page())
                return

            if parsed.path == "/incidents":
                params = urllib.parse.parse_qs(parsed.query or "")
                character_filter = (params.get("character", [""])[0] or "").strip().lower()
                show_filter = (params.get("show", [""])[0] or "").strip().lower()
                category_filter = (params.get("category", [""])[0] or "").strip().lower()
                all_inc = list(get_user_incidents(username))
                if character_filter:
                  all_inc = [i for i in all_inc if i["character"].lower() == character_filter]
                  
                  if show_filter:
                    all_inc = [i for i in all_inc if i.get("show", "").lower() == show_filter]
                    if category_filter:
                      all_inc = [i for i in all_inc if category_filter in [c.lower() for c in i.get("categories", [])]]
                # Show newest first
                all_inc.sort(key=lambda x: x["ts"], reverse=True)
                self.respond_html(incidents_list_page(username, all_inc, filter_character=filt))
                return

        if self.path == "/logout":
            self.clear_session_and_redirect("/")
            return

        if self.path == "/favicon.svg":
            self.respond_svg_favicon()
            return

        self.respond_not_found()

    def do_POST(self):
        ensure_demo_user()
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0 or length > MAX_POST_BYTES:
            self.respond_not_found()
            return
        body_bytes = self.rfile.read(length)
        try:
            data = urllib.parse.parse_qs(body_bytes.decode("utf-8"))
        except UnicodeDecodeError:
            self.respond_not_found()
            return

        path = self.path

        if path == "/login":
            username = (data.get("username", [""])[0] or "").strip()
            password = (data.get("password", [""])[0] or "")
            user_rec = USERS.get(username.lower())
            if user_rec and verify_password(password, user_rec["salt"], user_rec["pwd"]):
                self.send_response(302)
                self.send_header("Location", "/dashboard")
                create_session(self, user_rec["username"])
                self.end_headers()
            else:
                error = "Invalid credentials. That’s a 🚩—try again."
                self.respond_html(login_page(error_msg=error, username_prefill=username))
            return

        if path == "/register":
            username = (data.get("username", [""])[0] or "").strip()
            password = (data.get("password", [""])[0] or "")
            password2 = (data.get("password2", [""])[0] or "")

            if not username or not password or not password2:
                self.respond_html(register_page(error_msg="All fields are required.", username_prefill=username))
                return
            if password != password2:
                self.respond_html(register_page(error_msg="Passwords do not match.", username_prefill=username))
                return
            if len(password) < 8:
                self.respond_html(register_page(error_msg="Password must be at least 8 characters.", username_prefill=username))
                return
            if not username.isascii() or any(c.isspace() for c in username):
                self.respond_html(register_page(error_msg="Username must be ASCII and contain no spaces.", username_prefill=username))
                return
            uname_key = username.lower()
            if uname_key in USERS:
                self.respond_html(register_page(error_msg="That username is already taken.", username_prefill=username))
                return

            salt, pwd_hash = hash_password(password)
            USERS[uname_key] = {
                "username": username,
                "salt": salt,
                "pwd": pwd_hash,
                "created": time.time(),
            }
            self.send_response(302)
            self.send_header("Location", "/dashboard")
            create_session(self, username)
            self.end_headers()
            return

        if path == "/incidents/new":
            username = get_authenticated_username(self)
            if not username:
                self.redirect("/")
                return

            character = (data.get("character", [""])[0] or "").strip()
            severity_raw = (data.get("severity", [""])[0] or "").strip()
            tags_raw = (data.get("tags", [""])[0] or "")
            notes = (data.get("notes", [""])[0] or "").strip()
            show = (data.get("show", [""])[0] or "").strip()
            category_raw = (data.get("category", [""])[0] or "")
            categories = [c.strip() for c in category_raw.split(",") if c.strip()]

            # Basic validation
            if not character:
                self.respond_html(incident_form_page(error_msg="Character is required.", values={
                    "character": character, "severity": severity_raw, "tags": tags_raw, "notes": notes
                }))
                return
            try:
                severity = int(severity_raw)
                if severity < 1 or severity > 5:
                    raise ValueError()
            except ValueError:
                self.respond_html(incident_form_page(error_msg="Severity must be an integer 1–5.", values={
                    "character": character, "severity": severity_raw, "tags": tags_raw, "notes": notes
                }))
                return

            tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
            record = {
              "id": self._next_incident_id(username),
              "ts": time.time(),
              "character": character,
              "severity": severity,
              "tags": tags,
              "notes": notes,
              "show": show,
              "categories": categories,
              }
            get_user_incidents(username).append(record)

            # Redirect to list (PRG pattern)
            self.send_response(303)  # See Other
            self.send_header("Location", "/incidents")
            self.end_headers()
            return

        self.respond_not_found()

    # --- Helpers ---
    def _next_incident_id(self, username):
        user_key = username.lower()
        items = INCIDENTS.setdefault(user_key, [])
        return (items[-1]["id"] + 1) if items else 1

    def clear_session_and_redirect(self, path="/"):
        cookies = parse_cookies(self.headers.get("Cookie"))
        sid = cookies.get("session_id")
        if sid and sid in SESSIONS:
            del SESSIONS[sid]
        self.send_response(302)
        self.send_header("Location", path)
        self.send_header("Set-Cookie", "session_id=deleted; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT; SameSite=Lax; HttpOnly")
        self.end_headers()

    def redirect(self, path="/"):
        self.send_response(302)
        self.send_header("Location", path)
        self.end_headers()

    def respond_html(self, html_text):
        data = html_text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def respond_not_found(self):
        self.send_response(404)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"404 Not Found")

    def respond_svg_favicon(self):
        svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <defs>
    <linearGradient id="g" x1="0" x2="1" y1="0" y2="1">
      <stop offset="0%" stop-color="#ff2b2b"/>
      <stop offset="100%" stop-color="#ff5f6d"/>
    </linearGradient>
  </defs>
  <rect width="64" height="64" rx="12" fill="#1b153a"/>
  <path d="M18 10v44M18 12h28a2 2 0 0 1 1.3 3.56L36 24l11.3 8.9A2 2 0 0 1 46 36H18"
        stroke="url(#g)" stroke-width="6" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
</svg>
"""
        data = svg.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
        self.send_header("Cache-Control", "max-age=86400")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # Quiet default logging a bit
    def log_message(self, format, *args):
        # return super().log_message(format, *args)
        pass

# ---------- Server ----------

def run():
    with socketserver.TCPServer(("", PORT), RedFlagHandler) as httpd:
        print(f"🚩 Drama Red Flag Tracker server running at http://localhost:{PORT}")
        print("   Demo user: admin | Password: redflags!")
        httpd.serve_forever()

if __name__ == "__main__":
    run()