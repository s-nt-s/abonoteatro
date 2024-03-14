from functools import cached_property

from requests import Session
from requests.exceptions import RequestException, ConnectionError
from urllib.parse import urlencode
from json.decoder import JSONDecodeError
import logging
from .cache import Cache
from typing import Tuple, Dict

logger = logging.getLogger(__name__)


def myex(e, msg):
    largs = list(e.args)
    if len(largs) == 1 and isinstance(largs, str):
        largs[0] = largs[0]+' '+msg
    else:
        largs.append(msg)
    e.args = tuple(largs)
    return e


class WP:
    def __init__(self, s: Session, url: str):
        self.s = s
        self.last_url = None
        self.url = url.rstrip("/")
        self.rest_route = self.url + "/?rest_route="
        self.info = self.get("/")

    def __json(self, url):
        r = self.s.get(url)
        self.last_url = r.url
        try:
            js = r.json()
            return js
        except (JSONDecodeError, RequestException, ConnectionError) as e:
            raise myex(e, f'in request.get("{url}").json()')

    def get(self, path):
        url = self.rest_route+path
        js = self.__json(url)
        logger.info(f"{len(js):>4} {url}")
        return js

    def get_objects(self, tp, size=100, page=1, **kargv):
        url = "/wp/v2/{}/&per_page={}&page={}".format(tp, size, page)
        if "offset" in kargv and kargv["offset"] in (None, 0):
            del kargv["offset"]
        if kargv:
            url = url + "&" + urlencode(kargv, doseq=True)
        return self.get(url)

    def get_object(self, tp, id):
        url = "/wp/v2/{}/{}".format(tp, id)
        js = self.get(url)
        return js

    def safe_get_object(self, tp, size=100, page=1, **kargv):
        try:
            return self.get_objects(tp, size=size, page=page, orderby='id', order='asc', **kargv)
        except JSONDecodeError:
            pass
        offset = kargv.get("offset", 0)
        offset = offset + ((size)*(page-1))
        if "offset" in kargv:
            del kargv["offset"]
        if size % 2 == 0:
            n_size = int(size / 2)
            r1 = self.safe_get_object(tp, size=n_size, page=1, offset=offset, **kargv)
            r2 = self.safe_get_object(tp, size=n_size, page=2, offset=offset, **kargv)
            return r1 + r2
        if size % 3 == 0:
            n_size = int(size / 3)
            r1 = self.safe_get_object(tp, size=n_size, page=1, offset=offset, **kargv)
            r2 = self.safe_get_object(tp, size=n_size, page=2, offset=offset, **kargv)
            r3 = self.safe_get_object(tp, size=n_size, page=3, offset=offset, **kargv)
            return r1 + r2 + r3
        rs = []
        for p in range(1, size+1):
            try:
                r = self.get_objects(tp, size=1, page=p, offset=offset, orderby='id', order='asc', **kargv)
                if isinstance(r, list) and len(r) > 0:
                    rs.extend(r)
                else:
                    return rs
            except JSONDecodeError:
                pass
        return rs

    @Cache("rec/wp/{0}.json")
    def get_all_objects(self, tp, size=100, **kargv):
        rs = {}
        page = 0
        while True:
            page = page + 1
            r = self.safe_get_object(tp, size=size, page=page, **kargv)
            if isinstance(r, list) and len(r) > 0:
                for i in r:
                    rs[i["id"]] = i
            else:
                return sorted(rs.values(), key=lambda x: x["id"])

    @cached_property
    def error(self):
        js = self.get_objects("posts", size=1)
        if "code" in js:
            return js["code"] + " " + self.last_url
        return None

    @cached_property
    def posts(self) -> Tuple[Dict]:
        return tuple(self.get_all_objects("posts"))

    @cached_property
    def pages(self) -> Tuple[Dict]:
        return tuple(self.get_all_objects("pages"))

    @cached_property
    def media(self) -> Tuple[Dict]:
        return tuple(self.get_all_objects("media"))

    @cached_property
    def comments(self) -> Tuple[Dict]:
        return tuple(self.get_all_objects("comments"))

    @cached_property
    def users(self) -> Tuple[Dict]:
        return self.get_all_objects("users")

    @cached_property
    def tags(self) -> Tuple[Dict]:
        tags = self.get_all_objects("tags")
        ids = set(i["id"] for i in tags)
        falta = set()
        for p in self.posts + self.pages:
            for t in p.get("tags", []):
                if t not in ids:
                    falta.add(t)
        for id in falta:
            t = self.get_object("tags", id)
            tags.append(t)
        return tuple(tags)

    @cached_property
    def categories(self) -> Tuple[Dict]:
        categories = self.get_all_objects("categories")
        ids = set(i["id"] for i in categories)
        falta = set()
        for p in self.posts + self.pages:
            for t in p.get("categories", []):
                if t not in ids:
                    falta.add(t)
        for id in falta:
            t = self.get_object("categories", id)
            categories.append(t)
        return tuple(categories)
