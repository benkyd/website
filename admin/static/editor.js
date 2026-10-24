// The post editor: Markdown on the left, a live preview in the site's own
// styling on the right. Changes are autosaved to the server (outside git) a
// moment after typing stops; Save writes the post and commits it, and
// Publish / Update also rebuild the site.
(function () {
  var root = document.querySelector("[data-editor]");
  if (!root) return;
  var cfg = JSON.parse(document.getElementById("post-data").textContent);
  function $(s) { return root.querySelector(s); }
  var title = $(".ed-title"), desc = $(".ed-desc"), tags = $("[name=tags]"), day = $("[name=date]");
  var slug = $("[name=slug]"), text = $(".ed-text"), state = $(".ed-save"), words = $(".words");
  var panes = $(".ed-panes"), frame = $(".ed-preview iframe"), write = $(".ed-write");

  function fields() {
    return {
      title: title.value.trim(), description: desc.value.trim(),
      tags: tags.value.split(",").map(function (t) { return t.trim(); }).filter(Boolean),
      date: day.value, slug: slug.value.trim(), body: text.value.replace(/\s+$/, "")
    };
  }
  var KEYS = ["title", "description", "tags", "date", "slug", "body"];
  function same(a, b) {
    return KEYS.every(function (k) { return JSON.stringify(a[k]) === JSON.stringify(b[k]); });
  }
  var saved = cfg.saved, busy = false, autoTimer = null, autoAt = cfg.autosavedAt || null;

  // ---------------------------------------------------------------- state --
  function time(ts) {
    return new Date(ts * 1000).toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"});
  }
  function refresh() {
    var dirty = !same(fields(), saved);
    state.classList.toggle("dirty", dirty);
    if (busy) state.textContent = "Saving…";
    else if (!dirty) state.textContent = "Saved";
    else if (autoTimer) state.textContent = "Editing…";
    else if (autoAt) state.textContent = "Autosaved " + time(autoAt);
    else state.textContent = "Not saved";
    state.title = dirty && autoAt ? "Kept on the server, but not saved to the post yet" : "";
    var n = (text.value.match(/\S+/g) || []).length;
    words.textContent = n.toLocaleString() + " word" + (n === 1 ? "" : "s") + " · " + Math.max(1, Math.round(n / 220)) + " min read";
    return dirty;
  }

  function toast(html, bad) {
    var t = document.querySelector(".toast");
    if (!t) { t = document.createElement("div"); t.className = "toast"; t.setAttribute("role", "status"); document.body.appendChild(t); }
    t.innerHTML = html; t.classList.toggle("bad", !!bad); t.classList.add("show");
    clearTimeout(t._hide);
    t._hide = setTimeout(function () { t.classList.remove("show"); }, bad ? 9000 : 3200);
  }

  function post(url, data) {
    return fetch(url, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(data)})
      .then(function (r) { return r.json().catch(function () { return {ok: false, message: "The server sent back an error (" + r.status + ")."}; }); });
  }

  // ------------------------------------------------------------- autosave --
  function changed() {
    clearTimeout(autoTimer);
    autoTimer = refresh() ? setTimeout(autosave, 1200) : null;
    refresh();
    schedulePreview();
  }
  function autosave() {
    autoTimer = null;
    if (busy || same(fields(), saved)) return refresh();
    post(cfg.urls.autosave, fields()).then(function (j) {
      if (j.ok) autoAt = j.at;
      else state.textContent = "Not autosaved";
      refresh();
    }, function () { state.textContent = "Offline – not autosaved"; });
  }
  // A draft's address follows its title until the address is edited by hand
  // (a published post's address is fixed - its field is disabled).
  function slugify(s) {
    return s.normalize("NFKD").replace(/[^\x00-\x7f]/g, "").replace(/[^\w\s-]/g, "").trim().toLowerCase()
      .replace(/[-_\s]+/g, "-").replace(/^-+|-+$/g, "");
  }
  var follow = !slug.disabled && new RegExp("^" + slugify(saved.title) + "(-\\d+)?$").test(slug.value);
  function dialogText() {
    document.querySelector("#publish-dialog h2").textContent = "Publish “" + (title.value.trim() || "Untitled") + "”?";
    document.querySelector("#publish-dialog .pub-slug").textContent = slug.value.trim();
  }
  title.addEventListener("input", function () {
    if (follow) slug.value = slugify(title.value) || slug.value;
    dialogText();
  });
  slug.addEventListener("input", function () { follow = false; dialogText(); });
  [title, desc, tags, day, slug, text].forEach(function (el) { el.addEventListener("input", changed); });
  window.addEventListener("beforeunload", function (e) {
    if (busy || autoTimer) { e.preventDefault(); e.returnValue = ""; }
  });

  // ----------------------------------------------------------------- save --
  function save(action, extra) {
    if (busy) return;
    var f = fields();
    if (!f.title) { toast("Give the post a title first.", true); title.focus(); return; }
    clearTimeout(autoTimer); autoTimer = null;
    busy = true; refresh();
    root.querySelectorAll("[data-action]").forEach(function (b) { b.disabled = true; });
    post(cfg.urls.save, Object.assign({action: action}, f, extra || {})).then(function (j) {
      if (j.ok && j.reload) { busy = false; location.href = j.reload; return; }
      busy = false;
      root.querySelectorAll("[data-action]").forEach(function (b) { b.disabled = false; });
      if (!j.ok) { toast(j.message || "Couldn't save.", true); refresh(); return; }
      saved = f; autoAt = null; refresh();
      toast(j.message);
    }, function () {
      busy = false;
      root.querySelectorAll("[data-action]").forEach(function (b) { b.disabled = false; });
      refresh();
      toast("Couldn't reach the server – your writing is still here; try again.", true);
    });
  }
  var dialog = document.getElementById("publish-dialog");
  root.addEventListener("click", function (e) {
    var b = e.target.closest("[data-action]");
    if (!b) return;
    var act = b.dataset.action;
    if (act === "publish") return dialog.showModal();
    if (act === "unpublish" && !confirm("Unpublish this post? It'll be taken off the site.")) return;
    save(act);
  });
  dialog.addEventListener("close", function () {
    if (dialog.returnValue === "publish") save("publish", {today: dialog.querySelector("[name=today]").checked});
  });

  // -------------------------------------------------------------- editing --
  // Edits go through execCommand where it's supported, so undo still works.
  function replace(start, end, str, selStart, selEnd) {
    text.focus();
    text.setSelectionRange(start, end);
    if (!document.execCommand || !document.execCommand("insertText", false, str)) {
      text.setRangeText(str, start, end, "end");
      changed();
    }
    if (selStart != null) text.setSelectionRange(selStart, selEnd);
  }
  function wrap(before, after, placeholder) {
    var s = text.selectionStart, e = text.selectionEnd, sel = text.value.slice(s, e) || placeholder;
    replace(s, e, before + sel + after, s + before.length, s + before.length + sel.length);
  }
  function lines(prefix) {
    var v = text.value, s = v.lastIndexOf("\n", text.selectionStart - 1) + 1;
    var e = v.indexOf("\n", text.selectionEnd); if (e < 0) e = v.length;
    var block = v.slice(s, e).split("\n");
    var on = block.every(function (l) { return l.indexOf(prefix) === 0; });
    var out = block.map(function (l) { return on ? l.slice(prefix.length) : prefix + l; }).join("\n");
    replace(s, e, out, s, s + out.length);
  }
  function link() {
    var s = text.selectionStart, e = text.selectionEnd, sel = text.value.slice(s, e) || "link text";
    var str = "[" + sel + "](https://)";
    var u = s + sel.length + 3;
    replace(s, e, str, u, u + 8);
  }
  var picker = document.createElement("input");
  picker.type = "file"; picker.accept = ".jpg,.jpeg,.png,.webp,.gif"; picker.multiple = true;
  picker.addEventListener("change", function () { upload(picker.files); picker.value = ""; });
  var ACTIONS = {
    bold: function () { wrap("**", "**", "bold text"); },
    italic: function () { wrap("_", "_", "italic text"); },
    heading: function () { lines("## "); },
    quote: function () { lines("> "); },
    list: function () { lines("- "); },
    code: function () {
      var sel = text.value.slice(text.selectionStart, text.selectionEnd);
      sel.indexOf("\n") >= 0 ? wrap("```\n", "\n```", "") : wrap("`", "`", "code");
    },
    link: link,
    image: function () { picker.click(); }
  };
  $(".ed-bar").addEventListener("click", function (e) {
    var b = e.target.closest("[data-md]");
    if (b) ACTIONS[b.dataset.md]();
  });
  document.addEventListener("keydown", function (e) {
    if (!(e.ctrlKey || e.metaKey) || e.altKey) return;
    var k = e.key.toLowerCase();
    if (k === "s") { e.preventDefault(); save("save"); return; }
    if (document.activeElement !== text) return;
    var map = {b: "bold", i: "italic", k: "link"};
    if (map[k]) { e.preventDefault(); ACTIONS[map[k]](); }
  });

  // --------------------------------------------------------------- images --
  function isImage(f) { return /\.(jpe?g|png|webp|gif)$/i.test(f.name) || /^image\//.test(f.type); }
  function upload(files) {
    files = Array.prototype.filter.call(files || [], isImage);
    if (!files.length) return;
    files.forEach(function (f) {
      var name = f.name && f.name !== "image.png" ? f.name : "pasted image";
      var mark = "![Uploading " + name + "…]()";
      var s = text.selectionStart;
      var pre = s > 0 && text.value[s - 1] !== "\n" ? "\n\n" : "";
      replace(s, text.selectionEnd, pre + mark + "\n\n");
      var form = new FormData();
      form.append("image", f, f.name || "image.png");
      fetch(cfg.urls.image, {method: "POST", body: form})
        .then(function (r) { return r.json(); })
        .then(function (j) {
          var at = text.value.indexOf(mark);
          if (!j.ok) {
            if (at >= 0) replace(at, at + mark.length, "");
            toast(j.message || "Couldn't add that image.", true);
            return;
          }
          var alt = "Describe the image", md = "![" + alt + "](" + j.name + ")";
          if (at >= 0) replace(at, at + mark.length, md, at + 2, at + 2 + alt.length);
          if (j.message) toast(j.message, true);
        }, function () { toast("Couldn't upload " + name + ".", true); });
    });
  }
  text.addEventListener("paste", function (e) {
    var files = e.clipboardData && e.clipboardData.files;
    if (files && files.length && Array.prototype.some.call(files, isImage)) { e.preventDefault(); upload(files); }
  });
  var depth = 0;
  function hasFiles(e) { return e.dataTransfer && Array.prototype.indexOf.call(e.dataTransfer.types, "Files") >= 0; }
  write.addEventListener("dragenter", function (e) { if (hasFiles(e)) { depth++; write.classList.add("over"); } });
  write.addEventListener("dragleave", function () { if (--depth <= 0) { depth = 0; write.classList.remove("over"); } });
  write.addEventListener("dragover", function (e) { if (hasFiles(e)) e.preventDefault(); });
  write.addEventListener("drop", function (e) {
    depth = 0; write.classList.remove("over");
    if (!hasFiles(e)) return;
    e.preventDefault();
    var pos = document.caretPositionFromPoint ? document.caretPositionFromPoint(e.clientX, e.clientY) : null;
    if (pos && pos.offsetNode === text) text.setSelectionRange(pos.offset, pos.offset);
    upload(e.dataTransfer.files);
  });
  // a file dropped elsewhere on the page shouldn't navigate away from the post
  document.addEventListener("dragover", function (e) { if (hasFiles(e)) e.preventDefault(); });
  document.addEventListener("drop", function (e) { if (hasFiles(e) && !e.defaultPrevented) { e.preventDefault(); upload(e.dataTransfer.files); } });

  // -------------------------------------------------------------- preview --
  var dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  frame.srcdoc = '<!doctype html><html lang="en"><head><meta charset="utf-8"><base target="_blank">' +
    (cfg.css ? '<link rel="stylesheet" href="' + cfg.css + '">' : "") +
    "<style>body{min-height:100vh}.main{padding-top:24px}.sc-ph{margin:1.2em 0;padding:.7em 1em;border:1px dashed var(--border,#ccc);border-radius:8px;color:var(--secondary,#777);font-family:monospace;font-size:.85em}" +
    ".post-content img{max-width:100%}</style>" +
    "<script>MathJax={tex:{displayMath:[['\\\\[','\\\\]'],['$$','$$']],inlineMath:[['\\\\(','\\\\)']]},startup:{typeset:false}};<\/script>" +
    '<script async src="/js/mathjax-3.2.2/tex-chtml.js"><\/script>' +
    '</head><body class="' + (dark ? "dark" : "") + '"><main class="main"><article class="post-single">' +
    '<header class="post-header"><h1 class="post-title" id="t"></h1><div class="post-description" id="d"></div><div class="post-meta" id="m"></div></header>' +
    '<div class="post-content" id="c"></div></article></main></body></html>';

  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]; }); }
  function attrs(s) {
    var out = {}, m, re = /(\w+)\s*=\s*"([^"]*)"/g;
    while ((m = re.exec(s))) out[m[1]] = m[2];
    return out;
  }
  // Hugo shortcodes, drawn the way the site's own ones render.
  function shortcode(name, a, inner) {
    if (name === "audio") return '\n<figure class="audio-player"><audio src="' + esc(a.src || "") + '" preload="metadata" controls></audio><figcaption><span class="audio-title">' + esc(a.title || "Audio") + "</span></figcaption></figure>\n";
    if (name === "quote") return '\n<blockquote class="quote">' + marked.parse(inner || "") + (a.source ? "<footer>&mdash; " + marked.parseInline(a.source) + "</footer>" : "") + "</blockquote>\n";
    return '\n<div class="sc-ph">{{&lt; ' + esc(name) + " &gt;}}</div>\n";
  }
  function toHtml(md) {
    var stash = [];
    // keep maths away from the Markdown parser, for MathJax
    md = md.replace(/\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|\\\([\s\S]+?\\\)/g, function (m) {
      stash.push(m); return "" + (stash.length - 1) + "";
    });
    md = md.replace(/\{\{[<%]\s*([\w-]+)([^}]*?)[>%]\}\}([\s\S]*?)\{\{[<%]\s*\/\s*\1\s*[>%]\}\}/g,
      function (_, name, a, inner) { return shortcode(name, attrs(a), inner); });
    md = md.replace(/\{\{[<%]\s*([\w-]+)([^}]*?)\/?\s*[>%]\}\}/g,
      function (_, name, a) { return shortcode(name, attrs(a), null); });
    return marked.parse(md, {gfm: true}).replace(/(\d+)/g, function (_, i) { return esc(stash[i]); });
  }
  function fmtDate(v) {
    var d = v ? new Date(v + "T12:00:00") : null;
    return d && !isNaN(d) ? d.toLocaleDateString("en-GB", {day: "numeric", month: "long", year: "numeric"}) : "";
  }
  var previewTimer = null;
  function schedulePreview() { clearTimeout(previewTimer); previewTimer = setTimeout(renderPreview, 120); }
  function renderPreview() {
    var doc = frame.contentDocument;
    if (!doc || !doc.getElementById("c")) return;
    var f = fields(), n = (f.body.match(/\S+/g) || []).length;
    doc.getElementById("t").textContent = f.title || "Untitled";
    doc.getElementById("d").textContent = f.description;
    doc.getElementById("m").textContent = [fmtDate(f.date), Math.max(1, Math.round(n / 220)) + " min", n + " words"].filter(Boolean).join(" · ");
    var c = doc.getElementById("c");
    c.innerHTML = toHtml(f.body);
    c.querySelectorAll("img").forEach(function (img) {
      var src = img.getAttribute("src") || "";
      if (src && !/^([a-z]+:|\/|#)/i.test(src)) img.src = cfg.urls.files + encodeURIComponent(src);
    });
    var mj = frame.contentWindow.MathJax;
    if (mj && mj.typesetPromise) mj.typesetPromise([c]).catch(function () {});
    syncScroll();
  }
  frame.addEventListener("load", function () {
    renderPreview();
    // MathJax arrives a little after the page; typeset once it's there
    var tries = 0, wait = setInterval(function () {
      var mj = frame.contentWindow && frame.contentWindow.MathJax;
      if ((mj && mj.typesetPromise) || ++tries > 40) { clearInterval(wait); renderPreview(); }
    }, 250);
  });
  function syncScroll() {
    if (panes.dataset.view !== "split") return;
    var w = frame.contentWindow, d = frame.contentDocument;
    if (!w || !d || !d.documentElement) return;
    var max = text.scrollHeight - text.clientHeight;
    var ratio = max > 0 ? text.scrollTop / max : 0;
    w.scrollTo(0, ratio * (d.documentElement.scrollHeight - w.innerHeight));
  }
  text.addEventListener("scroll", syncScroll, {passive: true});

  // ---------------------------------------------------------------- views --
  var KEY = "post-editor-view";
  function setView(v) {
    panes.dataset.view = v;
    root.querySelectorAll(".views button").forEach(function (b) { b.setAttribute("aria-pressed", b.dataset.view === v); });
    try { localStorage.setItem(KEY, v); } catch (e) {}
    if (v !== "write") renderPreview();
  }
  root.querySelector(".views").addEventListener("click", function (e) {
    var b = e.target.closest("[data-view]");
    if (b) setView(b.dataset.view);
  });
  var view = null;
  try { view = localStorage.getItem(KEY); } catch (e) {}
  if (window.matchMedia("(max-width: 860px)").matches && view === "split") view = "write";
  setView(view || (window.matchMedia("(max-width: 860px)").matches ? "write" : "split"));

  refresh();
  if (!same(fields(), saved)) state.textContent = "Restored – not saved";
})();
