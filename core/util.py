import re
from typing import List, Dict, Union, Set, Tuple
from bs4 import Tag, BeautifulSoup
from minify_html import minify
import unicodedata
import requests
import logging
from unidecode import unidecode
from urllib.parse import urlparse
import pytz
from datetime import datetime

logger = logging.getLogger(__name__)

re_sp = re.compile(r"\s+")

tag_concat = ('u', 'ul', 'ol', 'i', 'em', 'strong')
tag_round = ('u', 'i', 'em', 'span', 'strong', 'a')
tag_trim = ('li', 'th', 'td', 'div', 'caption', 'h[1-6]')
tag_right = ('p',)
heads = ("h1", "h2", "h3", "h4", "h5", "h6")
block = heads + ("p", "div", "table", "article")
inline = ("span", "strong", "i", "em", "u", "b", "del")


def get_domain(url):
    parsed_url = urlparse(url)
    domain: str = parsed_url.netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


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
    while True:
        new_html = __simplify_html(html)
        if new_html == html:
            return new_html
        html = new_html


def __simplify_html(html: str):
    html = re_sp.sub(" ", html)
    html = minify(
        html,
        do_not_minify_doctype=True,
        ensure_spec_compliant_unquoted_attribute_values=True,
        keep_spaces_between_attributes=True,
        keep_html_and_head_opening_tags=True,
        keep_closing_tags=True,
        minify_js=True,
        minify_css=True,
        remove_processing_instructions=True
    )
    blocks = ("html", "head", "body", "style", "script", "meta", "p", "div", "main", "header", "footer",
              "table", "tr", "tbody", "thead", "tfoot" "ol", "li", "ul", "h1", "h2", "h3", "h4", "h5", "h6")
    html = re.sub(r"<(" + "|".join(blocks) +
                  "\b)([^>]*)>", r"\n<\1\2>\n", html)
    html = re.sub(r"</(" + "|".join(blocks) + ")>", r"\n</\1>\n", html)
    html = re.sub(r"\n\n+", r"\n", html).strip()
    soup = BeautifulSoup("<faketag>"+html+"<faketag>", "html.parser")
    for n in soup.findAll(["span", "font"]):
        n.unwrap()
    for a in soup.findAll("a"):
        href = a.attrs.get("href")
        if href in (None, "", "#"):
            a.unwrap()
    useful = ("href", "src", "alt", "title")
    for n in tuple(soup.select(":scope *")):
        if n.attrs:
            n.attrs = {k: v for k, v in n.attrs.items() if k in useful}
    for n in soup.findAll(block + inline):
        chls = n.select(":scope > *")
        if len(chls) != 1:
            continue
        c = chls[0]
        if c.name != n.name or get_text(c) != get_text(n):
            continue
        n.unwrap()
    for br in soup.select("p br"):
        br.replace_with(" ")
    for n in soup.findAll("faketag"):
        n.unwrap()
    return clean_html(str(soup))


def clean_js_obj(obj: Union[List, Dict, str]):
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
    s = re.sub(r"[´”]", "'", s)
    s = re.sub(r"\s*[\.,]+\s*$", "", s)
    s = unicodedata.normalize('NFC', s)
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


def dict_add(obj: Dict[str, Set], a: str, b: Union[str, int, List[str], Set[str], Tuple[str]]):
    if a not in obj:
        obj[a] = set()
    if isinstance(b, (str, int)):
        obj[a].add(b)
    else:
        obj[a] = obj[a].union(b)


def dict_tuple(obj: Dict[str, Union[Set, List, Tuple]]):
    return {k: tuple(sorted(set(v))) for k, v in obj.items()}


def safe_get_list_dict(url) -> List[Dict]:
    js = []
    try:
        r = requests.get(url)
        js = r.json()
    except Exception:
        logger.critical(url+" no se puede recuperar", exc_info=True)
        pass
    if not isinstance(js, list):
        logger.critical(url+" no es una lista")
        return []
    for i in js:
        if not isinstance(i, dict):
            logger.critical(url+" no es una lista de diccionarios")
            return []
    return js


def safe_get_dict(url) -> Dict:
    js = {}
    try:
        r = requests.get(url)
        js = r.json()
    except Exception:
        logger.critical(url+" no se puede recuperar", exc_info=True)
        pass
    if not isinstance(js, dict):
        logger.critical(url+" no es un diccionario")
        return {}
    return js


def plain_text(s: Union[str, Tag], is_html=False):
    if s is None:
        return None
    if isinstance(s, str) and is_html:
        s = BeautifulSoup(s, "html.parser")
    if isinstance(s, Tag):
        for n in s.findAll(["p", "br"]):
            n.insert_after(" ")
        s = get_text(s)
    faken = "&%%%#%%%#%%#%%%%%%&"
    s = re.sub(r"[,\.:\(\)\[\]¡!¿\?]", " ", s).lower()
    s = s.replace("ñ", faken)
    s = unidecode(s)
    s = s.replace(faken, "ñ")
    s = re_sp.sub(" ", s).strip()
    if len(s) == 0:
        return None
    return s


def re_or(s: str, *args: Union[str, Tuple[str]]):
    if s is None or len(s) == 0 or len(args) == 0:
        return None
    for r in args:
        if isinstance(r, tuple):
            b = re_and(s, *r)
            if b is not None:
                return b
        elif re.search(r"\b" + r + r"\b", s):
            return r
    return None


def re_and(s: str, *args: Union[str, Tuple[str]]):
    if s is None or len(s) == 0 or len(args) == 0:
        return None
    arr = []
    for r in args:
        if isinstance(r, tuple):
            b = re_or(s, *r)
            if b is None:
                return None
            arr.append(b)
        elif re.search(r"\b" + r + r"\b", s):
            arr.append(r)
        else:
            return None
    return " AND ".join(arr)


def get_redirect(url: str):
    r = requests.get(url, allow_redirects=False)
    return r.headers.get('Location')


def to_datetime(s: str):
    if s is None:
        return None
    tz = pytz.timezone('Europe/Madrid')
    if len(s) == 10:
        dt = datetime.strptime(s, "%Y-%m-%d")
    else:
        dt = datetime.strptime(s, "%Y-%m-%d %H:%M")
    dt = tz.localize(dt)
    return dt


def get_chunks(arr: List, size: int):
    chunk = []
    for a in arr:
        chunk.append(a)
        if len(chunk) == size:
            yield chunk
            chunk = []
    if len(chunk) > 0:
        yield chunk


def get_joins(arr: List, sep: str, size: int):
    line = ""
    lsep = len(sep)
    for a in arr:
        if (len(line) + len(a) - lsep) > size:
            yield line[lsep:]
            line = ""
        line = line + sep + a
    if len(line) > 0:
        yield line[lsep:]
