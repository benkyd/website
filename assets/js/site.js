// Small progressive enhancements. Everything works without this file.
(function () {
  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Blur-up: images inside .photo-ph sit on a blurred placeholder and fade
  // in once loaded. Also used for photos the homepage adds later.
  function settle(root) {
    (root || document).querySelectorAll(".photo-ph img").forEach(function (img) {
      if (img.complete && img.naturalWidth) { img.classList.add("loaded"); return; }
      img.addEventListener("load", function () { img.classList.add("loaded"); }, { once: true });
      img.addEventListener("error", function () { img.classList.add("loaded"); }, { once: true });
    });
  }
  window.siteSettle = settle;
  settle();

  // Gallery tiles rise in as they scroll into view. Anything already on
  // screen at load is shown straight away so it doesn't flash.
  var tiles = document.querySelectorAll(".reveal");
  if (reduceMotion || !("IntersectionObserver" in window)) {
    tiles.forEach(function (t) { t.classList.add("in"); });
  } else {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
      });
    }, { rootMargin: "0px 0px -40px 0px" });
    tiles.forEach(function (t) {
      if (t.getBoundingClientRect().top < window.innerHeight) t.classList.add("in", "instant");
      else io.observe(t);
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
