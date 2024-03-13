function filtrar() {
    const select = document.getElementById("categoria")
    const categ = select.value.trim();
    document.querySelectorAll("div.evento").forEach(e=>{
        e.style.display = '';
    })
    if (categ.length > 0) document.querySelectorAll("div.evento:not(."+categ+")").forEach(e=>{
        e.style.display = 'none';
    })

    const title = document.querySelector("title");
    const txt = select.selectedOptions[0].textContent.trim().replace(/\s*\(\d+\)\s*$/, "");
    if (categ.length == 0 || txt.length == 0)  title.textContent = window.__title__;
    else title.textContent = window.__title__+": "+txt;
    if (categ.length==0 && document.location.search.length<2) return;
    if (categ.length>0 && document.location.search=='?'+categ) return;
    const url = document.location.href.replace(/\?.*$/,"");
    if (categ.length==0) {
        console.log(document.location.href, "->", url);
        history.pushState({}, "", url);
        title.textContent = window.__title__;
        return;
    }
    console.log(document.location.href, "->", url+'?'+categ);
    history.pushState(categ, "", url+'?'+categ);
}

document.addEventListener("DOMContentLoaded", function () {
    window.__title__ = document.querySelector("title").textContent.trim();
    const value = document.location.search.substring(1);
    const categ = document.getElementById("categoria");
    if (categ.querySelector("option[value='"+value+"']")==null) {
        const url = document.location.href.replace(/\?.*$/,"");
        console.log(document.location.href, "=>", url);
        history.replaceState({}, "", url);
        categ.value = "";
    }
    else categ.value = value;
    categ.addEventListener("change", filtrar)
    filtrar();
});
