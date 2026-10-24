document.querySelectorAll(".drop").forEach(function (zone) {
  var input = zone.querySelector("input[type=file]"), name = zone.querySelector(".drop-file"), depth = 0;
  function shown() {
    var f = input.files[0];
    zone.classList.toggle("has", !!f);
    name.textContent = f ? f.name + " · " + (f.size / 1048576).toFixed(1) + " MB" : "";
  }
  zone.feed = function (files) {
    var f = Array.prototype.find.call(files || [], function (f) { return /\.(jpe?g|png|webp)$/i.test(f.name); });
    if (!f) { alert("Only jpg, png or webp files can be added."); return; }
    var dt = new DataTransfer(); dt.items.add(f); input.files = dt.files;
    input.dispatchEvent(new Event("change", {bubbles: true}));
  };
  input.addEventListener("change", shown);
  zone.addEventListener("dragenter", function (e) { e.preventDefault(); depth++; zone.classList.add("over"); });
  zone.addEventListener("dragover", function (e) { e.preventDefault(); });
  zone.addEventListener("dragleave", function () { if (--depth <= 0) { depth = 0; zone.classList.remove("over"); } });
  zone.addEventListener("drop", function (e) {
    e.preventDefault(); depth = 0; zone.classList.remove("over"); zone.feed(e.dataTransfer.files);
  });
  shown();
});
// A file dropped anywhere else on the page goes to the drop zone too, rather
// than the browser navigating away to show it.
(function () {
  var depth = 0, root = document.documentElement;
  function files(e) { return e.dataTransfer && Array.prototype.indexOf.call(e.dataTransfer.types, "Files") >= 0; }
  document.addEventListener("dragenter", function (e) { if (files(e)) { depth++; root.classList.add("dragging"); } });
  document.addEventListener("dragleave", function () { if (--depth <= 0) { depth = 0; root.classList.remove("dragging"); } });
  document.addEventListener("dragover", function (e) { if (files(e)) e.preventDefault(); });
  document.addEventListener("drop", function (e) {
    depth = 0; root.classList.remove("dragging");
    if (!files(e) || e.defaultPrevented) return;
    e.preventDefault();
    var zone = document.querySelector(".drop");
    if (!zone) return;
    var panel = zone.closest("details");
    if (panel) panel.open = true;
    zone.feed(e.dataTransfer.files);
    zone.scrollIntoView({block: "center", behavior: "smooth"});
  });
})();
// Uploads take a while; stop a second click sending the photo twice.
document.querySelectorAll("form[enctype]").forEach(function (form) {
  form.addEventListener("submit", function () {
    var btn = form.querySelector("button[type=submit]");
    if (btn) { btn.disabled = true; btn.textContent = btn.dataset.busy || "Working…"; }
  });
});
