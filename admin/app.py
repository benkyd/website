import glob
import os
import re
import shutil
import subprocess
import time
import unicodedata
from datetime import date

from flask import Flask, request, session, redirect, render_template_string
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import secure_filename

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

REPO = "/var/www/website"
ASSETS_DIR = os.path.join(REPO, "assets", "photography")
CONTENT_DIR = os.path.join(REPO, "content", "photography")
HUGO_BIN = "/home/benk/.local/bin/hugo-0.167"
BASE_URL = "https://benkyd.co.uk/"
ALLOWED_EXT = {"jpg", "jpeg", "png", "webp"}

# Very small in-memory login rate limit: 5 failed attempts from one
# source IP locks that IP out for 60s. Resets if the process restarts -
# that's fine, this is a deterrent against casual password guessing, not
# a defense against a serious distributed attacker (there is nothing
# juicy enough behind this login to be worth one).
_failed_logins = {}  # ip -> (count, locked_until_ts)
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 60


def client_ip():
    return request.remote_addr or "unknown"


TEMPLATE = """<!DOCTYPE html>
<html><head>
<meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Photography Admin</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#14161a;color:#e8e8e6;font-family:system-ui,sans-serif;padding:1.5rem;min-height:100vh}
h1{font-size:1.3rem;margin-bottom:1.5rem;letter-spacing:.02em}
h2{font-size:1rem;margin:2rem 0 1rem;color:#c5c6ca}
.card{background:#1d2026;border:1px solid rgba(255,255,255,.08);border-radius:8px;padding:1.25rem;margin-bottom:1rem;max-width:480px}
label{display:block;font-size:.75rem;letter-spacing:.08em;text-transform:uppercase;color:#9a9ca3;margin-bottom:.4rem;margin-top:.9rem}
label:first-child{margin-top:0}
.hint{font-size:.75rem;color:#6b6d74;margin-top:-.25rem;margin-bottom:.5rem;text-transform:none;letter-spacing:0}
.gear-row{display:grid;grid-template-columns:repeat(4,1fr);gap:.5rem}
.gear-row label{font-size:.65rem}
input[type=text],input[type=date],input[type=month],input[type=password],input[type=file]{width:100%;padding:.6rem .8rem;background:#101216;border:1px solid rgba(255,255,255,.12);border-radius:4px;color:#e8e8e6;font-size:1rem}
input:focus{outline:none;border-color:#6fa8ff}
.btn{width:100%;padding:.8rem;background:#6fa8ff;color:#0a0a0a;border:none;border-radius:4px;font-size:1rem;font-weight:700;cursor:pointer;margin-top:1.1rem}
.btn:active{background:#8fbaff}
.btn-danger{background:#e05c5c}
.btn-ghost{background:transparent;border:1px solid rgba(255,255,255,.15);color:#c5c6ca}
.status{padding:.75rem 1rem;border-radius:4px;margin-bottom:1rem;font-size:.9rem;max-width:480px}
.ok{background:rgba(34,197,94,.12);border:1px solid rgba(34,197,94,.3);color:#86efac}
.err{background:rgba(239,68,68,.12);border:1px solid rgba(239,68,68,.3);color:#fca5a5}
.login-wrap{max-width:320px;margin:4rem auto}
.section{font-size:.7rem;letter-spacing:.1em;text-transform:uppercase;color:#6fa8ff;margin-top:1.3rem;margin-bottom:-.3rem}
a{color:#6fa8ff}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:12px;max-width:900px}
.tile{display:block;border:1px solid rgba(255,255,255,.08);border-radius:8px;overflow:hidden;background:#1d2026;color:#e8e8e6}
.tile img{width:100%;aspect-ratio:1;object-fit:cover;display:block}
.tile .cap{padding:.5rem .6rem;font-size:.8rem}
.tile .cap .row{display:flex;gap:.5rem;margin-top:.4rem}
.tile .cap a{font-size:.75rem}
.row-actions{display:flex;gap:.5rem;align-items:center}
form.inline{display:inline}
</style></head><body>
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
<h1>Add a photo</h1>
{% if message %}<div class="status {{ 'ok' if ok else 'err' }}">{{ message | safe }}</div>{% endif %}
<form method="post" action="/admin/upload" enctype="multipart/form-data" class="card">
<label>Image (jpg / png / webp)</label>
<input type="file" name="image" accept=".jpg,.jpeg,.png,.webp" required/>

<label>Caption / alt text</label>
<input type="text" name="alt" placeholder="A short description of the photo" required/>

<label>Location</label>
<input type="text" name="location" placeholder="e.g. Les Deux Alpes, France"/>

<label>Date</label>
<input type="month" name="date" value="{{ this_month }}"/>

<div class="section">Gear (optional)</div>
<p class="hint">Not read from the file - type what you shot it with.</p>
<label>Camera</label>
<input type="text" name="camera" list="cameras-list" placeholder="e.g. Hasselblad 500C"/>
<label>Lens</label>
<input type="text" name="lens" list="lenses-list" placeholder="e.g. 80mm f/2.8"/>
<div class="gear-row">
<div><label>Focal length</label><input type="text" name="focal_length" placeholder="50"/></div>
<div><label>Aperture</label><input type="text" name="aperture" placeholder="5.6"/></div>
<div><label>Shutter</label><input type="text" name="shutter" placeholder="1/1000"/></div>
<div><label>ISO</label><input type="text" name="iso" placeholder="100"/></div>
</div>
<label>Film stock</label>
<input type="text" name="film_stock" list="films-list" placeholder="e.g. Kodak Portra 400"/>
<datalist id="cameras-list">{% for c in gear.cameras %}<option value="{{ c }}">{% endfor %}</datalist>
<datalist id="lenses-list">{% for l in gear.lenses %}<option value="{{ l }}">{% endfor %}</datalist>
<datalist id="films-list">{% for fs in gear.films %}<option value="{{ fs }}">{% endfor %}</datalist>

<button class="btn" type="submit">Publish</button>
</form>

<h2>Existing photos ({{ photos|length }})</h2>
<div class="grid">
{% for p in photos %}
<a class="tile" href="/admin/edit/{{ p.slug }}">
  <img src="{{ p.thumb }}" alt=""/>
  <div class="cap">{{ p.alt }}</div>
</a>
{% endfor %}
</div>

<form method="post" action="/admin/logout" style="max-width:480px;margin-top:2rem">
<button class="btn btn-ghost" type="submit">Sign Out</button>
</form>
{% endif %}
</body></html>"""

EDIT_TEMPLATE = """<!DOCTYPE html>
<html><head>
<meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Edit photo - Photography Admin</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#14161a;color:#e8e8e6;font-family:system-ui,sans-serif;padding:1.5rem;min-height:100vh}
h1{font-size:1.3rem;margin-bottom:1.5rem}
.card{background:#1d2026;border:1px solid rgba(255,255,255,.08);border-radius:8px;padding:1.25rem;margin-bottom:1rem;max-width:480px}
label{display:block;font-size:.75rem;letter-spacing:.08em;text-transform:uppercase;color:#9a9ca3;margin-bottom:.4rem;margin-top:.9rem}
label:first-child{margin-top:0}
.hint{font-size:.75rem;color:#6b6d74;margin-top:-.25rem;margin-bottom:.5rem;text-transform:none;letter-spacing:0}
.gear-row{display:grid;grid-template-columns:repeat(4,1fr);gap:.5rem}
.gear-row label{font-size:.65rem}
input[type=text],input[type=month],input[type=file]{width:100%;padding:.6rem .8rem;background:#101216;border:1px solid rgba(255,255,255,.12);border-radius:4px;color:#e8e8e6;font-size:1rem}
input:focus{outline:none;border-color:#6fa8ff}
.btn{width:100%;padding:.8rem;background:#6fa8ff;color:#0a0a0a;border:none;border-radius:4px;font-size:1rem;font-weight:700;cursor:pointer;margin-top:1.1rem}
.btn-danger{background:#e05c5c;color:#1a0a0a}
.btn-ghost{background:transparent;border:1px solid rgba(255,255,255,.15);color:#c5c6ca}
.status{padding:.75rem 1rem;border-radius:4px;margin-bottom:1rem;font-size:.9rem;max-width:480px}
.ok{background:rgba(34,197,94,.12);border:1px solid rgba(34,197,94,.3);color:#86efac}
.err{background:rgba(239,68,68,.12);border:1px solid rgba(239,68,68,.3);color:#fca5a5}
.section{font-size:.7rem;letter-spacing:.1em;text-transform:uppercase;color:#6fa8ff;margin-top:1.3rem;margin-bottom:-.3rem}
a{color:#6fa8ff}
img.preview{max-width:100%;border-radius:6px;margin-bottom:1rem;display:block}
</style></head><body>
<p><a href="/admin">&lsaquo; Back</a></p>
<h1>Edit photo</h1>
{% if message %}<div class="status {{ 'ok' if ok else 'err' }}">{{ message | safe }}</div>{% endif %}
<img class="preview" src="{{ p.thumb }}" alt=""/>
<form method="post" action="/admin/edit/{{ p.slug }}" enctype="multipart/form-data" class="card">
<label>Replace image (optional)</label>
<input type="file" name="image" accept=".jpg,.jpeg,.png,.webp"/>

<label>Caption / alt text</label>
<input type="text" name="alt" value="{{ p.alt }}" required/>

<label>Location</label>
<input type="text" name="location" value="{{ p.location }}"/>

<label>Date</label>
<input type="month" name="date" value="{{ p.month }}"/>

<div class="section">Gear (optional)</div>
<p class="hint">Not read from the file - type what you shot it with.</p>
<label>Camera</label>
<input type="text" name="camera" list="cameras-list" value="{{ p.camera }}"/>
<label>Lens</label>
<input type="text" name="lens" list="lenses-list" value="{{ p.lens }}"/>
<div class="gear-row">
<div><label>Focal length</label><input type="text" name="focal_length" value="{{ p.focal_length }}"/></div>
<div><label>Aperture</label><input type="text" name="aperture" value="{{ p.aperture }}"/></div>
<div><label>Shutter</label><input type="text" name="shutter" value="{{ p.shutter }}"/></div>
<div><label>ISO</label><input type="text" name="iso" value="{{ p.iso }}"/></div>
</div>
<label>Film stock</label>
<input type="text" name="film_stock" list="films-list" value="{{ p.film_stock }}"/>
<datalist id="cameras-list">{% for c in gear.cameras %}<option value="{{ c }}">{% endfor %}</datalist>
<datalist id="lenses-list">{% for l in gear.lenses %}<option value="{{ l }}">{% endfor %}</datalist>
<datalist id="films-list">{% for fs in gear.films %}<option value="{{ fs }}">{% endfor %}</datalist>

<button class="btn" type="submit">Save</button>
</form>
<form method="post" action="/admin/delete/{{ p.slug }}" class="card"
      onsubmit="return confirm('Delete this photo? This removes it from the live site and the repo.');">
<button class="btn btn-danger" type="submit">Delete this photo</button>
</form>
</body></html>"""


def run(cmd, cwd=REPO):
    return subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, timeout=120
    )


def slugify(value):
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    return re.sub(r"[-\s]+", "-", value) or "photo"


def yaml_escape(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def content_path(slug):
    return os.path.join(CONTENT_DIR, f"{slug}.md")


def parse_front_matter(path):
    with open(path) as f:
        text = f.read()
    data = {}
    for m in re.finditer(r'^(\w+):\s*(?:"((?:[^"\\]|\\.)*)"|(\S+))\s*$', text, re.M):
        key = m.group(1)
        val = m.group(2) if m.group(2) is not None else m.group(3)
        if m.group(2) is not None:
            val = val.replace('\\"', '"').replace("\\\\", "\\")
        data[key] = val
    return data


def list_photos():
    out = []
    for fname in sorted(os.listdir(CONTENT_DIR)):
        if not fname.endswith(".md") or fname == "_index.md":
            continue
        slug = fname[: -len(".md")]
        data = parse_front_matter(content_path(slug))
        photo_file = data.get("photoFile", "")
        base = os.path.basename(photo_file)
        thumb_candidates = [
            f for f in os.listdir(os.path.join(REPO, "public", "photography"))
            if f.startswith(os.path.splitext(base)[0] + "_hu_") and f.endswith(".webp")
        ] if os.path.isdir(os.path.join(REPO, "public", "photography")) else []
        thumb = f"{BASE_URL}photography/{thumb_candidates[0]}" if thumb_candidates else ""
        out.append({
            "slug": slug,
            "alt": data.get("alt", data.get("title", slug)),
            "location": data.get("location", ""),
            "date": data.get("date", "") or "",
            "month": (data.get("date", "") or "")[:7],
            "camera": data.get("camera", ""),
            "lens": data.get("lens", ""),
            "focal_length": data.get("focalLength", ""),
            "aperture": data.get("aperture", ""),
            "shutter": data.get("shutter", ""),
            "iso": data.get("iso", ""),
            "film_stock": data.get("filmStock", ""),
            "photo_file": photo_file,
            "thumb": thumb,
        })
    out.sort(key=lambda p: p["date"], reverse=True)
    return out


def write_front_matter(slug, photo_file, form, existing_date=None):
    month = (form.get("date") or (existing_date or "")[:7] or this_month()).strip()
    if not re.match(r"^\d{4}-\d{2}$", month):
        return None, "Invalid date."
    photo_date = f"{month}-01"
    alt = (form.get("alt") or "").strip()
    if not alt:
        return None, "Caption / alt text is required."
    location = (form.get("location") or "").strip()
    description = f"{alt} — {location}" if location else alt

    lines = [
        "---",
        f'title: "{yaml_escape(alt)}"',
        f'alt: "{yaml_escape(alt)}"',
        f'description: "{yaml_escape(description)}"',
        'layout: "photo"',
        f"date: {photo_date}",
        f'photoFile: "{photo_file}"',
    ]
    camera = (form.get("camera") or "").strip()
    lens = (form.get("lens") or "").strip()
    focal_length = (form.get("focal_length") or "").strip().removesuffix("mm")
    aperture = (form.get("aperture") or "").strip().removeprefix("f/")
    shutter = (form.get("shutter") or "").strip().removesuffix("s")
    iso = (form.get("iso") or "").strip().removeprefix("ISO").strip()
    film_stock = (form.get("film_stock") or "").strip()
    if location:
        lines.append(f'location: "{yaml_escape(location)}"')
    if camera:
        lines.append(f'camera: "{yaml_escape(camera)}"')
    if lens:
        lines.append(f'lens: "{yaml_escape(lens)}"')
    if focal_length:
        lines.append(f'focalLength: "{yaml_escape(focal_length)}"')
    if aperture:
        lines.append(f'aperture: "{yaml_escape(aperture)}"')
    if shutter:
        lines.append(f'shutter: "{yaml_escape(shutter)}"')
    if iso:
        lines.append(f'iso: "{yaml_escape(iso)}"')
    if film_stock:
        lines.append(f'filmStock: "{yaml_escape(film_stock)}"')
    lines.append("---\n")

    with open(content_path(slug), "w") as f:
        f.write("\n".join(lines))
    return alt, None


def gear_history():
    """Unique, previously-used values for the gear fields that tend to
    repeat across many photos (same camera/lens/film bag), so the admin
    form can offer them as a dropdown instead of retyping every time.
    Settings (aperture/shutter/ISO/focal length) vary per shot, so no
    dropdown for those."""
    cameras, lenses, films = set(), set(), set()
    for p in list_photos():
        if p["camera"]:
            cameras.add(p["camera"])
        if p["lens"]:
            lenses.add(p["lens"])
        if p["film_stock"]:
            films.add(p["film_stock"])
    return {
        "cameras": sorted(cameras),
        "lenses": sorted(lenses),
        "films": sorted(films),
    }


def require_login():
    return "admin" in session


def this_month():
    return date.today().strftime("%Y-%m")


def build_commit_push(commit_message):
    build = run([HUGO_BIN, "--minify", "--baseURL", BASE_URL])
    if build.returncode != 0:
        return False, f"Build failed:<br><pre>{build.stderr[-800:]}</pre>"

    # Only the .md metadata is versioned; images and the built site live on
    # this server's disk (gitignored, covered by the nightly host backup).
    run(["git", "add", "-A", "--", "content/photography"])
    commit = run(["git", "commit", "-q", "-m", commit_message])
    if commit.returncode != 0:
        if "nothing to commit" in (commit.stdout + commit.stderr).lower():
            return True, None
        return False, f"Build succeeded and is live on disk, but git commit failed:<br><pre>{(commit.stderr + commit.stdout)[-500:]}</pre>"

    push = run(["git", "push", "origin", "master"])
    if push.returncode != 0:
        return True, f"(committed locally, but push to GitHub failed - local backup commit exists):<br><pre>{push.stderr[-500:]}</pre>"
    return True, None


@app.route("/admin")
def index():
    return render_template_string(
        TEMPLATE, logged_in=require_login(), message=None,
        this_month=this_month(), photos=list_photos() if require_login() else [],
        gear=gear_history() if require_login() else {"cameras": [], "lenses": [], "films": []},
    )


@app.route("/admin/login", methods=["POST"])
def login():
    ip = client_ip()
    count, locked_until = _failed_logins.get(ip, (0, 0))
    now = time.time()
    if now < locked_until:
        wait = int(locked_until - now)
        return render_template_string(
            TEMPLATE, logged_in=False,
            message=f"Too many attempts. Try again in {wait}s.",
        )

    if request.form.get("password") == ADMIN_PASSWORD:
        _failed_logins.pop(ip, None)
        session.clear()
        session["admin"] = True
        return redirect("/admin")

    count += 1
    locked_until = time.time() + LOGIN_LOCKOUT_SECONDS if count >= LOGIN_MAX_ATTEMPTS else 0
    _failed_logins[ip] = (count, locked_until)
    msg = "Wrong password." if not locked_until else f"Too many attempts. Locked for {LOGIN_LOCKOUT_SECONDS}s."
    return render_template_string(TEMPLATE, logged_in=False, message=msg)


@app.route("/admin/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect("/admin")


@app.route("/admin/upload", methods=["POST"])
def upload():
    if not require_login():
        return redirect("/admin")

    def fail(msg):
        return render_template_string(
            TEMPLATE, logged_in=True, message=msg, ok=False,
            this_month=this_month(), photos=list_photos(), gear=gear_history(),
        )

    file = request.files.get("image")
    alt = (request.form.get("alt") or "").strip()
    if not file or not file.filename:
        return fail("No file selected.")
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXT:
        return fail("Only jpg, png or webp files are allowed.")
    if not alt:
        return fail("Caption / alt text is required.")

    slug = slugify(alt)
    base_slug = slug
    n = 2
    while os.path.exists(content_path(slug)):
        slug = f"{base_slug}-{n}"
        n += 1

    filename = secure_filename(f"{slug}.{ext}")
    dest = os.path.join(ASSETS_DIR, filename)
    file.save(dest)

    result_alt, err = write_front_matter(slug, f"photography/{filename}", request.form)
    if err:
        os.remove(dest)
        return fail(err)

    ok, err = build_commit_push(f"Add photo: {result_alt}")
    link = f'{BASE_URL}photography/{slug}/'
    if ok and not err:
        msg = f'Published: <a href="{link}">{link}</a>'
    elif ok:
        msg = f'Published: <a href="{link}">{link}</a> {err}'
    else:
        os.remove(dest)
        os.remove(content_path(slug))
        msg = err

    return render_template_string(
        TEMPLATE, logged_in=True, message=msg, ok=ok,
        this_month=this_month(), photos=list_photos(), gear=gear_history(),
    )


def find_photo(slug):
    for p in list_photos():
        if p["slug"] == slug:
            return p
    return None


@app.route("/admin/edit/<slug>")
def edit_form(slug):
    if not require_login():
        return redirect("/admin")
    p = find_photo(slug)
    if not p:
        return redirect("/admin")
    return render_template_string(EDIT_TEMPLATE, logged_in=True, message=None, p=p, gear=gear_history())


@app.route("/admin/edit/<slug>", methods=["POST"])
def edit_save(slug):
    if not require_login():
        return redirect("/admin")
    p = find_photo(slug)
    if not p:
        return redirect("/admin")

    def fail(msg):
        return render_template_string(EDIT_TEMPLATE, logged_in=True, message=msg, ok=False, p=p, gear=gear_history())

    photo_file = p["photo_file"]
    file = request.files.get("image")
    if file and file.filename:
        ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
        if ext not in ALLOWED_EXT:
            return fail("Only jpg, png or webp files are allowed.")
        old_path = os.path.join(REPO, "assets", photo_file)
        new_filename = secure_filename(f"{slug}.{ext}")
        new_path = os.path.join(ASSETS_DIR, new_filename)
        file.save(new_path)
        if os.path.basename(old_path) != new_filename and os.path.exists(old_path):
            os.remove(old_path)
        photo_file = f"photography/{new_filename}"

    result_alt, err = write_front_matter(slug, photo_file, request.form, existing_date=p["month"])
    if err:
        return fail(err)

    # If the image content changed (new upload, or same filename but new
    # bytes), old derivatives are orphaned under their old content hash -
    # clean them up so they don't just sit there taking up space.
    public_photo_dir = os.path.join(REPO, "public", "photography")
    old_basename = os.path.splitext(os.path.basename(p["photo_file"]))[0]
    for stale in glob.glob(os.path.join(public_photo_dir, f"{old_basename}_hu_*")):
        os.remove(stale)

    ok, err = build_commit_push(f"Edit photo: {result_alt}")
    p = find_photo(slug)
    msg = "Saved." if ok and not err else (f"Saved. {err}" if ok else err)
    return render_template_string(EDIT_TEMPLATE, logged_in=True, message=msg, ok=ok, p=p, gear=gear_history())


@app.route("/admin/delete/<slug>", methods=["POST"])
def delete(slug):
    if not require_login():
        return redirect("/admin")
    p = find_photo(slug)
    if not p:
        return redirect("/admin")

    md_path = content_path(slug)
    asset_path = os.path.join(REPO, "assets", p["photo_file"])
    if os.path.exists(md_path):
        os.remove(md_path)
    if os.path.exists(asset_path):
        os.remove(asset_path)

    # Hugo's normal (non -cleanDestinationDir) build only adds/updates
    # output, it never prunes a removed page's old output - so the
    # deleted photo's page and its derivatives would otherwise keep
    # being served live forever. Remove them explicitly. Scoped to this
    # one slug/basename, never a broad clean (public/ also holds loose
    # files that aren't ours to touch).
    public_photo_dir = os.path.join(REPO, "public", "photography")
    page_dir = os.path.join(public_photo_dir, slug)
    if os.path.isdir(page_dir):
        shutil.rmtree(page_dir)
    basename = os.path.splitext(os.path.basename(p["photo_file"]))[0]
    for stale in glob.glob(os.path.join(public_photo_dir, f"{basename}_hu_*")):
        os.remove(stale)

    ok, err = build_commit_push(f"Delete photo: {p['alt']}")
    message = "Deleted." if ok and not err else (f"Deleted. {err}" if ok else err)
    return render_template_string(
        TEMPLATE, logged_in=True, message=message, ok=ok,
        this_month=this_month(), photos=list_photos(), gear=gear_history(),
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5002)
