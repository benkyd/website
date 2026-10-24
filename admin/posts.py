"""Blog posts for the admin's writing tool: content/posts/, built by Hugo.

A post is a single file, content/posts/<Name>.md, or a bundle,
content/posts/<slug>/index.md with its images beside it. New posts are
bundles; a single-file post becomes one when its first image is added.
Its URL is /posts/<slug>/ - the bundle's folder, or the file name made
URL-shaped the way Hugo does it.

Unlike photos, posts are static pages: anything that changes what's on the
site (publishing, unpublishing, editing a published post) rebuilds it.
Saving only rewrites the front matter keys the editor knows about; every
other key, and its formatting, is left exactly as it was.
"""
import glob
import json
import os
import re
import shutil
import subprocess
import threading
import time
from datetime import date, datetime

import yaml
from PIL import Image, ImageOps

import photos

REPO = photos.REPO
POSTS_DIR = os.path.join(REPO, "content", "posts")
AUTOSAVE_DIR = os.path.join(REPO, "cache", "autosave")
HUGO = os.environ.get("HUGO_BIN", "/home/benk/.local/bin/hugo-0.167")
IMAGE_EXT = {"jpg", "jpeg", "png", "webp", "gif"}
MAX_IMAGE = 2400  # longest side of an image in a post; larger ones are scaled down
SLUG_RE = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")

_FM_RE = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", re.S)

# Front matter for a new post, matching the existing ones.
NEW_POST = """---
title: {title}
date: {date}
tags: []
author: "Ben Kyd"
showToc: true
TocOpen: false
draft: true
hidemeta: false
comments: false
description: ""
disableShare: false
disableHLJS: false
hideSummary: false
searchHidden: true
ShowReadingTime: true
ShowBreadCrumbs: true
ShowPostNavLinks: true
ShowWordCount: true
ShowRssButtonInSectionTermList: true
---

"""


def urlize(name):
    """A file name as Hugo puts it in a URL: lower case, spaces as hyphens."""
    return re.sub(r"[^\w\-.~]", "", re.sub(r"\s+", "-", name.strip().lower()))


def _paths():
    files = [p for p in glob.glob(os.path.join(POSTS_DIR, "*.md"))
             if not os.path.basename(p).startswith("_")]
    return files + glob.glob(os.path.join(POSTS_DIR, "*", "index.md"))


def _text(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return "" if value is None else str(value)


def read(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    m = _FM_RE.match(text)
    fm, body = (m.group(1), text[m.end():]) if m else ("", text)
    try:
        meta = yaml.safe_load(fm) or {}
        if not isinstance(meta, dict):
            meta = {}
    except yaml.YAMLError:
        meta = {}
    bundle = os.path.basename(path) == "index.md"
    slug = os.path.basename(os.path.dirname(path)) if bundle else urlize(os.path.basename(path)[:-3])
    raw_date = re.search(r"^date:[ \t]*['\"]?([^'\"\n]*)", fm, re.M)
    tags = meta.get("tags") or []
    body = body.lstrip("\n")
    return {
        "slug": slug, "path": path, "bundle": bundle, "fm": fm, "body": body,
        "dir": os.path.dirname(path) if bundle else None,
        "title": _text(meta.get("title")) or slug,
        "description": _text(meta.get("description")),
        "tags": [_text(t) for t in tags] if isinstance(tags, list) else [_text(tags)],
        "date": raw_date.group(1).strip() if raw_date else _text(meta.get("date")),
        "draft": bool(meta.get("draft", False)),
        "mtime": os.path.getmtime(path),
        "words": len(re.findall(r"\S+", body)),
        "url": f"/posts/{slug}/",
    }


def load_all():
    """Every post, newest first."""
    posts = [read(p) for p in _paths()]
    posts.sort(key=lambda p: (p["date"][:10], p["mtime"]), reverse=True)
    return posts


def load(slug):
    if not SLUG_RE.match(slug or ""):
        return None
    return next((p for p in load_all() if p["slug"] == slug), None)


def taken(slug):
    return os.path.exists(os.path.join(POSTS_DIR, slug)) or any(
        p["slug"] == slug for p in load_all())


def create(slug, title):
    """A new draft bundle; returns its slug (made unique if need be)."""
    base, n = slug, 2
    while taken(slug):
        slug, n = f"{base}-{n}", n + 1
    os.makedirs(os.path.join(POSTS_DIR, slug))
    _write(os.path.join(POSTS_DIR, slug, "index.md"),
           NEW_POST.format(title=_quote(title), date=date.today().isoformat()))
    return slug


def _quote(s):
    # a JSON string is also a valid double-quoted YAML string
    return json.dumps(s, ensure_ascii=False)


def _set(fm, key, value):
    """Front matter with `key` set to the YAML `value` (None removes it). Only
    that key's line (and any indented lines under it) changes."""
    lines, out, found, i = fm.split("\n") if fm else [], [], False, 0
    while i < len(lines):
        if re.match(rf"^{re.escape(key)}[ \t]*:", lines[i]):
            if not found and value is not None:
                out.append(f"{key}: {value}")
            found = True
            i += 1
            while i < len(lines) and lines[i][:1] in (" ", "\t", "-") and lines[i].strip() != "---":
                i += 1
            continue
        out.append(lines[i])
        i += 1
    if not found and value is not None:
        out.append(f"{key}: {value}")
    return "\n".join(out)


def save(post, title, description, tags, day, draft, body):
    """Write the editor's fields into the post. `day` is YYYY-MM-DD; a date
    with a time keeps it while the day is unchanged."""
    fm = post["fm"]
    fm = _set(fm, "title", _quote(title))
    fm = _set(fm, "description", _quote(description))
    fm = _set(fm, "tags", "[" + ", ".join(_quote(t) for t in tags) + "]")
    if day and day != post["date"][:10]:
        fm = _set(fm, "date", day)
    fm = _set(fm, "draft", "true" if draft else "false")
    _write(post["path"], f"---\n{fm}\n---\n\n{body.rstrip()}\n")


def _write(path, text):
    tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def make_bundle(post):
    """Turn a single-file post into a bundle (same URL) so images can sit
    beside it. Returns the post as re-read."""
    if post["bundle"]:
        return post
    folder = os.path.join(POSTS_DIR, post["slug"])
    os.makedirs(folder, exist_ok=True)
    os.rename(post["path"], os.path.join(folder, "index.md"))
    return read(os.path.join(folder, "index.md"))


def rename(post, slug):
    """Move a post to a new URL; returns the post as re-read."""
    post = make_bundle(post)
    folder = os.path.join(POSTS_DIR, slug)
    os.rename(post["dir"], folder)
    old = autosave_path(post["slug"])
    if os.path.exists(old):
        os.replace(old, autosave_path(slug))
    return read(os.path.join(folder, "index.md"))


def delete(post):
    if post["bundle"]:
        shutil.rmtree(post["dir"])
    else:
        os.remove(post["path"])
    clear_autosave(post["slug"])


# ---------------------------------------------------------------- images ----

def _image_name(post, filename, ext):
    stem = filename.rpartition(".")[0]
    stem = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    if not stem or stem in ("image", "img", "screenshot", "pasted"):
        stem = post["slug"]
    name, n = f"{stem}.{ext}", 2
    while os.path.exists(os.path.join(post["dir"], name)):
        name, n = f"{stem}-{n}.{ext}", n + 1
    return name


def add_image(post, file):
    """Save an uploaded image beside the post: (post, name) or (None, error).
    Photos lose their metadata (EXIF, including any GPS position) and are
    scaled to MAX_IMAGE on the long side; GIFs are kept as they are."""
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in IMAGE_EXT:
        return None, "Only jpg, png, webp or gif images can go in a post."
    post = make_bundle(post)
    name = _image_name(post, file.filename, "jpg" if ext == "jpeg" else ext)
    out = os.path.join(post["dir"], name)
    tmp = out + ".upload"
    file.save(tmp)
    try:
        if ext == "gif":
            Image.open(tmp).verify()
            os.replace(tmp, out)
            return post, name
        with Image.open(tmp) as im:
            icc = im.info.get("icc_profile")
            im = ImageOps.exif_transpose(im)
            im.thumbnail((MAX_IMAGE, MAX_IMAGE), Image.Resampling.LANCZOS)
            extra = {"icc_profile": icc} if icc else {}
            if ext in ("jpg", "jpeg"):
                im.convert("RGB").save(out, "JPEG", quality=88, progressive=True, **extra)
            elif ext == "webp":
                im.save(out, "WEBP", quality=88, **extra)
            else:
                im.save(out, "PNG", optimize=True, **extra)
    except Exception:
        for p in (tmp, out):
            if os.path.exists(p):
                os.remove(p)
        return None, "That file isn't a readable image."
    os.remove(tmp)
    return post, name


def image_path(post, name):
    if not post["bundle"] or name != os.path.basename(name):
        return None
    path = os.path.join(post["dir"], name)
    return path if os.path.isfile(path) else None


# -------------------------------------------------------------- autosave ----
# Work in progress is kept outside git (cache/ is ignored) until it's saved.

def autosave_path(slug):
    return os.path.join(AUTOSAVE_DIR, f"{slug}.json")


def autosave(slug, fields):
    os.makedirs(AUTOSAVE_DIR, exist_ok=True)
    fields = dict(fields, at=time.time())
    _write(autosave_path(slug), json.dumps(fields))
    return fields["at"]


def load_autosave(post):
    """Unsaved changes for the post, if there are any newer than the file."""
    try:
        with open(autosave_path(post["slug"])) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if data.get("at", 0) <= post["mtime"]:
        return None
    return data


def clear_autosave(slug):
    try:
        os.remove(autosave_path(slug))
    except OSError:
        pass


# ----------------------------------------------------------------- build ----

_build_lock = threading.Lock()


def rebuild():
    """Rebuild the site with Hugo; None when it worked, else the error."""
    if os.environ.get("NO_BUILD"):
        return None
    with _build_lock:
        try:
            os.remove(os.path.join(REPO, ".hugo_build.lock"))
        except OSError:
            pass
        try:
            # clean: an unpublished or deleted post's page goes too (public/
            # holds nothing Hugo doesn't generate)
            r = subprocess.run([HUGO, "--minify", "--cleanDestinationDir"], cwd=REPO,
                               capture_output=True, text=True, timeout=300)
        except (OSError, subprocess.TimeoutExpired) as e:
            return str(e)
        return None if r.returncode == 0 else (r.stderr or r.stdout)[-800:]
