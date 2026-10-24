// Crop view: a draggable box over the upright original. The box is kept as
// fractions (left, top, right, bottom) in the crop view's hidden input.
document.querySelectorAll(".crop").forEach(function (root) {
  var stage = root.querySelector(".crop-stage"), img = root.querySelector(".crop-img");
  var box = root.querySelector(".crop-box"), tools = root.querySelector(".crop-tools");
  var input = root.querySelector("input[type=hidden]"), info = root.querySelector(".crop-info");
  var hole = root.querySelector(".crop-hole");
  var loupe = document.createElement("canvas"), LS = 200, ZOOM = 4;
  loupe.className = "crop-loupe"; loupe.width = loupe.height = LS * (window.devicePixelRatio || 1);
  loupe.hidden = true; document.body.appendChild(loupe);
  var lctx = loupe.getContext("2d");

  // Magnifier: while an edge or corner is dragged, show the area around
  // that edge at ZOOM x the on-screen size, next to the cursor.
  function drawLoupe(h, px, py) {
    var r = img.getBoundingClientRect(), nat = img.naturalWidth / r.width;
    var fx = h.indexOf("w") >= 0 ? c[0] : h.indexOf("e") >= 0 ? c[2] : (c[0] + c[2]) / 2;
    var fy = h.indexOf("n") >= 0 ? c[1] : h.indexOf("s") >= 0 ? c[3] : (c[1] + c[3]) / 2;
    var span = LS / ZOOM * nat;                       // natural px shown across the loupe
    var sx = fx * img.naturalWidth - span / 2, sy = fy * img.naturalHeight - span / 2;
    var d = loupe.width, k = d / span;
    lctx.fillStyle = "#222"; lctx.fillRect(0, 0, d, d);
    lctx.imageSmoothingEnabled = false;
    lctx.drawImage(img, sx, sy, span, span, 0, 0, d, d);
    var x0 = (c[0] * img.naturalWidth - sx) * k, y0 = (c[1] * img.naturalHeight - sy) * k;
    var x1 = (c[2] * img.naturalWidth - sx) * k, y1 = (c[3] * img.naturalHeight - sy) * k;
    lctx.fillStyle = "rgba(0,0,0,.55)";
    lctx.beginPath(); lctx.rect(0, 0, d, d); lctx.rect(x0, y0, x1 - x0, y1 - y0); lctx.fill("evenodd");
    lctx.strokeStyle = "#fff"; lctx.lineWidth = Math.max(1, d / LS);
    lctx.strokeRect(x0, y0, x1 - x0, y1 - y0);
    var off = 28, lx = px + off, ly = py + off;
    if (lx + LS > window.innerWidth - 8) lx = px - off - LS;
    if (ly + LS > window.innerHeight - 8) ly = py - off - LS;
    loupe.style.left = lx + "px"; loupe.style.top = ly + "px"; loupe.hidden = false;
  }
  var form = root.closest("form"), file = form.querySelector("input[type=file]");
  var start = function () { return parse(root.dataset.initial) || [0, 0, 1, 1]; };
  var c = parse(input.value) || start(), MIN = 0.05;

  function parse(v) {
    var a = (v || "").split(",").map(Number);
    return a.length === 4 && a.every(function (x) { return x >= 0 && x <= 1; }) ? a : null;
  }
  function render() {
    [box, hole].forEach(function (el) {
      el.style.left = c[0] * 100 + "%"; el.style.top = c[1] * 100 + "%";
      el.style.width = (c[2] - c[0]) * 100 + "%"; el.style.height = (c[3] - c[1]) * 100 + "%";
    });
    var full = c[0] <= 0.0001 && c[1] <= 0.0001 && c[2] >= 0.9999 && c[3] >= 0.9999;
    input.value = full ? "" : c.map(function (x) { return x.toFixed(4); }).join(",");
    info.textContent = full ? "Not cropped" : "Keeping " + Math.round((c[2] - c[0]) * 100) + "% × " + Math.round((c[3] - c[1]) * 100) + "% of the original";
    if (img.naturalWidth) {
      var shape = (c[2] - c[0]) * img.naturalWidth / ((c[3] - c[1]) * img.naturalHeight);
      info.textContent += " · " + shape.toFixed(1) + ":1";
    }
  }
  function show(src, keep) {
    if (!keep) c = start();
    img.onload = function () { stage.hidden = false; tools.hidden = false; render(); };
    img.src = src;
  }

  var drag = null;
  stage.addEventListener("pointerdown", function (e) {
    if (e.target !== box && !e.target.classList.contains("crop-h")) return;
    e.preventDefault();
    box.setPointerCapture(e.pointerId);
    drag = { h: e.target.dataset.h || "move", x: e.clientX, y: e.clientY, start: c.slice() };
  });
  box.addEventListener("pointermove", function (e) {
    if (!drag) return;
    var r = img.getBoundingClientRect(), dx = (e.clientX - drag.x) / r.width, dy = (e.clientY - drag.y) / r.height;
    var s = drag.start, n = s.slice();
    if (drag.h === "move") {
      var w = s[2] - s[0], h = s[3] - s[1];
      n[0] = Math.min(Math.max(0, s[0] + dx), 1 - w); n[2] = n[0] + w;
      n[1] = Math.min(Math.max(0, s[1] + dy), 1 - h); n[3] = n[1] + h;
    } else {
      if (drag.h.indexOf("w") >= 0) n[0] = Math.min(Math.max(0, s[0] + dx), s[2] - MIN);
      if (drag.h.indexOf("e") >= 0) n[2] = Math.max(Math.min(1, s[2] + dx), s[0] + MIN);
      if (drag.h.indexOf("n") >= 0) n[1] = Math.min(Math.max(0, s[1] + dy), s[3] - MIN);
      if (drag.h.indexOf("s") >= 0) n[3] = Math.max(Math.min(1, s[3] + dy), s[1] + MIN);
    }
    c = n; render();
    if (drag.h !== "move") drawLoupe(drag.h, e.clientX, e.clientY);
  });
  box.addEventListener("pointerup", function () { drag = null; loupe.hidden = true; });
  box.addEventListener("pointercancel", function () { drag = null; loupe.hidden = true; });

  // Find a uniform border (white mount, black film rebate, scanner bed) on
  // each side and crop just inside it.
  function autoBorder() {
    var W = Math.min(480, img.naturalWidth), H = Math.round(img.naturalHeight * W / img.naturalWidth);
    var cv = document.createElement("canvas"); cv.width = W; cv.height = H;
    var ctx = cv.getContext("2d"); ctx.drawImage(img, 0, 0, W, H);
    var d = ctx.getImageData(0, 0, W, H).data;
    function lum(x, y) { var i = (y * W + x) * 4; return 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2]; }
    function line(pos, vertical) {
      var out = [], n = vertical ? H : W;
      for (var k = 0; k < n; k++) out.push(vertical ? lum(pos, k) : lum(k, pos));
      return out;
    }
    function median(a) { var b = a.slice().sort(function (p, q) { return p - q; }); return b[b.length >> 1]; }
    // A border is a near-white or near-black band, almost perfectly uniform,
    // ending in a sharp step - so bright skies, mist or snow don't count.
    function frac(pos, vertical, ref) {
      var vals = line(pos, vertical), hit = 0;
      for (var j = 0; j < vals.length; j++) if (Math.abs(vals[j] - ref) < 12) hit++;
      return hit / vals.length;
    }
    function scan(vertical, fromEnd) {
      var n = vertical ? W : H, at = function (k) { return fromEnd ? n - 1 - k : k; };
      var ref = median(line(at(0), vertical));
      if (ref > 28 && ref < 232) return 0;
      var k = 0;
      while (k < n * 0.45 && frac(at(k), vertical, ref) >= 0.97) k++;
      if (k === 0 || k >= n * 0.45) return 0;
      return frac(at(Math.min(n - 1, k + 2)), vertical, ref) < 0.75 ? k : 0;
    }
    var inset = 0.004;
    var l = scan(true, false) / W, r = scan(true, true) / W, t = scan(false, false) / H, b = scan(false, true) / H;
    c = [l ? l + inset : 0, t ? t + inset : 0, r ? 1 - r - inset : 1, b ? 1 - b - inset : 1];
    render();
    if (!l && !r && !t && !b) info.textContent = "No border found";
  }

  // The homepage banner on a desktop screen is about 2.2:1 - fit the largest
  // box of that shape inside the current one, keeping its centre.
  function banner() {
    var BANNER = 2.2, iw = img.naturalWidth, ih = img.naturalHeight;
    var w = (c[2] - c[0]) * iw, h = (c[3] - c[1]) * ih;
    if (w / h > BANNER) w = h * BANNER; else h = w / BANNER;
    var cx = (c[0] + c[2]) / 2, cy = (c[1] + c[3]) / 2, fw = w / iw / 2, fh = h / ih / 2;
    c = [cx - fw, cy - fh, cx + fw, cy + fh];
    render();
  }
  tools.addEventListener("click", function (e) {
    var act = e.target.dataset.act;
    if (act === "auto") autoBorder();
    if (act === "reset") { c = start(); render(); }
    if (act === "banner") banner();
    if (act === "full") setFull(!root.classList.contains("crop-full"));
  });
  // Full screen: the photo as large as the window allows.
  var fullBtn = tools.querySelector("[data-act=full]");
  function setFull(on) {
    root.classList.toggle("crop-full", on);
    document.documentElement.classList.toggle("crop-locked", on);
    fullBtn.textContent = on ? "Done" : "Full screen";
  }
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && root.classList.contains("crop-full")) setFull(false);
  });
  if (file) file.addEventListener("change", function () {
    if (file.files[0]) show(URL.createObjectURL(file.files[0]), false);
  });
  if (root.dataset.src) show(root.dataset.src, true);
});
