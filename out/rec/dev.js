document.addEventListener("DOMContentLoaded", function () {
    document.body.classList.add("js");
    if (document.location.protocol != "file:") return;
    Array.from(document.getElementsByTagName("a")).forEach(a => {
        if (a.protocol != "file:") return;
        if (a.pathname.endsWith("/")) {
            a.pathname = a.pathname + "index.html"
            return;
        }
        if (a.pathname.match(/.*\/e\/\d+$/)) {
            a.pathname = a.pathname + ".html"
            return;
        }
    });
});