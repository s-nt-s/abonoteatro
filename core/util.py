import re
from typing import List, Dict, Union
from bs4 import Tag, BeautifulSoup

re_sp = re.compile(r"\s+")

tag_concat = ('u', 'ul', 'ol', 'i', 'em', 'strong')
tag_round = ('u', 'i', 'em', 'span', 'strong', 'a')
tag_trim = ('li', 'th', 'td', 'div', 'caption', 'h[1-6]')
tag_right = ('p',)
heads = ("h1", "h2", "h3", "h4", "h5", "h6")
block = heads + ("p", "div", "table", "article")
inline = ("span", "strong", "b", "del")


def clean_html(html: str):
    soup = BeautifulSoup(html, "html.parser")
    for div in soup.findAll(["div", "p"]):
        if not div.find("img"):
            txt = div.get_text()
            txt = re_sp.sub("", txt)
            if len(txt) == 0:
                div.extract()
    h = str(soup)
    r = re.compile("(\s*\.\s*)</a>", re.MULTILINE | re.DOTALL | re.UNICODE)
    h = r.sub("</a>\\1", h)
    for t in tag_concat:
        r = re.compile(
            "</" + t + ">(\s*)<" + t + ">", re.MULTILINE | re.DOTALL | re.UNICODE)
        h = r.sub("\\1", h)
    for t in tag_round:
        r = re.compile(
            "(<" + t + ">)(\s+)", re.MULTILINE | re.DOTALL | re.UNICODE)
        h = r.sub("\\2\\1", h)
        r = re.compile(
            "(<" + t + " [^>]+>)(\s+)", re.MULTILINE | re.DOTALL | re.UNICODE)
        h = r.sub("\\2\\1", h)
        r = re.compile(
            "(\s+)(</" + t + ">)", re.MULTILINE | re.DOTALL | re.UNICODE)
        h = r.sub("\\2\\1", h)
    for t in tag_trim:
        r = re.compile(
            "(<" + t + ">)\s+", re.MULTILINE | re.DOTALL | re.UNICODE)
        h = r.sub("\\1", h)
        r = re.compile(
            "\s+(</" + t + ">)", re.MULTILINE | re.DOTALL | re.UNICODE)
        h = r.sub("\\1", h)
    for t in tag_right:
        r = re.compile(
            "\s+(</" + t + ">)", re.MULTILINE | re.DOTALL | re.UNICODE)
        h = r.sub("\\1", h)
        r = re.compile(
            "(<" + t + ">) +", re.MULTILINE | re.DOTALL | re.UNICODE)
        h = r.sub("\\1", h)
    r = re.compile(
        r"\s*(<meta[^>]+>)\s*", re.MULTILINE | re.DOTALL | re.UNICODE)
    h = r.sub(r"\n\1\n", h)
    r = re.compile(r"\n\n+", re.MULTILINE | re.DOTALL | re.UNICODE)
    h = re.sub(r"<p([^<>]*)>\s*<br/?>\s*", r"<p\1>", h,
               flags=re.MULTILINE | re.DOTALL | re.UNICODE)
    h = re.sub(r"\s*<br/?>\s*</p>", "</p>", h,
               flags=re.MULTILINE | re.DOTALL | re.UNICODE)
    h = r.sub(r"\n", h)
    return h


def simplify_html(html: str):
    soup = BeautifulSoup("<faketag>"+html+"<faketag>", "html.parser")
    for n in soup.findAll(["span", "font"]):
        n.unwrap()
    for a in soup.findAll("a"):
        href = a.attrs.get("href")
        if href in (None, "", "#"):
            a.unwrap()
    useful = ("href", "src")
    for n in tuple(soup.select(":scope *")):
        if n.attrs:
            n.attrs = {k: v for k, v in n.attrs.items() if k in useful}
    for n in soup.findAll("faketag"):
        n.unwrap()
    return clean_html(str(soup))


def clean_js_obj(obj: Union[List, Dict]):
    if isinstance(obj, dict):
        for k in set(obj.keys()).intersection(("nabonado", )):
            del obj[k]
        return {k: clean_js_obj(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean_js_obj(v) for v in obj]
    if not isinstance(obj, str):
        return obj
    v = obj.strip()
    if v in ("", "undefined", "null"):
        return None
    if v in ("true", "false"):
        return v == "true"
    if re.match(r"^\d+(\.\d+)?$", v):
        return to_int(v)
    if "</p>" in v or "</div>" in v:
        return clean_html(v)
    return v


def clean_txt(s: str):
    if s is None:
        return None
    if s == s.upper():
        s = s.title()
    s = re.sub(r"\\", "", s)
    s = re.sub(r"´", "'", s)
    return s


def to_int(s: str):
    f = float(s)
    i = int(f)
    if f == i:
        return i
    return f


def get_obj(*args, **kwargs) -> dict:
    if len(args) != 0 and len(kwargs) != 0:
        raise ValueError()
    if len(args) > 1:
        raise ValueError()
    if len(args) == 0:
        return kwargs
    obj = args[0]
    if not isinstance(obj, (dict, list)):
        raise ValueError()
    return obj


def trim(s: str):
    if s is None:
        return None
    s = s.strip()
    if len(s) == 0:
        return None
    return s


def get_text(n: Tag):
    if n is None:
        return None
    txt = n.get_text()
    txt = re_sp.sub(r" ", txt)
    txt = txt.strip()
    if len(txt) == 0:
        return None
    return txt


def get_or(obj: Dict, *args):
    for k in args:
        v = obj.get(k)
        if v is not None:
            return v
    raise KeyError(", ".join(map(str, args)))
