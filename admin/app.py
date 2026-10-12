"""Photo app: serves /photography/* (rendered at request time from photos/)
and the /admin tool for adding, editing and deleting photos.

Adding or changing a photo only ever writes photos/<slug>.md and the image
next to it - no site rebuild. The page chrome (header, nav, footer, CSS) is
the Hugo-built shell at public/photography/index.html, filled in per request.
"""
import os
import re
import subprocess
import time
import unicodedata
from datetime import date

from flask import (Flask, abort, jsonify, redirect, render_template_string,
                   request, send_file, session)
from markupsafe import escape
from werkzeug.middleware.proxy_fix import ProxyFix

import photos

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
app.secret_key = os.environ["ADMIN_SECRET"]
ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]

app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    MAX_CONTENT_LENGTH=40 * 1024 * 1024,  # 40MB per upload
)

REPO = photos.REPO
SITE_URL = "https://benkyd.co.uk"
SITE_TITLE = "Ben Kyd"
SHELL = os.environ.get("PHOTO_SHELL", os.path.join(REPO, "public", "photography", "index.html"))

# Very small in-memory login rate limit: 5 failed attempts from one
# source IP locks that IP out for 60s. Resets if the process restarts -
# that's fine, this is a deterrent against casual password guessing, not
# a defense against a serious distributed attacker (there is nothing
# juicy enough behind this login to be worth one).
_failed_logins = {}  # ip -> (count, locked_until_ts)
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 60


# ---------------------------------------------------------------- public ----

_shell_cache = {"mtime": None, "html": ""}


def shell():
    mtime = os.path.getmtime(SHELL)
    if _shell_cache["mtime"] != mtime:
        with open(SHELL) as f:
            _shell_cache.update(mtime=mtime, html=f.read())
    return _shell_cache["html"]


def render_page(main, title, description, path, extra_head=""):
    url = SITE_URL + path
    html = shell()
    swaps = [
        (r"<title>[^<]*</title>", f"<title>{escape(title)} | {SITE_TITLE}</title>"),
        (r'<meta name="?description"?[^>]*>', f'<meta name="description" content="{escape(description)}">'),
        (r'<link rel="?canonical"?[^>]*>', f'<link rel="canonical" href="{escape(url)}">'),
        (r'<meta name="?photo-head"?[^>]*>', render_template_string(
            HEAD_TMPL, title=title, description=description, url=url,
            site_title=SITE_TITLE) + extra_head),
        (r'<div id="?photo-main"?></div>', main),
    ]
    for pattern, new in swaps:
        html, n = re.subn(pattern, lambda _m, new=new: str(new), html, count=1)
        if not n:
            app.logger.error("photo shell is missing %r - rebuild the site", pattern)
            abort(500)
    return html


def absolute(path):
    return SITE_URL + path


HEAD_TMPL = """<meta property="og:url" content="{{ url }}">
<meta property="og:site_name" content="{{ site_title }}">
<meta property="og:title" content="{{ title }}">
<meta property="og:description" content="{{ description }}">
<meta name="twitter:title" content="{{ title }}">
<meta name="twitter:description" content="{{ description }}">"""

GALLERY_TMPL = """<header class="page-header">
<div class="breadcrumbs"><a href="{{ site }}/">Home</a></div>
<h1>Photography</h1>
</header>
{% if photos %}
<div class="photo-grid">
{% for p in photos %}
<a href="/photography/{{ p.slug }}/" class="photo-tile photo-ph reveal" style="--ph:url({{ p.ph }})" aria-label="View full size: {{ p.alt }}">
<picture>
<source type="image/webp" srcset="{{ p.thumb_webp }} 1x, {{ p.thumb2x_webp }} 2x">
<img src="{{ p.thumb_jpg }}" srcset="{{ p.thumb_jpg }} 1x, {{ p.thumb2x_jpg }} 2x" alt="{{ p.alt }}" width="{{ p.w }}" height="{{ p.h }}" style="view-transition-name:p-{{ p.slug }}"
 {% if loop.index0 < 4 %}loading="eager"{% if loop.first %} fetchpriority="high"{% endif %}{% else %}loading="lazy"{% endif %} decoding="async">
</picture>
<span class="photo-tile-cap">{{ p.alt }}{% if p.when %}<small>{{ p.when }}</small>{% endif %}</span>
</a>
{% endfor %}
</div>
{% else %}
<p>No photos yet.</p>
{% endif %}"""

PHOTO_TMPL = """<header class="page-header">
<div class="breadcrumbs"><a href="{{ site }}/">Home</a>&nbsp;»&nbsp;<a href="{{ site }}/photography/">Photography</a></div>
</header>
<figure class="photo-single-figure">
<span class="photo-frame photo-ph" style="--ph:url({{ ph }})">
<picture>
<source type="image/webp" srcset="{{ full_webp }}">
<img src="{{ full_jpg }}" alt="{{ p.alt }}" width="{{ w }}" height="{{ h }}" style="view-transition-name:p-{{ p.slug }}" loading="eager" fetchpriority="high" decoding="async">
</picture>
</span>
<figcaption class="photo-single-caption">
<span class="photo-single-alt">{{ p.alt }}</span>
{% if when %}<span class="photo-single-when">{{ when }}</span>{% endif %}
{% if chips %}<span class="photo-chips">{% for c in chips %}<span class="photo-chip">{{ c }}</span>{% endfor %}</span>{% endif %}
</figcaption>
</figure>
{% for para in paragraphs %}<p class="photo-single-body">{{ para }}</p>{% endfor %}
<nav class="photo-single-nav">
{% if newer %}<a class="photo-single-prev" href="/photography/{{ newer.slug }}/">&lsaquo;&nbsp;Previous</a>{% endif %}
<a class="photo-single-up" href="/photography/">Back to Photography</a>
<span class="photo-single-hint" aria-hidden="true">Use &larr; &rarr; to browse</span>
{% if older %}<a class="photo-single-next" href="/photography/{{ older.slug }}/">Next&nbsp;&rsaquo;</a>{% endif %}
</nav>"""

IMAGE_META_TMPL = """
<meta property="og:type" content="{{ og_type }}">
<meta property="og:image" content="{{ image }}">
<meta property="og:image:width" content="{{ w }}">
<meta property="og:image:height" content="{{ h }}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="{{ image }}">"""


def month_year(value):
    try:
        y, m = value[:7].split("-")
        return date(int(y), int(m), 1).strftime("%B %Y")
    except (ValueError, AttributeError):
        return ""


def when_line(p):
    return " · ".join(x for x in (p.get("location"), month_year(p.get("date", ""))) if x)


def describe(p):
    return f"{p['alt']} — {p['location']}" if p.get("location") else p["alt"]


def image_meta(p, og_type):
    w, h = photos.variant_size(p, "og")
    return render_template_string(
        IMAGE_META_TMPL, og_type=og_type, w=w, h=h,
        image=absolute(photos.variant_url(p, "og", "jpg")))


@app.errorhandler(404)
def not_found(_e):
    # the site's own 404 page rather than Flask's bare one
    try:
        with open(os.path.join(REPO, "public", "404.html")) as f:
            return f.read(), 404
    except OSError:
        return "Not found", 404


@app.route("/photography")
def gallery_slash():
    return redirect("/photography/", 301)


@app.route("/photography/")
def gallery():
    all_photos = photos.load_all()
    items = []
    for p in all_photos:
        w, h = photos.variant_size(p, "thumb")
        items.append(dict(slug=p["slug"], alt=p["alt"], when=when_line(p), w=w, h=h,
                          ph=photos.placeholder(p),
                          thumb_webp=photos.variant_url(p, "thumb", "webp"),
                          thumb_jpg=photos.variant_url(p, "thumb", "jpg"),
                          thumb2x_webp=photos.variant_url(p, "thumb2x", "webp"),
                          thumb2x_jpg=photos.variant_url(p, "thumb2x", "jpg")))
    extra = image_meta(all_photos[0], "website") if all_photos else ""
    main = render_template_string(GALLERY_TMPL, photos=items, site=SITE_URL)
    return render_page(main, "Photography", "Photography by Ben Kyd.", "/photography/", extra)


@app.route("/photography/<slug>")
def photo_slash(slug):
    if not photos.load(slug):
        abort(404)
    return redirect(f"/photography/{slug}/", 301)


@app.route("/photography/<slug>/")
def photo_page(slug):
    p = photos.load(slug)
    if not p:
        abort(404)
    ordered = photos.load_all()
    i = next(n for n, q in enumerate(ordered) if q["slug"] == slug)
    w, h = photos.variant_size(p, "full")
    when = when_line(p)
    main = render_template_string(
        PHOTO_TMPL, p=p, w=w, h=h, when=when, chips=photos.gear_chips(p), site=SITE_URL,
        ph=photos.placeholder(p),
        paragraphs=[x.strip() for x in p.get("body", "").split("\n\n") if x.strip()],
        full_webp=photos.variant_url(p, "full", "webp"),
        full_jpg=photos.variant_url(p, "full", "jpg"),
        newer=ordered[i - 1] if i > 0 else None,
        older=ordered[i + 1] if i + 1 < len(ordered) else None)
    return render_page(main, p["alt"], describe(p), f"/photography/{slug}/", image_meta(p, "article"))


@app.route("/photography/recent.json")
def recent():
    """Homepage data: a hero (the newest photo marked featured, else the
    newest photo) plus the next four for the "Recent photos" strip."""
    all_ = photos.load_all()
    if not all_:
        return jsonify(hero=None, photos=[])
    hero = next((p for p in all_ if p.get("featured")), all_[0])
    hw, hh = photos.variant_size(hero, "hero")
    out = []
    for p in [p for p in all_ if p is not hero][:4]:
        w, h = photos.variant_size(p, "teaser")
        out.append(dict(alt=p["alt"], slug=p["slug"], url=f"/photography/{p['slug']}/",
                        width=w, height=h, thumb=photos.variant_url(p, "teaser", "webp"),
                        thumb2x=photos.variant_url(p, "teaser2x", "webp"),
                        ph=photos.placeholder(p)))
    return jsonify(
        hero=dict(alt=hero["alt"], slug=hero["slug"], url=f"/photography/{hero['slug']}/",
                  when=when_line(hero), width=hw, height=hh,
                  src=photos.variant_url(hero, "hero", "webp"), ph=photos.placeholder(hero),
                  srcset=", ".join(f"{photos.variant_url(hero, v, 'webp')} {photos.variant_size(hero, v)[0]}w"
                                   for v in ("hero", "full"))),
        photos=out)


@app.route("/photography/img/<slug>/<variant>.<ext>")
def photo_image(slug, variant, ext):
    p = photos.load(slug)
    if not p or variant not in photos.VARIANTS or ext not in photos.FORMATS:
        abort(404)
    resp = send_file(photos.variant_file(p, variant, ext),
                     mimetype=photos.FORMATS[ext][1], max_age=31536000)
    resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return resp


# ----------------------------------------------------------------- admin ----

STYLE = """@font-face{font-family:Libron;src:url(/fonts/libron/Libron-Regular.woff2) format("woff2");font-weight:400}
@font-face{font-family:Libron;src:url(/fonts/libron/Libron-Bold.woff2) format("woff2");font-weight:700}
:root{--bg:#faf9f6;--card:#fdfcfa;--text:#1e1e1e;--muted:#6c6c6c;--line:#e6e3dc;--field:#fff;--accent:#b8406a;--on-accent:#fff}
@media (prefers-color-scheme:dark){:root{--bg:#1d1e20;--card:#2e2e33;--text:#dadadb;--muted:#9b9c9d;--line:#3a3a3f;--field:#232427;--accent:#ee8fb1;--on-accent:#1d1e20}}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:Libron,Georgia,serif;padding:1.5rem;min-height:100vh;line-height:1.5}
.wrap{max-width:900px;margin:0 auto}
h1{font-size:1.6rem;margin-bottom:1.25rem}
h2{font-size:1.15rem;margin:2.25rem 0 1rem}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:1.25rem;margin-bottom:1rem;max-width:520px;box-shadow:0 1px 2px rgba(0,0,0,.03)}
label{display:block;font-size:.85rem;color:var(--muted);margin-bottom:.3rem;margin-top:.9rem}
label:first-child{margin-top:0}
.hint{font-size:.8rem;color:var(--muted);margin-bottom:.5rem}
label.check{display:flex;align-items:center;gap:.5rem;color:var(--text);font-size:.95rem;margin-top:1rem;cursor:pointer}
label.check input{width:1.05rem;height:1.05rem;accent-color:var(--accent)}
.gear-row{display:grid;grid-template-columns:repeat(4,1fr);gap:.5rem;margin-top:.9rem}
input[type=file]::file-selector-button{font:inherit;font-size:.9rem;padding:.3rem .8rem;margin-right:.8rem;border:1px solid var(--line);border-radius:4px;background:var(--bg);color:var(--text);cursor:pointer}
.topbar{display:flex;gap:1rem;margin-bottom:1rem;font-size:.95rem}
.gear-row label{font-size:.75rem;white-space:nowrap}
input[type=text],input[type=month],input[type=password],input[type=file]{width:100%;padding:.55rem .75rem;background:var(--field);border:1px solid var(--line);border-radius:6px;color:var(--text);font:inherit;font-size:1rem}
input:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px color-mix(in srgb,var(--accent) 20%,transparent)}
.btn{width:100%;padding:.75rem;background:var(--accent);color:var(--on-accent);border:none;border-radius:6px;font:inherit;font-size:1rem;font-weight:700;cursor:pointer;margin-top:1.1rem}
.btn:hover{filter:brightness(1.07)}
.btn-danger{background:transparent;color:#c0392b;border:1px solid currentColor;margin-top:0}
.btn-ghost{background:transparent;border:1px solid var(--line);color:var(--muted)}
.status{padding:.75rem 1rem;border-radius:6px;margin-bottom:1rem;font-size:.95rem;max-width:520px}
.ok{background:rgba(34,140,80,.1);border:1px solid rgba(34,140,80,.35)}
.err{background:rgba(192,57,43,.1);border:1px solid rgba(192,57,43,.35)}
.login-wrap{max-width:340px;margin:12vh auto}
.section{font-size:1.05rem;font-weight:700;margin-top:1.6rem;margin-bottom:.2rem;padding-top:1rem;border-top:1px solid var(--line)}
a{color:var(--accent)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:12px}
.tile{display:block;border:1px solid var(--line);border-radius:8px;overflow:hidden;background:var(--card);color:var(--text);text-decoration:none;transition:box-shadow .2s,transform .2s}
.tile:hover{box-shadow:0 6px 20px rgba(0,0,0,.08);transform:translateY(-2px)}
.tile img{width:100%;aspect-ratio:1;object-fit:cover;display:block}
.tile .cap{padding:.5rem .6rem;font-size:.85rem}
img.preview{max-width:min(100%,520px);max-height:50vh;border-radius:8px;margin-bottom:1rem;display:block}
@media (max-width:480px){body{padding:1rem}.gear-row{grid-template-columns:repeat(2,1fr)}}"""

FIELDS_HTML = """<label>Caption / alt text</label>
<input type="text" name="alt" value="{{ p.alt }}" placeholder="A short description of the photo" required/>
<label>Location</label>
<input type="text" name="location" value="{{ p.location }}" placeholder="e.g. Les Deux Alpes, France"/>
<label>Date</label>
<input type="month" name="date" value="{{ p.month }}"/>
<label class="check"><input type="checkbox" name="featured" value="1"{% if p.featured %} checked{% endif %}/> Feature on the homepage</label>
<p class="hint">The newest featured photo is the big one at the top of the homepage. With none featured, the newest photo is used.</p>
<div class="section">Gear (optional)</div>
<p class="hint">Not read from the file - type what you shot it with.</p>
<label>Camera</label>
<input type="text" name="camera" list="cameras-list" value="{{ p.camera }}" placeholder="e.g. Hasselblad 500C"/>
<label>Lens</label>
<input type="text" name="lens" list="lenses-list" value="{{ p.lens }}" placeholder="e.g. 80mm f/2.8"/>
<div class="gear-row">
<div><label>Focal length</label><input type="text" name="focal_length" value="{{ p.focalLength }}" placeholder="50"/></div>
<div><label>Aperture</label><input type="text" name="aperture" value="{{ p.aperture }}" placeholder="5.6"/></div>
<div><label>Shutter</label><input type="text" name="shutter" value="{{ p.shutter }}" placeholder="1/1000"/></div>
<div><label>ISO</label><input type="text" name="iso" value="{{ p.iso }}" placeholder="100"/></div>
</div>
<label>Film stock</label>
<input type="text" name="film_stock" list="films-list" value="{{ p.filmStock }}" placeholder="e.g. Kodak Portra 400"/>
<datalist id="cameras-list">{% for c in gear.cameras %}<option value="{{ c }}">{% endfor %}</datalist>
<datalist id="lenses-list">{% for l in gear.lenses %}<option value="{{ l }}">{% endfor %}</datalist>
<datalist id="films-list">{% for fs in gear.films %}<option value="{{ fs }}">{% endfor %}</datalist>"""

TEMPLATE = """<!DOCTYPE html>
<html><head>
<meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Photography Admin</title>
<style>""" + STYLE + """</style></head><body><div class="wrap">
{% if not logged_in %}
<div class="login-wrap">
<h1>Photography Admin</h1>
{% if message %}<div class="status err">{{ message }}</div>{% endif %}
<form method="post" action="/admin/login">
<label>Password</label>
<input type="password" name="password" autofocus required/>
<button class="btn" type="submit">Sign In</button>
</form>
</div>
{% else %}
<p class="topbar"><a href="/photography/">&lsaquo; View the gallery</a></p>
<h1>Add a photo</h1>
{% if message %}<div class="status {{ 'ok' if ok else 'err' }}">{{ message | safe }}</div>{% endif %}
<form method="post" action="/admin/upload" enctype="multipart/form-data" class="card">
<label>Image (jpg / png / webp)</label>
<input type="file" name="image" accept=".jpg,.jpeg,.png,.webp" required/>
""" + FIELDS_HTML + """
<button class="btn" type="submit">Publish</button>
</form>

<h2>Existing photos ({{ photos|length }})</h2>
<div class="grid">
{% for q in photos %}
<a class="tile" href="/admin/edit/{{ q.slug }}">
  <img src="{{ q.thumb }}" alt=""/>
  <div class="cap">{{ q.alt }}</div>
</a>
{% endfor %}
</div>

<form method="post" action="/admin/logout" style="max-width:520px;margin-top:2rem">
<button class="btn btn-ghost" type="submit">Sign Out</button>
</form>
{% endif %}
</div></body></html>"""

EDIT_TEMPLATE = """<!DOCTYPE html>
<html><head>
<meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Edit photo - Photography Admin</title>
<style>""" + STYLE + """</style></head><body><div class="wrap">
<p class="topbar"><a href="/admin">&lsaquo; All photos</a><a href="/photography/{{ p.slug }}/">View on site</a></p>
<h1>Edit photo</h1>
{% if message %}<div class="status {{ 'ok' if ok else 'err' }}">{{ message | safe }}</div>{% endif %}
<img class="preview" src="{{ p.thumb }}" alt=""/>
<form method="post" action="/admin/edit/{{ p.slug }}" enctype="multipart/form-data" class="card">
<label>Replace image (optional)</label>
<input type="file" name="image" accept=".jpg,.jpeg,.png,.webp"/>
""" + FIELDS_HTML + """
<button class="btn" type="submit">Save</button>
</form>
<form method="post" action="/admin/delete/{{ p.slug }}" style="max-width:520px"
      onsubmit="return confirm('Delete this photo? This removes it from the live site.');">
<button class="btn btn-danger" type="submit">Delete this photo</button>
</form>
</div></body></html>"""

EMPTY = {"alt": "", "location": "", "month": "", "camera": "", "lens": "",
         "focalLength": "", "aperture": "", "shutter": "", "iso": "", "filmStock": "", "featured": ""}


def client_ip():
    return request.remote_addr or "unknown"


def require_login():
    return "admin" in session


def this_month():
    return date.today().strftime("%Y-%m")


def run(cmd):
    return subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=120)


def slugify(value):
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    return re.sub(r"[-_\s]+", "-", value).strip("-") or "photo"


def admin_photos():
    out = []
    for p in photos.load_all():
        q = dict(EMPTY, **{k: v for k, v in p.items() if isinstance(v, str)})
        q["month"] = p.get("date", "")[:7]
        q["thumb"] = photos.variant_url(p, "thumb", "webp")
        out.append(q)
    return out


def gear_history():
    """Previously-used camera/lens/film values, offered as dropdowns so repeat
    gear doesn't need retyping. Settings vary per shot, so no dropdown there."""
    all_ = photos.load_all()
    return {key: sorted({p[field] for p in all_ if p.get(field)})
            for key, field in (("cameras", "camera"), ("lenses", "lens"), ("films", "filmStock"))}


def render_index(message=None, ok=False):
    blank = dict(EMPTY, month=this_month())
    return render_template_string(TEMPLATE, logged_in=True, message=message, ok=ok,
                                  p=blank, photos=admin_photos(), gear=gear_history())


def render_edit(slug, message=None, ok=False):
    p = next((q for q in admin_photos() if q["slug"] == slug), None)
    if not p:
        return redirect("/admin")
    return render_template_string(EDIT_TEMPLATE, message=message, ok=ok, p=p, gear=gear_history())


def form_data(existing_date=""):
    """Front matter from the submitted form, or an error message."""
    f = request.form
    alt = (f.get("alt") or "").strip()
    if not alt:
        return None, "Caption / alt text is required."
    month = (f.get("date") or this_month()).strip()
    if not re.match(r"^\d{4}-\d{2}$", month):
        return None, "Invalid date."
    # Keep the exact day when the month is unchanged, so photos within the
    # same month keep their relative order.
    day = existing_date if existing_date[:7] == month else f"{month}-01"
    return {
        "alt": alt, "date": day,
        "location": (f.get("location") or "").strip(),
        "camera": (f.get("camera") or "").strip(),
        "lens": (f.get("lens") or "").strip(),
        "focalLength": (f.get("focal_length") or "").strip().removesuffix("mm"),
        "aperture": (f.get("aperture") or "").strip().removeprefix("f/"),
        "shutter": (f.get("shutter") or "").strip().removesuffix("s"),
        "iso": (f.get("iso") or "").strip().removeprefix("ISO").strip(),
        "filmStock": (f.get("film_stock") or "").strip(),
        "featured": "true" if f.get("featured") else "",
    }, None


def save_upload(file, slug):
    """Save an uploaded image as photos/<slug>.<ext>; (filename, error)."""
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in photos.ALLOWED_EXT:
        return None, "Only jpg, png or webp files are allowed."
    name = f"{slug}.{ext}"
    tmp = os.path.join(photos.PHOTOS_DIR, f".{name}.upload")
    file.save(tmp)
    if not photos.is_image(tmp):
        os.remove(tmp)
        return None, "That file isn't a readable image."
    os.replace(tmp, os.path.join(photos.PHOTOS_DIR, name))
    return name, None


def commit_push(slug, message):
    """Version the metadata. Images aren't in git - the host backup covers them."""
    if os.environ.get("PHOTO_NO_GIT"):  # test instances
        return ""
    run(["git", "add", "-A", "--", f"photos/{slug}.md"])
    commit = run(["git", "commit", "-q", "-m", message])
    out = (commit.stdout + commit.stderr).lower()
    if commit.returncode != 0 and "nothing to commit" not in out:
        return f" (live, but git commit failed: <pre>{escape(out[-400:])}</pre>)"
    push = run(["git", "push", "-q", "origin", "master"])
    if push.returncode != 0:
        return f" (live and committed, but push failed: <pre>{escape(push.stderr[-400:])}</pre>)"
    return ""


@app.route("/admin")
def index():
    if not require_login():
        return render_template_string(TEMPLATE, logged_in=False, message=None)
    return render_index()


@app.route("/admin/login", methods=["POST"])
def login():
    ip = client_ip()
    count, locked_until = _failed_logins.get(ip, (0, 0))
    now = time.time()
    if now < locked_until:
        return render_template_string(TEMPLATE, logged_in=False,
                                      message=f"Too many attempts. Try again in {int(locked_until - now)}s.")
    if request.form.get("password") == ADMIN_PASSWORD:
        _failed_logins.pop(ip, None)
        session.clear()
        session["admin"] = True
        return redirect("/admin")
    count += 1
    locked_until = time.time() + LOGIN_LOCKOUT_SECONDS if count >= LOGIN_MAX_ATTEMPTS else 0
    _failed_logins[ip] = (count, locked_until)
    msg = f"Too many attempts. Locked for {LOGIN_LOCKOUT_SECONDS}s." if locked_until else "Wrong password."
    return render_template_string(TEMPLATE, logged_in=False, message=msg)


@app.route("/admin/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect("/admin")


@app.route("/admin/upload", methods=["POST"])
def upload():
    if not require_login():
        return redirect("/admin")
    file = request.files.get("image")
    if not file or not file.filename:
        return render_index("No file selected.")
    data, err = form_data()
    if err:
        return render_index(err)

    base = slug = slugify(data["alt"])
    n = 2
    while os.path.exists(photos.md_path(slug)):
        slug, n = f"{base}-{n}", n + 1

    name, err = save_upload(file, slug)
    if err:
        return render_index(err)
    data["image"] = name
    photos.write(slug, data)
    note = commit_push(slug, f"Add photo: {data['alt']}")
    link = f"/photography/{slug}/"
    return render_index(f'Published: <a href="{link}">{escape(SITE_URL + link)}</a>{note}', ok=True)


@app.route("/admin/edit/<slug>")
def edit_form(slug):
    if not require_login():
        return redirect("/admin")
    return render_edit(slug)


@app.route("/admin/edit/<slug>", methods=["POST"])
def edit_save(slug):
    if not require_login():
        return redirect("/admin")
    p = photos.load(slug)
    if not p:
        return redirect("/admin")
    data, err = form_data(p.get("date", ""))
    if err:
        return render_edit(slug, err)
    data["image"] = p["image"]

    file = request.files.get("image")
    if file and file.filename:
        name, err = save_upload(file, slug)
        if err:
            return render_edit(slug, err)
        if name != p["image"]:
            os.remove(p["src"])
        data["image"] = name
        photos.purge_cache(slug)

    photos.write(slug, data, p.get("body", ""))
    note = commit_push(slug, f"Edit photo: {data['alt']}")
    return render_edit(slug, f"Saved.{note}", ok=True)


@app.route("/admin/delete/<slug>", methods=["POST"])
def delete(slug):
    if not require_login():
        return redirect("/admin")
    p = photos.load(slug)
    if not p:
        return redirect("/admin")
    os.remove(photos.md_path(slug))
    os.remove(p["src"])
    photos.purge_cache(slug)
    note = commit_push(slug, f"Delete photo: {p['alt']}")
    return render_index(f"Deleted.{note}", ok=True)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5002")))
