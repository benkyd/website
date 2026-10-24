// Tabs (photo edit page): each .tab shows the [data-panel] it names.
document.querySelectorAll(".tab").forEach(function (t, _, all) {
  t.addEventListener("click", function () {
    all.forEach(function (o) {
      o.setAttribute("aria-selected", o === t);
      document.querySelector("[data-panel=" + o.dataset.tab + "]").hidden = o !== t;
    });
  });
});

// /admin/photos#add opens the "Add a photo" panel.
(function () {
  var add = document.getElementById("add");
  if (add && location.hash === "#add") {
    add.open = true;
    add.scrollIntoView({block: "start"});
  }
})();
