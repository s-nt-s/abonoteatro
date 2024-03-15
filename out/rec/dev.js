const INPUT_DATE_SUPPORT=(() => {
    const div = document.createElement("div");
    div.innerHTML='<input type="date" value="2024-01-01"/>'
    const i = div.querySelector("input");
    if (i.tagName!="INPUT" || i.getAttribute("type")!="date") return false;
    if (i.valueAsDate == null) return false;
    if (!(i.valueAsDate instanceof Date) || isNaN(i.valueAsDate)) return false;
    return true;
})();

document.addEventListener("DOMContentLoaded", function () {
    document.body.classList.add("js");
    if (!INPUT_DATE_SUPPORT) {
        document.body.classList.add("noinputdate");
    }
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