"""The photo library: photos/<slug>.md (front matter) next to photos/<slug>.<ext>.

Only the .md files are in git. Images and resized derivatives live on this
server (derivatives are generated on first request and cached under cache/).
"""
import base64
import glob
import io
import os
import re

from PIL import Image, ImageOps

REPO = "/var/www/website"
PHOTOS_DIR = os.path.join(REPO, "photos")
CACHE_DIR = os.path.join(REPO, "cache", "photos")
ALLOWED_EXT = {"jpg", "jpeg", "png", "webp"}
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

# Front matter keys, in the order they're written.
FIELDS = ["alt", "date", "image", "location", "camera", "lens",
          "focalLength", "aperture", "shutter", "iso", "filmStock", "featured"]

# Derivative sizes: (axis, pixels). A fixed set, so the cache stays bounded.
VARIANTS = {
    "thumb": ("w", 640),    # gallery grid
    "teaser": ("h", 260),   # homepage strip - same height for every photo
    "full": ("w", 2200),    # single photo page
    "hero": ("w", 1600),    # homepage banner
    "og": ("w", 1200),      # link previews
}
FORMATS = {"webp": ("WEBP", "image/webp", {"quality": 80}),
           "jpg": ("JPEG", "image/jpeg", {"quality": 84, "optimize": True, "progressive": True})}

_FM_RE = re.compile(r"\A---\n(.*?)\n---\n?(.*)\Z", re.S)
_LINE_RE = re.compile(r'^(\w+):\s*(?:"((?:[^"\\]|\\.)*)"|(\S.*?))\s*$', re.M)
_size_cache = {}
_placeholder_cache = {}


def md_path(slug):
    return os.path.join(PHOTOS_DIR, f"{slug}.md")


def parse(path):
    with open(path) as f:
        text = f.read()
    m = _FM_RE.match(text)
    front, body = (m.group(1), m.group(2)) if m else ("", text)
    data = {}
    for lm in _LINE_RE.finditer(front):
        quoted, bare = lm.group(2), lm.group(3)
        data[lm.group(1)] = (quoted.replace('\\"', '"').replace("\\\\", "\\")
                             if quoted is not None else bare)
    data["body"] = body.strip()
    return data


def load(slug):
    if not SLUG_RE.match(slug or "") or not os.path.exists(md_path(slug)):
        return None
    photo = parse(md_path(slug))
    photo["slug"] = slug
    src = source_path(photo)
    if not src:
        return None
    photo["src"] = src
    photo["mtime"] = int(os.path.getmtime(src))
    return photo


def load_all():
    photos = []
    for path in glob.glob(os.path.join(PHOTOS_DIR, "*.md")):
        p = load(os.path.basename(path)[:-3])
        if p:
            photos.append(p)
    photos.sort(key=lambda p: p.get("date", ""), reverse=True)
    return photos


def write(slug, data, body=""):
    def esc(v):
        return str(v).replace("\\", "\\\\").replace('"', '\\"')
    lines = ["---"]
    for key in FIELDS:
        val = (data.get(key) or "").strip()
        if val:
            lines.append(f"{key}: {val}" if key == "date" else f'{key}: "{esc(val)}"')
    lines.append("---")
    text = "\n".join(lines) + "\n" + (f"\n{body.strip()}\n" if body.strip() else "")
    with open(md_path(slug), "w") as f:
        f.write(text)


def source_path(photo):
    name = os.path.basename(photo.get("image", ""))
    path = os.path.join(PHOTOS_DIR, name)
    return path if name and os.path.isfile(path) else None


def source_size(photo):
    """Display size of the original, honouring EXIF orientation."""
    key = (photo["src"], photo["mtime"])
    if key not in _size_cache:
        with Image.open(photo["src"]) as im:
            w, h = im.size
            if im.getexif().get(0x0112, 1) in (5, 6, 7, 8):
                w, h = h, w
        _size_cache[key] = (w, h)
    return _size_cache[key]


def variant_size(photo, variant):
    w, h = source_size(photo)
    axis, n = VARIANTS[variant]
    if axis == "w":
        return (w, h) if w <= n else (n, max(1, round(h * n / w)))
    return (w, h) if h <= n else (max(1, round(w * n / h)), n)


def variant_url(photo, variant, ext):
    return f"/photography/img/{photo['slug']}/{variant}.{ext}?v={photo['mtime']}"


def variant_file(photo, variant, ext):
    """Path to the resized image, generating it on first use.

    Re-encoding drops all metadata from the output (EXIF, including any GPS
    position), so what's served never leaks more than the picture itself.
    """
    out = os.path.join(CACHE_DIR, f"{photo['slug']}-{variant}-{photo['mtime']}.{ext}")
    if os.path.exists(out):
        return out
    os.makedirs(CACHE_DIR, exist_ok=True)
    tw, th = variant_size(photo, variant)
    fmt, _, opts = FORMATS[ext]
    with Image.open(photo["src"]) as im:
        rotated = im.getexif().get(0x0112, 1) in (5, 6, 7, 8)
        im.draft("RGB", (th, tw) if rotated else (tw, th))  # fast JPEG downscale
        im = ImageOps.exif_transpose(im).convert("RGB")
        if im.size != (tw, th):
            im = im.resize((tw, th), Image.Resampling.LANCZOS)
        tmp = f"{out}.{os.getpid()}.tmp"
        im.save(tmp, fmt, **opts)
    os.replace(tmp, out)
    return out


def placeholder(photo):
    """A ~24px-wide JPEG as a data: URI - shown blurred while the real image loads."""
    key = (photo["src"], photo["mtime"])
    if key not in _placeholder_cache:
        with Image.open(photo["src"]) as im:
            im.draft("RGB", (64, 64))
            im = ImageOps.exif_transpose(im).convert("RGB")
            im.thumbnail((24, 24))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=60)
        _placeholder_cache[key] = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    return _placeholder_cache[key]


def gear_chips(photo):
    """Camera, lens, settings and film as separate labels."""
    return [x for x in (photo.get("camera"), photo.get("lens"),
                        settings_line(photo), photo.get("filmStock")) if x]


def purge_cache(slug):
    for path in glob.glob(os.path.join(CACHE_DIR, f"{slug}-*")):
        os.remove(path)


def is_image(path):
    try:
        with Image.open(path) as im:
            im.verify()
        return True
    except Exception:
        return False


def settings_line(photo):
    """Consistently formatted, however it was typed: 50mm · f/5.6 · 1/1000s · ISO 100."""
    parts = []
    if photo.get("focalLength"):
        parts.append(photo["focalLength"].removesuffix("mm") + "mm")
    if photo.get("aperture"):
        parts.append("f/" + photo["aperture"].removeprefix("f/"))
    if photo.get("shutter"):
        parts.append(photo["shutter"].removesuffix("s") + "s")
    if photo.get("iso"):
        parts.append("ISO " + photo["iso"].removeprefix("ISO").strip())
    return " · ".join(parts)


def gear_line(photo):
    return " • ".join(x for x in (photo.get("camera"), photo.get("lens"),
                                       settings_line(photo), photo.get("filmStock")) if x)
