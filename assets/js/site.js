// Small progressive enhancements. Everything works without this file.
(function () {
  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Blur-up: images inside .photo-ph sit on a blurred placeholder and fade
  // in once loaded. Also used for photos the homepage adds later.
  function settle(root) {
    (root || document).querySelectorAll(".photo-ph img").forEach(function (img) {
      if (img.dataset.settled) return;
      img.dataset.settled = "1";
      function done() { img.classList.remove("fading"); img.classList.add("loaded"); }
      // already decoded (cached, or loaded before this ran): show as-is
      if (img.complete && img.naturalWidth) { done(); return; }
      img.classList.add("fading");
      img.addEventListener("load", done, { once: true });
      img.addEventListener("error", done, { once: true });
    });
  }
  window.siteSettle = settle;
  settle();

  // Gallery tiles rise in as they scroll into view. Anything already on
  // screen at load is shown straight away so it doesn't flash.
  var tiles = document.querySelectorAll(".reveal");
  if (!reduceMotion && "IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.remove("pending"); io.unobserve(e.target); }
      });
    }, { rootMargin: "0px 0px -40px 0px" });
    tiles.forEach(function (t) {
      if (t.getBoundingClientRect().top > window.innerHeight) { t.classList.add("pending"); io.observe(t); }
    });
  }

  // Single photo page: arrow keys and horizontal swipes move between photos.
  var prev = document.querySelector(".photo-single-prev");
  var next = document.querySelector(".photo-single-next");
  if (prev || next) {
    document.addEventListener("keydown", function (e) {
      if (e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
      if (/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)) return;
      if (e.key === "ArrowLeft" && prev) location.href = prev.href;
      if (e.key === "ArrowRight" && next) location.href = next.href;
    });
    var fig = document.querySelector(".photo-single-figure"), x0 = null, y0 = 0;
    if (fig) {
      fig.addEventListener("touchstart", function (e) {
        if (e.touches.length !== 1) { x0 = null; return; }
        x0 = e.touches[0].clientX; y0 = e.touches[0].clientY;
      }, { passive: true });
      fig.addEventListener("touchend", function (e) {
        if (x0 === null) return;
        var dx = e.changedTouches[0].clientX - x0, dy = e.changedTouches[0].clientY - y0;
        x0 = null;
        if (Math.abs(dx) < 60 || Math.abs(dx) < Math.abs(dy) * 1.5) return;
        if (dx < 0 && next) location.href = next.href;
        if (dx > 0 && prev) location.href = prev.href;
      }, { passive: true });
    }
  }

  // Blog posts: a thin reading-progress bar along the top of the window.
  if (document.querySelector(".post-single .post-content")) {
    var bar = document.createElement("div");
    bar.className = "read-progress";
    document.body.appendChild(bar);
    var queued = false;
    function update() {
      queued = false;
      var max = document.documentElement.scrollHeight - window.innerHeight;
      bar.style.transform = "scaleX(" + (max > 0 ? Math.min(1, window.scrollY / max) : 0) + ")";
    }
    window.addEventListener("scroll", function () {
      if (!queued) { queued = true; requestAnimationFrame(update); }
    }, { passive: true });
    update();
  }
})();

// Audio: upgrade each .audio-player into a play button + waveform scrubber.
// The waveform is decoded from the file itself once the player scrolls near
// the viewport; if that fails the bar still works, just flat.
(function () {
  var players = document.querySelectorAll(".audio-player");
  if (!players.length) return;
  var all = [];
  var PLAY = '<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M8 5.5v13l10.5-6.5z"/></svg>';
  var PAUSE = '<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z"/></svg>';
  function fmt(t) {
    if (!isFinite(t)) return "0:00";
    var s = Math.floor(t % 60);
    return Math.floor(t / 60) + ":" + (s < 10 ? "0" : "") + s;
  }
  function css(name) { return getComputedStyle(document.body).getPropertyValue(name).trim(); }

  players.forEach(function (fig) {
    var audio = fig.querySelector("audio");
    audio.controls = false;
    all.push(audio);
    var ui = document.createElement("div");
    ui.className = "audio-ui";
    ui.innerHTML = '<button type="button" class="audio-play" aria-label="Play">' + PLAY + '</button>' +
      '<canvas class="audio-wave" role="slider" tabindex="0" aria-label="Seek" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0"></canvas>' +
      '<span class="audio-time">0:00</span>';
    fig.insertBefore(ui, audio);
    var btn = ui.querySelector(".audio-play"), cv = ui.querySelector(".audio-wave"), time = ui.querySelector(".audio-time");
    var peaks = null, ctx = cv.getContext("2d");

    function draw() {
      var dpr = window.devicePixelRatio || 1, w = cv.clientWidth, h = cv.clientHeight;
      if (!w) return;
      cv.width = w * dpr; cv.height = h * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      var bar = 2, gap = 2, n = Math.floor(w / (bar + gap));
      var played = audio.duration ? audio.currentTime / audio.duration : 0;
      var on = css("--accent"), off = css("--tertiary");
      for (var i = 0; i < n; i++) {
        var p = peaks ? peaks[Math.floor(i / n * peaks.length)] : 0.08;
        var bh = Math.max(2, p * (h - 4));
        ctx.fillStyle = (i + 0.5) / n <= played ? on : off;
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(i * (bar + gap), (h - bh) / 2, bar, bh, 1); else ctx.rect(i * (bar + gap), (h - bh) / 2, bar, bh);
        ctx.fill();
      }
      cv.setAttribute("aria-valuenow", Math.round(played * 100));
      time.textContent = fmt(audio.currentTime) + " / " + fmt(audio.duration);
    }

    function loadPeaks() {
      if (peaks || !window.AudioContext) return;
      fetch(audio.currentSrc || audio.src).then(function (r) { return r.arrayBuffer(); }).then(function (buf) {
        var ac = new AudioContext();
        return ac.decodeAudioData(buf).then(function (data) { ac.close(); return data; });
      }).then(function (data) {
        var ch = data.getChannelData(0), buckets = 400, size = Math.floor(ch.length / buckets), out = [], max = 0;
        for (var b = 0; b < buckets; b++) {
          var m = 0;
          for (var j = b * size; j < (b + 1) * size; j += 16) { var v = Math.abs(ch[j]); if (v > m) m = v; }
          out.push(m); if (m > max) max = m;
        }
        peaks = out.map(function (v) { return max ? Math.pow(v / max, 0.8) : 0; });
        draw();
      }).catch(function () {});
    }
    if ("IntersectionObserver" in window) {
      var io = new IntersectionObserver(function (es) {
        if (es[0].isIntersecting) { io.disconnect(); loadPeaks(); }
      }, { rootMargin: "300px" });
      io.observe(fig);
    } else loadPeaks();

    btn.addEventListener("click", function () {
      if (audio.paused) {
        all.forEach(function (a) { if (a !== audio) a.pause(); });
        audio.play();
      } else audio.pause();
    });
    audio.addEventListener("play", function () { btn.innerHTML = PAUSE; btn.setAttribute("aria-label", "Pause"); fig.classList.add("playing"); tick(); });
    audio.addEventListener("pause", function () { btn.innerHTML = PLAY; btn.setAttribute("aria-label", "Play"); fig.classList.remove("playing"); draw(); });
    audio.addEventListener("ended", function () { audio.currentTime = 0; draw(); });
    audio.addEventListener("loadedmetadata", draw);
    function tick() { draw(); if (!audio.paused) requestAnimationFrame(tick); }

    function seek(e) {
      var r = cv.getBoundingClientRect();
      var x = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
      if (audio.duration) { audio.currentTime = x * audio.duration; draw(); }
    }
    var dragging = false;
    cv.addEventListener("pointerdown", function (e) { dragging = true; cv.setPointerCapture(e.pointerId); seek(e); });
    cv.addEventListener("pointermove", function (e) { if (dragging) seek(e); });
    cv.addEventListener("pointerup", function () { dragging = false; });
    cv.addEventListener("keydown", function (e) {
      if (!audio.duration) return;
      if (e.key === "ArrowRight") audio.currentTime = Math.min(audio.duration, audio.currentTime + 5);
      else if (e.key === "ArrowLeft") audio.currentTime = Math.max(0, audio.currentTime - 5);
      else if (e.key === " " || e.key === "Enter") { btn.click(); }
      else return;
      e.preventDefault(); draw();
    });
    window.addEventListener("resize", draw);
    new MutationObserver(draw).observe(document.body, { attributes: true, attributeFilter: ["class"] });
    draw();
  });
})();

// Single photo page: click the photo to view it full screen over a greyed
// background. Click, Esc or the close button exits. Full screen persists
// while moving between photos with the arrow keys or swipes.
(function () {
  var photo = document.querySelector(".photo-frame img");
  if (!photo) return;
  var KEY = "photo-lightbox", box = null;

  // Full resolution, mipmap-style: the page shows a 2200px image first; once
  // that's up, the original-resolution image loads in the background and is
  // swapped in (same framing, so nothing moves). Full screen uses it too.
  var maxSrc = photo.dataset.max, maxReady = null;
  function loadMax() {
    if (!maxSrc) return Promise.resolve(null);
    if (!maxReady) maxReady = new Promise(function (resolve) {
      var i = new Image();
      i.onload = function () { (i.decode ? i.decode() : Promise.resolve()).then(function () { resolve(maxSrc); }, function () { resolve(maxSrc); }); };
      i.onerror = function () { resolve(null); };
      i.src = maxSrc;
    });
    return maxReady;
  }
  function upgradePage() {
    loadMax().then(function (src) {
      if (!src) return;
      var pic = photo.closest("picture");
      if (pic) pic.querySelectorAll("source").forEach(function (el) { el.remove(); });
      photo.src = src;
    });
  }
  function whenActive(fn) {
    if (document.prerendering) document.addEventListener("prerenderingchange", fn, { once: true });
    else fn();
  }
  var saveData = navigator.connection && navigator.connection.saveData;
  if (!saveData) whenActive(function () {
    var go = function () { setTimeout(upgradePage, 250); };
    if (document.readyState === "complete") go(); else window.addEventListener("load", go, { once: true });
  });
  function store(on) { try { on ? sessionStorage.setItem(KEY, "1") : sessionStorage.removeItem(KEY); } catch (e) {} }
  function stored() { try { return sessionStorage.getItem(KEY) === "1"; } catch (e) { return false; } }

  function open(instant) {
    if (box) return;
    box = document.createElement("div");
    box.className = "lightbox" + (instant ? " open instant" : "");
    box.setAttribute("role", "dialog");
    box.setAttribute("aria-modal", "true");
    box.setAttribute("aria-label", photo.alt);
    var img = document.createElement("img");
    img.src = photo.currentSrc || photo.src;
    img.alt = photo.alt;
    if (img.src !== maxSrc) loadMax().then(function (src) { if (src) img.src = src; });
    var close = document.createElement("button");
    close.type = "button"; close.className = "lightbox-close"; close.setAttribute("aria-label", "Close");
    close.innerHTML = '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>';
    box.appendChild(img); box.appendChild(close);
    var cap = document.querySelector(".photo-single-caption");
    if (cap) {
      var info = document.createElement("div");
      info.className = "lightbox-info";
      info.innerHTML = cap.innerHTML;
      box.appendChild(info);
    }
    document.body.appendChild(box);
    document.documentElement.classList.add("lightbox-on");
    box.addEventListener("click", shut);
    if (!instant) requestAnimationFrame(function () { box.classList.add("open"); });
    close.focus({ preventScroll: true });
    store(true);
  }
  function shut() {
    if (!box) return;
    var b = box; box = null;
    b.classList.remove("open", "instant");
    document.documentElement.classList.remove("lightbox-on");
    setTimeout(function () { b.remove(); }, 200);
    store(false);
    photo.focus({ preventScroll: true });
  }

  photo.classList.add("zoomable");
  photo.tabIndex = 0;
  photo.addEventListener("click", function () { open(false); });
  photo.addEventListener("keydown", function (e) { if (e.key === "Enter") open(false); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") shut(); });

  // came here from another photo while in full screen: reopen straight away
  function restore() { if (stored()) open(true); }
  if (document.prerendering) document.addEventListener("prerenderingchange", restore, { once: true });
  else restore();
})();
