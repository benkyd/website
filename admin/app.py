"""Photo app: serves /photography/* (rendered at request time from photos/)
and /admin, the site admin: the photo library and the writing tool for blog
posts (templates/admin/, static/).

Adding or changing a photo only ever writes photos/<slug>.md and the image
next to it - no site rebuild. The page chrome (header, nav, footer, CSS) is
the Hugo-built shell at public/photography/index.html, filled in per request.
Posts are Hugo content (content/posts/), so publishing one rebuilds the site.
"""
import glob
import hashlib
import os
import random
import re
import subprocess
import time
import unicodedata
from datetime import date, datetime

from flask import (Flask, abort, jsonify, redirect, render_template,
                   render_template_string, request, send_file, session)
from markupsafe import escape
from werkzeug.middleware.proxy_fix import ProxyFix

import photos
import posts

app = Flask(__name__, static_url_path="/admin/static")
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
<a href="/photography/{{ p.slug }}/" class="photo-tile photo-ph reveal" style="--ph:url({{ p.ph }});--a:{{ p.ratio }}" aria-label="View full size: {{ p.alt }}">
<picture>
<source type="image/webp" srcset="{{ p.thumb_webp }} 640w, {{ p.thumb2x_webp }} 1280w" sizes="(max-width: 600px) 100vw, 60vw">
<img src="{{ p.thumb_jpg }}" srcset="{{ p.thumb_jpg }} 640w, {{ p.thumb2x_jpg }} 1280w" sizes="(max-width: 600px) 100vw, 60vw" alt="{{ p.alt }}" width="{{ p.w }}" height="{{ p.h }}"
 {% if loop.index0 < 4 %}loading="eager"{% if loop.first %} fetchpriority="high"{% endif %}{% else %}loading="lazy"{% endif %} decoding="async">
</picture>
<span class="photo-tile-cap">{{ p.alt }}{% if p.when %}<small>{{ p.when }}</small>{% endif %}</span>
</a>
{% endfor %}
</div>
<script type="speculationrules">{"prerender": [{"where": {"href_matches": "/photography/*"}, "eagerness": "moderate"}]}</script>
{% else %}
<p>No photos yet.</p>
{% endif %}"""

PHOTO_TMPL = """<figure class="photo-single-figure">
<span class="photo-frame photo-ph" style="--ph:url({{ ph }});--ar:{{ w }}/{{ h }};width:min(100%, calc(max(320px, 100svh - 210px) * {{ w }} / {{ h }}))">
<picture>
<source type="image/webp" srcset="{{ mid_webp }}">
<img src="{{ mid_jpg }}" data-full="{{ full_webp }}" data-max="{{ max_jpg }}" alt="{{ p.alt }}" width="{{ w }}" height="{{ h }}" loading="eager" fetchpriority="high" decoding="async">
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
</nav>
{% if newer or older %}<script type="speculationrules">{"prerender": [{"urls": [{% if newer %}"/photography/{{ newer.slug }}/"{% endif %}{% if newer and older %}, {% endif %}{% if older %}"/photography/{{ older.slug }}/"{% endif %}]}]}</script>{% endif %}"""

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
                          ratio=round(w / h, 4),
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
        max_jpg=photos.variant_url(p, "max", "jpg"),
        mid_webp=photos.variant_url(p, "thumb2x", "webp"),
        mid_jpg=photos.variant_url(p, "thumb2x", "jpg"),
        newer=ordered[i - 1] if i > 0 else None,
        older=ordered[i + 1] if i + 1 < len(ordered) else None)
    return render_page(main, p["alt"], describe(p), f"/photography/{slug}/", image_meta(p, "article"))


@app.route("/photography/recent.json")
def recent():
    """Homepage data: a hero (chosen by the "Homepage photo" setting - a
    random one per request, the newest, or a specific photo) plus the newest
    four others for the "Recent photos" strip."""
    all_ = photos.load_all()
    if not all_:
        return jsonify(hero=None, photos=[])
    hero = pick_hero(all_)
    hw, hh = photos.variant_size(hero, "hero")
    # desktop screens get the banner crop, when the photo has one
    desk = None
    if hero.get("herobox"):
        desk = dict(ph=photos.placeholder(hero, "banner"),
                    low=photos.variant_url(hero, "bannersm", "webp"),
                    srcset=", ".join(f"{photos.variant_url(hero, v, 'webp')} {photos.variant_size(hero, v)[0]}w"
                                     for v in ("banner", "banner2x")))
    out = []
    for p in [p for p in all_ if p is not hero][:4]:
        w, h = photos.variant_size(p, "teaser")
        out.append(dict(alt=p["alt"], slug=p["slug"], url=f"/photography/{p['slug']}/",
                        width=w, height=h, thumb=photos.variant_url(p, "teaser", "webp"),
                        thumb2x=photos.variant_url(p, "teaser2x", "webp"),
                        ph=photos.placeholder(p)))
    resp = jsonify(
        hero=dict(alt=hero["alt"], slug=hero["slug"], url=f"/photography/{hero['slug']}/",
                  when=when_line(hero), width=hw, height=hh,
                  src=photos.variant_url(hero, "hero", "webp"), ph=photos.placeholder(hero),
                  # a small level shown first (the gallery thumbnail, often cached)
                  low=photos.variant_url(hero, "thumb", "webp"),
                  srcset=", ".join(f"{photos.variant_url(hero, v, 'webp')} {photos.variant_size(hero, v)[0]}w"
                                   for v in ("hero", "full")),
                  desk=desk),
        photos=out)
    resp.headers["Cache-Control"] = "no-store"  # a fresh pick on every visit
    return resp


def pick_hero(all_):
    mode = photos.load_settings()["hero"]
    if mode == "random":
        return random.choice(all_)
    # a specific photo, falling back to the newest if it's been deleted
    return next((p for p in all_ if p["slug"] == mode), all_[0])


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

EMPTY = {"alt": "", "location": "", "month": "", "camera": "", "lens": "",
         "focalLength": "", "aperture": "", "shutter": "", "iso": "", "filmStock": "", "crop": "", "heroCrop": ""}


def client_ip():
    # Behind nginx every request comes from loopback; nginx resolves the
    # visitor's address from Cloudflare's CF-Connecting-IP and passes it on.
    if request.remote_addr in ("127.0.0.1", "::1"):
        return request.headers.get("X-Real-IP") or "unknown"
    return request.remote_addr or "unknown"


def require_login():
    return "admin" in session


def this_month():
    return date.today().strftime("%Y-%m")


def run(cmd):
    return subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=120)


def slugify(value, fallback="photo"):
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    return re.sub(r"[-_\s]+", "-", value).strip("-") or fallback


def admin_photos():
    out = []
    for p in photos.load_all():
        q = dict(EMPTY, **{k: v for k, v in p.items() if isinstance(v, str)})
        q["month"] = p.get("date", "")[:7]
        q["thumb"] = photos.variant_url(p, "thumb", "webp")
        q["mtime"] = p["mtime"]
        q["month_label"] = month_year(p.get("date", "")) or "Undated"
        q["rank"] = len(out)
        out.append(q)
    return out


def gear_history():
    """Previously-used camera/lens/film values, offered as dropdowns so repeat
    gear doesn't need retyping. Settings vary per shot, so no dropdown there."""
    all_ = photos.load_all()
    return {key: sorted({p[field] for p in all_ if p.get(field)})
            for key, field in (("cameras", "camera"), ("lenses", "lens"), ("films", "filmStock"))}


def done(url, message, ok=True):
    """Redirect after a successful POST, so reloading the page that follows
    can't send the form again. The message is shown once, on that page."""
    session["flash"] = [message, ok]
    return redirect(url)


def take_flash(message, ok):
    if message is None and "flash" in session:
        flash = session.pop("flash")
        return (flash[0], flash[1]) if isinstance(flash, list) else (flash, True)
    return message, ok


# Static files are linked with ?v=<newest mtime> so a deploy is picked up.
STATIC_V = str(int(max((os.path.getmtime(p) for p in glob.glob(
    os.path.join(app.static_folder, "*"))), default=0)))


def page(template, active, message=None, ok=False, **context):
    """An admin page: the shared shell (nav with counts) plus the page's own
    template; a message passed on from a redirect is shown once."""
    message, ok = take_flash(message, ok)
    all_posts = posts.load_all()
    nav = {"photos": len(photos.load_all()),
           "posts": len(all_posts)}
    return render_template(template, active=active, nav=nav, v=STATIC_V,
                           message=message, ok=ok, site=SITE_URL, **context)


def render_photos(message=None, ok=False):
    blank = dict(EMPTY, month=this_month())
    return page("admin/photos.html", "photos", message, ok,
                p=blank, photos=admin_photos(), gear=gear_history(),
                hero=photos.load_settings()["hero"])


def render_edit(slug, message=None, ok=False):
    p = next((q for q in admin_photos() if q["slug"] == slug), None)
    if not p:
        return redirect("/admin/photos")
    hero = photos.load_settings()["hero"]
    cover = hero == slug or (hero == "newest" and p["rank"] == 0)
    return page("admin/photo_edit.html", "photos", message, ok, p=p, cover=cover,
                gear=gear_history())


def login_page(message=None):
    return render_template("admin/login.html", message=message, v=STATIC_V)


def ago(ts):
    """A timestamp as "5 min ago", "yesterday", "12 Mar"..."""
    secs = time.time() - ts
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{int(secs // 60)} min ago"
    if secs < 86400:
        return f"{int(secs // 3600)} h ago"
    if secs < 2 * 86400:
        return "yesterday"
    if secs < 7 * 86400:
        return f"{int(secs // 86400)} days ago"
    return datetime.fromtimestamp(ts).strftime("%-d %b %Y")


def activity(n=9):
    """The latest commits to photos and posts - most of them made from here."""
    log = run(["git", "log", f"-{n}", "--format=%ct%x09%s", "--", "photos", "content/posts"])
    out = []
    for line in log.stdout.splitlines():
        ts, _, subject = line.partition("\t")
        low = subject.lower()
        kind = "photo" if "photo" in low else "post" if ("post" in low or "draft" in low) else ""
        out.append(dict(when=ago(int(ts)), what=subject, kind=kind))
    return out


def day_label(value):
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").strftime("%-d %b %Y")
    except ValueError:
        return value or "Undated"


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
    crop, hero_crop = clean_crop(f.get("crop")), clean_crop(f.get("hero_crop"))
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
        "crop": crop,
        # the same box as the crop is no banner crop at all
        "heroCrop": "" if hero_crop == crop else hero_crop,
    }, None


def clean_crop(value):
    """The crop box from the form, normalised, or "" for none."""
    box = photos.parse_crop(value or "")
    return ",".join(f"{x:.4f}" for x in box) if box else ""


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


def find_duplicate(file):
    """The library photo whose image is byte-for-byte the uploaded file, if any."""
    data = file.stream.read()
    file.stream.seek(0)
    digest = hashlib.sha1(data).digest()
    for p in photos.load_all():
        try:
            if os.path.getsize(p["src"]) != len(data):
                continue
            with open(p["src"], "rb") as fh:
                if hashlib.sha1(fh.read()).digest() == digest:
                    return p
        except OSError:
            pass
    return None


def commit_push(slug, message):
    """Version the metadata. Images aren't in git - the host backup covers them."""
    return commit_paths([f"photos/{slug}.md"], message)


def commit_paths(paths, message):
    if os.environ.get("PHOTO_NO_GIT") or not paths:  # test instances
        return ""
    run(["git", "add", "-A", "--", *paths])
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
        return login_page()
    library = admin_photos()
    all_posts = posts.load_all()
    drafts = sorted((p for p in all_posts if p["draft"]), key=lambda p: p["mtime"], reverse=True)
    for p in drafts:
        p["edited"] = ago(p["mtime"])
    hero = photos.load_settings()["hero"]
    hero_photo = None if hero == "random" else next(
        (q for q in library if q["slug"] == hero), library[0] if library else None)
    if hero == "random":
        hero_label = "A different photo on every visit."
    elif hero_photo and hero_photo["slug"] == hero:
        hero_label = f"Always \u201c{hero_photo['alt']}\u201d."
    else:
        hero_label = "Always the newest photo."
    return page("admin/overview.html", "overview",
                photo_count=len(library), month_count=len({q["month"] for q in library}),
                recent_photos=library[:5], hero_label=hero_label, hero_photo=hero_photo,
                drafts=drafts, published=[p for p in all_posts if not p["draft"]],
                activity=activity())


@app.route("/admin/photos")
def photos_page():
    if not require_login():
        return redirect("/admin")
    return render_photos()


@app.route("/admin/login", methods=["POST"])
def login():
    ip = client_ip()
    count, locked_until = _failed_logins.get(ip, (0, 0))
    now = time.time()
    if now < locked_until:
        return login_page(f"Too many attempts. Try again in {int(locked_until - now)}s.")
    if request.form.get("password") == ADMIN_PASSWORD:
        _failed_logins.pop(ip, None)
        session.clear()
        session["admin"] = True
        return redirect("/admin")
    count += 1
    locked_until = time.time() + LOGIN_LOCKOUT_SECONDS if count >= LOGIN_MAX_ATTEMPTS else 0
    _failed_logins[ip] = (count, locked_until)
    msg = f"Too many attempts. Locked for {LOGIN_LOCKOUT_SECONDS}s." if locked_until else "Wrong password."
    return login_page(msg)


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
        return render_photos("No file selected.")
    data, err = form_data()
    if err:
        return render_photos(err)
    dupe = find_duplicate(file)
    if dupe:
        return render_photos(f'That image is already in the library as '
                            f'<a href="/admin/edit/{dupe["slug"]}">{escape(dupe["alt"])}</a>.')

    base = slug = slugify(data["alt"])
    n = 2
    while os.path.exists(photos.md_path(slug)):
        slug, n = f"{base}-{n}", n + 1

    name, err = save_upload(file, slug)
    if err:
        return render_photos(err)
    data["image"] = name
    photos.write(slug, data)
    note = commit_push(slug, f"Add photo: {data['alt']}")
    link = f"/photography/{slug}/"
    return done("/admin/photos", f'Published: <a href="{link}">{escape(SITE_URL + link)}</a>{note}')


@app.route("/admin/source/<slug>.jpg")
def admin_source(slug):
    """The uncropped original (upright, downsized) for the crop view."""
    if not require_login():
        abort(403)
    p = photos.load(slug)
    if not p:
        abort(404)
    resp = send_file(photos.uncropped_preview(p), mimetype="image/jpeg", max_age=0)
    resp.headers["Cache-Control"] = "private, no-store"
    return resp


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
        return redirect("/admin/photos")
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
    elif data["crop"] != p.get("crop", "") or data["heroCrop"] != p.get("heroCrop", ""):
        photos.purge_cache(slug)  # old crop's derivatives are no longer used

    photos.write(slug, data, p.get("body", ""))
    note = commit_push(slug, f"Edit photo: {data['alt']}")
    return done(f"/admin/edit/{slug}", f"Saved.{note}")


@app.route("/admin/move/<slug>", methods=["POST"])
def move(slug):
    """Swap a photo with its neighbour within the same month. Only the month
    is ever shown, so the day of the date is free to act as the position:
    the month's photos are renumbered so the one shown first has the latest day."""
    if not require_login():
        return redirect("/admin")
    ordered = photos.load_all()
    p = next((q for q in ordered if q["slug"] == slug), None)
    if not p:
        return redirect("/admin/photos")
    month = p.get("date", "")[:7]
    group = [q for q in ordered if q.get("date", "")[:7] == month]
    i = group.index(p)
    j = i - 1 if request.form.get("dir") == "up" else i + 1
    if not 0 <= j < len(group):
        return redirect("/admin/photos")
    if len(group) > 28:
        return render_photos("Can't reorder a month with more than 28 photos.")
    group[i], group[j] = group[j], group[i]
    changed = []
    for n, q in enumerate(group):
        day = f"{month}-{len(group) - n:02d}"
        if q.get("date") != day:
            q["date"] = day
            photos.write(q["slug"], q, q.get("body", ""))
            changed.append(q["slug"])
    note = commit_paths([f"photos/{s}.md" for s in changed], f"Reorder photos: {month_year(month)}")
    return redirect("/admin/photos#month-" + month) if not note else render_photos("Reordered." + note, ok=True)


@app.route("/admin/hero", methods=["POST"])
def set_hero():
    if not require_login():
        return redirect("/admin")
    choice = request.form.get("hero", "")
    if choice not in ("random", "newest") and not photos.load(choice):
        return render_photos("Pick a photo from the list.")
    settings = photos.load_settings()
    settings["hero"] = choice
    photos.save_settings(settings)
    label = choice if choice in ("random", "newest") else photos.load(choice)["alt"]
    note = commit_paths(["photos/_settings.json"], f"Homepage photo: {label}")
    return done("/admin/photos", f"Homepage photo saved.{note}")


@app.route("/admin/delete/<slug>", methods=["POST"])
def delete(slug):
    if not require_login():
        return redirect("/admin")
    p = photos.load(slug)
    if not p:
        return redirect("/admin/photos")
    os.remove(photos.md_path(slug))
    os.remove(p["src"])
    photos.purge_cache(slug)
    note = commit_push(slug, f"Delete photo: {p['alt']}")
    return done("/admin/photos", f"Deleted.{note}")


# --------------------------------------------------------------- writing ----

def site_stylesheet():
    """The site's built stylesheet, so the editor's preview looks like a post."""
    try:
        with open(os.path.join(REPO, "public", "index.html")) as f:
            m = re.search(r"/assets/css/stylesheet\.[0-9a-f]+\.css", f.read())
        return m.group(0) if m else ""
    except OSError:
        return ""


def post_fields(post):
    """A post as the editor's fields."""
    return {"title": post["title"], "description": post["description"], "tags": post["tags"],
            "date": post["date"][:10], "slug": post["slug"], "body": post["body"].rstrip()}


def json_error(message, status=400):
    return jsonify(ok=False, message=message), status


@app.route("/admin/posts")
def posts_page():
    if not require_login():
        return redirect("/admin")
    all_ = posts.load_all()
    for p in all_:
        p["edited"] = ago(p["mtime"])
        p["date_label"] = day_label(p["date"])
        p["unsaved"] = posts.load_autosave(p) is not None
    drafts = sorted((p for p in all_ if p["draft"]), key=lambda p: p["mtime"], reverse=True)
    return page("admin/posts.html", "posts", drafts=drafts,
                published=[p for p in all_ if not p["draft"]])


@app.route("/admin/posts/new", methods=["POST"])
def post_new():
    if not require_login():
        return redirect("/admin")
    title = (request.form.get("title") or "").strip() or "Untitled"
    slug = posts.create(slugify(title, "post"), title)
    note = commit_paths(["content/posts"], f"New draft: {title}")
    if note:
        return done(f"/admin/posts/{slug}", f"Draft started{note}", ok=False)
    return redirect(f"/admin/posts/{slug}")


@app.route("/admin/posts/<slug>")
def post_edit(slug):
    if not require_login():
        return redirect("/admin")
    post = posts.load(slug)
    if not post:
        return redirect("/admin/posts")
    saved = post_fields(post)
    auto = posts.load_autosave(post)
    fields = dict(saved, **{k: auto[k] for k in saved if k in auto}) if auto else saved
    base = f"/admin/posts/{slug}"
    cfg = {"saved": saved, "css": site_stylesheet(), "autosavedAt": auto["at"] if auto else None,
           "urls": {"save": base + "/save", "autosave": base + "/autosave",
                    "image": base + "/image", "files": base + "/files/"}}
    all_tags = sorted({t for p in posts.load_all() for t in p["tags"]}, key=str.lower)
    return page("admin/post_edit.html", "posts", post=post, f=fields, auto=auto,
                auto_when=ago(auto["at"]) if auto else "", cfg=cfg, all_tags=all_tags,
                date_label=day_label(post["date"]))


@app.route("/admin/posts/<slug>/save", methods=["POST"])
def post_save(slug):
    """Save from the editor (JSON). "publish" and "unpublish" also flip the
    draft flag; anything that changes what's on the site rebuilds it."""
    if not require_login():
        return json_error("You've been signed out. Sign in again in another tab, then save.", 401)
    post = posts.load(slug)
    if not post:
        return json_error("That post no longer exists.", 404)
    d = request.get_json(silent=True) or {}
    action = d.get("action", "save")
    if action not in ("save", "publish", "unpublish"):
        return json_error("Unknown action.")
    title = str(d.get("title") or "").strip()
    if not title:
        return json_error("A title is needed.")
    description = str(d.get("description") or "").strip()
    tags = list(dict.fromkeys(str(t).strip() for t in d.get("tags") or [] if str(t).strip()))
    day = str(d.get("date") or "").strip()
    if day and not re.match(r"^\d{4}-\d{2}-\d{2}$", day):
        return json_error("That date isn't valid.")
    was_draft = post["draft"]
    draft = {"publish": False, "unpublish": True}.get(action, was_draft)
    if action == "publish" and d.get("today"):
        day = date.today().isoformat()

    new_slug = str(d.get("slug") or slug).strip().lower()
    if new_slug != slug:
        if not was_draft:
            return json_error("A published post's address can't change - links to it would break.")
        if not posts.SLUG_RE.match(new_slug):
            return json_error("The address can only use a-z, 0-9 and single hyphens.")
        if posts.taken(new_slug):
            return json_error(f"Another post already uses /posts/{new_slug}/.")
        post = posts.rename(post, new_slug)

    posts.save(post, title, description, tags, day, draft, str(d.get("body") or ""))
    posts.clear_autosave(post["slug"])
    verb = {"publish": "Publish post", "unpublish": "Unpublish post"}.get(action, "Edit post")
    note = commit_paths(["content/posts"], f"{verb}: {title}")
    link = f'<a href="{post["url"]}" target="_blank" rel="noopener">{escape(SITE_URL + post["url"])}</a>'
    message = {"publish": f"Published: {link}", "unpublish": "Unpublished - it's no longer on the site."}.get(
        action, "Draft saved." if draft else f"Updated on the site: {link}")
    error = posts.rebuild() if not (draft and was_draft) else None
    if error:
        message += f" But the site rebuild failed, so the site hasn't changed yet: <pre>{escape(error)}</pre>"
    if not draft and day > date.today().isoformat():
        message += " Its date is in the future, so it won't show on the site until then."
    message += note
    if action != "save" or post["slug"] != slug:
        session["flash"] = [message, not (error or note)]
        return jsonify(ok=True, reload=f"/admin/posts/{post['slug']}")
    return jsonify(ok=True, message=message)


@app.route("/admin/posts/<slug>/autosave", methods=["POST"])
def post_autosave(slug):
    if not require_login():
        return json_error("Signed out.", 401)
    post = posts.load(slug)
    if not post:
        return json_error("That post no longer exists.", 404)
    d = request.get_json(silent=True) or {}
    fields = {k: d.get(k) for k in ("title", "description", "tags", "date", "slug", "body")}
    return jsonify(ok=True, at=posts.autosave(slug, fields))


@app.route("/admin/posts/<slug>/discard", methods=["POST"])
def post_discard(slug):
    if not require_login():
        return redirect("/admin")
    posts.clear_autosave(slug)
    return redirect(f"/admin/posts/{slug}")


@app.route("/admin/posts/<slug>/image", methods=["POST"])
def post_image(slug):
    """An image dropped or pasted into the editor: saved beside the post and
    committed straight away (the post's text is saved separately)."""
    if not require_login():
        return json_error("Signed out.", 401)
    post = posts.load(slug)
    file = request.files.get("image")
    if not post or not file or not file.filename:
        return json_error("No image received.")
    post, result = posts.add_image(post, file)
    if not post:
        return json_error(result)
    note = commit_paths(["content/posts"], f"Add image to post: {post['title']}")
    return jsonify(ok=True, name=result, message=note)


@app.route("/admin/posts/<slug>/files/<name>")
def post_file(slug, name):
    if not require_login():
        abort(403)
    post = posts.load(slug)
    path = posts.image_path(post, name) if post else None
    if not path:
        abort(404)
    resp = send_file(path, max_age=0)
    resp.headers["Cache-Control"] = "private, no-store"  # drafts' images stay out of Cloudflare
    return resp


@app.route("/admin/posts/<slug>/delete", methods=["POST"])
def post_delete(slug):
    if not require_login():
        return redirect("/admin")
    post = posts.load(slug)
    if not post:
        return redirect("/admin/posts")
    posts.delete(post)
    note = commit_paths(["content/posts"], f"Delete post: {post['title']}")
    error = None if post["draft"] else posts.rebuild()
    message = f"Deleted “{escape(post['title'])}”."
    if error:
        message += f" But the site rebuild failed: <pre>{escape(error)}</pre>"
    return done("/admin/posts", message + note, ok=not (error or note))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5002")))
