import re
from typing import List, Dict, Union
from bs4 import Tag

re_sp = re.compile(r"\s+")


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