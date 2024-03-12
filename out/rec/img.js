function add_class_to_img(i) {
    if (!i.complete || i.naturalWidth == 0) return;
    i.classList.add("loaded");
    if (i.naturalWidth>=i.naturalHeight) i.classList.add("landscape");
    else i.classList.add("portrait");
}

document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll("img").forEach((i) => {
    if (i.complete && i.naturalWidth !== 0) add_class_to_img(i);
    else i.addEventListener("load", (e) => add_class_to_img(e.target));
  });
});
