"""The photo library: photos/<slug>.md (front matter) next to photos/<slug>.<ext>.

Only the .md files are in git. Images and resized derivatives live on this
server (derivatives are generated on first request and cached under cache/).
"""
import base64
import glob
import hashlib
import io
import json
import os
import re

from PIL import Image, ImageDraw, ImageFont, ImageOps

REPO = "/var/www/website"
PHOTOS_DIR = os.path.join(REPO, "photos")
CACHE_DIR = os.path.join(REPO, "cache", "photos")
ALLOWED_EXT = {"jpg", "jpeg", "png", "webp"}
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

# Front matter keys, in the order they're written.
FIELDS = ["alt", "date", "image", "location", "camera", "lens",
          "focalLength", "aperture", "shutter", "iso", "filmStock", "crop"]

# Site-wide settings, versioned alongside the photos. "hero" is the homepage
# photo: "random" (a different one on every visit), "newest", or a slug.
SETTINGS_PATH = os.path.join(PHOTOS_DIR, "_settings.json")
SETTINGS_DEFAULTS = {"hero": "random"}

# Derivative sizes: (axis, pixels). A fixed set, so the cache stays bounded.
VARIANTS = {
    "thumb": ("w", 640),    # gallery grid
    "thumb2x": ("w", 1280), # gallery grid on high-density screens
    "teaser": ("h", 260),   # homepage strip - same height for every photo
    "teaser2x": ("h", 520),
    "full": ("w", 2200),    # single photo page
    "hero": ("w", 1600),    # homepage banner
    "og": ("w", 1200),      # link previews
    "max": ("w", 100000),   # the original's full resolution (never upscaled) -
                            # fetched in the background once a photo page has shown
}
# Large sizes get a small visible watermark drawn into the pixels; every size
# carries copyright/artist tags. Bump WATERMARK_VERSION after changing either
# so browsers and the CDN fetch the new images.
WATERMARK = "\u00a9 Ben Kyd"
WATERMARKED = {"full", "og", "max"}
WATERMARK_VERSION = "w2"
QUALITY_VERSION = "q2"
WATERMARK_FONT = os.path.join(REPO, "assets", "fonts", "Libron-Regular.ttf")
ARTIST = "Ben Kyd"
COPYRIGHT = "Copyright Ben Kyd. All rights reserved. benkyd.co.uk"

FORMATS = {"webp": ("WEBP", "image/webp"), "jpg": ("JPEG", "image/jpeg")}


def encode_options(variant, ext):
    """Photography first: visually lossless everywhere, full chroma (4:4:4)
    for JPEG. The max size is near-lossless JPEG - the originals are already
    JPEGs, so lossless re-encoding would only multiply the size."""
    if ext == "jpg":
        q = 97 if variant == "max" else 95 if variant in ("full", "og", "hero") else 92
        return {"quality": q, "subsampling": 0, "optimize": True, "progressive": True}
    q = 95 if variant in ("full", "hero") else 90
    return {"quality": q, "method": 6}

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
    photo["cropbox"] = parse_crop(photo.get("crop", ""))
    # version for cache keys and URLs: changes when the file or the crop does
    photo["ver"] = str(photo["mtime"]) + (
        "-" + hashlib.sha1(photo["crop"].encode()).hexdigest()[:8] if photo["cropbox"] else "")
    return photo


def load_all():
    photos = []
    for path in glob.glob(os.path.join(PHOTOS_DIR, "*.md")):
        p = load(os.path.basename(path)[:-3])
        if p:
            photos.append(p)
    # newest first; within a day (e.g. several uploads in one month, all on
    # the 1st) fall back to the slug so the order is at least stable
    photos.sort(key=lambda p: p["slug"])
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


def load_settings():
    try:
        with open(SETTINGS_PATH) as f:
            return dict(SETTINGS_DEFAULTS, **json.load(f))
    except (OSError, ValueError):
        return dict(SETTINGS_DEFAULTS)


def save_settings(settings):
    with open(SETTINGS_PATH, "w") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")


def parse_crop(value):
    """"left,top,right,bottom" as fractions of the (upright) original, or None.

    The crop is stored in the photo's markdown and applied whenever a
    derivative is made - the original file is never modified."""
    try:
        l, t, r, b = (float(x) for x in value.split(","))
    except (ValueError, AttributeError):
        return None
    if not (0 <= l < r <= 1 and 0 <= t < b <= 1) or r - l < 0.05 or b - t < 0.05:
        return None
    if (l, t, r, b) == (0, 0, 1, 1):
        return None
    return (l, t, r, b)


def crop_pixels(box, w, h):
    l, t, r, b = box
    return (round(l * w), round(t * h), round(r * w), round(b * h))


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


def display_size(photo):
    """Size of the original after orientation and crop."""
    w, h = source_size(photo)
    if photo.get("cropbox"):
        l, t, r, b = crop_pixels(photo["cropbox"], w, h)
        return r - l, b - t
    return w, h


def variant_size(photo, variant):
    w, h = display_size(photo)
    axis, n = VARIANTS[variant]
    if axis == "w":
        return (w, h) if w <= n else (n, max(1, round(h * n / w)))
    return (w, h) if h <= n else (max(1, round(w * n / h)), n)


def variant_ver(photo, variant):
    return f"{photo['ver']}-{QUALITY_VERSION}" + (f"-{WATERMARK_VERSION}" if variant in WATERMARKED else "")


def variant_url(photo, variant, ext):
    return f"/photography/img/{photo['slug']}/{variant}.{ext}?v={variant_ver(photo, variant)}"


def watermark(im):
    """Small translucent mark in the bottom-right corner, sized to the image.
    Only the corner is composited, so full-resolution images stay cheap."""
    w, h = im.size
    size = max(14, round(min(w, h) * 0.022))
    font = ImageFont.truetype(WATERMARK_FONT, size)
    l, t, r, b = ImageDraw.Draw(im).textbbox((0, 0), WATERMARK, font=font)
    margin = round(min(w, h) * 0.025)
    pad = size  # room for the shadow and glyph overhang
    cw, ch = (r - l) + 2 * pad, (b - t) + 2 * pad
    cx, cy = max(0, w - margin - (r - l) - pad), max(0, h - margin - (b - t) - pad)
    corner = im.crop((cx, cy, min(w, cx + cw), min(h, cy + ch))).convert("RGBA")
    layer = Image.new("RGBA", corner.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x, y = pad - l, pad - t
    shadow = max(1, size // 18)
    d.text((x + shadow, y + shadow), WATERMARK, font=font, fill=(0, 0, 0, 70))
    d.text((x, y), WATERMARK, font=font, fill=(255, 255, 255, 165))
    im.paste(Image.alpha_composite(corner, layer).convert("RGB"), (cx, cy))
    return im


def rights_exif():
    exif = Image.Exif()
    exif[0x013B] = ARTIST
    exif[0x8298] = COPYRIGHT
    return exif.tobytes()


def variant_file(photo, variant, ext):
    """Path to the resized image, generating it on first use.

    Re-encoding drops the original's metadata (EXIF, including any GPS
    position); the output carries only artist/copyright tags, plus a visible
    watermark on the large sizes.
    """
    out = os.path.join(CACHE_DIR, f"{photo['slug']}-{variant}-{variant_ver(photo, variant)}.{ext}")
    if os.path.exists(out):
        return out
    os.makedirs(CACHE_DIR, exist_ok=True)
    tw, th = variant_size(photo, variant)
    fmt = FORMATS[ext][0]
    box = photo.get("cropbox")
    with Image.open(photo["src"]) as im:
        # keep the colour profile (e.g. Display P3) so colours aren't flattened
        # to sRGB; no JPEG draft-mode shortcut - it softens the result
        icc = im.info.get("icc_profile")
        im = ImageOps.exif_transpose(im).convert("RGB")
        if box:
            im = im.crop(crop_pixels(box, *im.size))
        if im.size != (tw, th):
            im = im.resize((tw, th), Image.Resampling.LANCZOS)
        if variant in WATERMARKED:
            im = watermark(im)
        tmp = f"{out}.{os.getpid()}.tmp"
        extra = {"icc_profile": icc} if icc else {}
        im.save(tmp, fmt, exif=rights_exif(), **extra, **encode_options(variant, ext))
    os.replace(tmp, out)
    return out


def placeholder(photo):
    """A ~24px-wide JPEG as a data: URI - shown blurred while the real image loads."""
    key = (photo["src"], photo["ver"])
    if key not in _placeholder_cache:
        with Image.open(photo["src"]) as im:
            im.draft("RGB", (256, 256))
            im = ImageOps.exif_transpose(im).convert("RGB")
            if photo.get("cropbox"):
                im = im.crop(crop_pixels(photo["cropbox"], *im.size))
            im.thumbnail((24, 24))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=60)
        _placeholder_cache[key] = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    return _placeholder_cache[key]


def gear_chips(photo):
    """Camera, lens, settings and film as separate labels."""
    return [x for x in (photo.get("camera"), photo.get("lens"),
                        settings_line(photo), photo.get("filmStock")) if x]


def uncropped_preview(photo, width=2400):
    """Upright, uncropped JPEG for the admin crop view."""
    out = os.path.join(CACHE_DIR, f"{photo['slug']}-source{width}-{photo['mtime']}.jpg")
    if os.path.exists(out):
        return out
    os.makedirs(CACHE_DIR, exist_ok=True)
    with Image.open(photo["src"]) as im:
        im.draft("RGB", (width, width))
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((width, width), Image.Resampling.LANCZOS)
        tmp = f"{out}.{os.getpid()}.tmp"
        im.save(tmp, "JPEG", quality=85)
    os.replace(tmp, out)
    return out


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
