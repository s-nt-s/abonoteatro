import os
import re
import time
from urllib.parse import parse_qsl, urljoin, urlsplit
import curlify


import requests
from bs4 import BeautifulSoup, Tag
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.chrome import ChromeType
from webdriver_manager.core.utils import read_version_from_cmd
from webdriver_manager.core.os_manager import PATTERN
from selenium import webdriver
from seleniumwire import webdriver as wirewebdriver
from selenium.common.exceptions import (ElementNotInteractableException,
                                        ElementNotVisibleException,
                                        StaleElementReferenceException,
                                        TimeoutException, WebDriverException)
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.options import Options as CMoptions
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.proxy import Proxy, ProxyType
from selenium.webdriver.firefox.options import Options as FFoptions
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
import logging
from typing import Union
import random
from functools import wraps

logger = logging.getLogger(__name__)

re_sp = re.compile(r"\s+")
re_emb = re.compile(r"^image/[^;]+;base64,.*", re.IGNORECASE)
is_s5h = os.environ.get('http_proxy', "").startswith("socks5h://")
if is_s5h:
    proxy_ip, proxy_port = os.environ['http_proxy'].split(
        "//", 1)[-1].split(":")
    proxy_port = int(proxy_port)

default_headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:54.0) Gecko/20100101 Firefox/54.0',
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Expires": "Thu, 01 Jan 1970 00:00:00 GMT",
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'es-ES,es;q=0.8,en-US;q=0.5,en;q=0.3',
    'Accept-Encoding': 'gzip, deflate, br',
    'DNT': '1',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}


def mk_delay(name, min_delay=1, max_delay=3):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = random.uniform(min_delay, max_delay)
            time.sleep(delay)
            return func(*args, **kwargs)
        return wrapper
    return decorator


def get_query(url):
    q = urlsplit(url)
    q = parse_qsl(q.query)
    q = dict(q)
    return q


def iterhref(soup: BeautifulSoup):
    """Recorre los atributos href o src de los tags"""
    n: Tag
    for n in soup.findAll(["img", "form", "a", "iframe", "frame", "link", "script", "input"]):
        attr = "href" if n.name in ("a", "link") else "src"
        if n.name == "form":
            attr = "action"
        val = n.attrs.get(attr)
        if val is None or re_emb.search(val):
            continue
        if not (val.startswith("#") or val.startswith("javascript:")):
            yield n, attr, val


def buildSoup(root: str, source: str, parser="lxml"):
    soup = BeautifulSoup(source, parser)
    for n, attr, val in iterhref(soup):
        val = urljoin(root, val)
        n.attrs[attr] = val
    return soup


def get_text(node: Tag, default: str = None):
    if node is None:
        return default
    txt = None
    if node.name == "input":
        txt = node.attrs.get("value")
        if txt is None:
            txt = node.attrs.get("src")
    else:
        txt = node.get_text()
    if txt is None:
        return default
    txt = re_sp.sub(" ", txt).strip()
    if len(txt) == 0:
        return default
    return txt


class Web:
    def __init__(self, refer=None, verify=True):
        self.s = requests.Session()
        self.s.headers = default_headers
        self.response = None
        self.soup = None
        self.form = None
        self.refer = refer
        self.verify = verify

    def _get(self, url, allow_redirects=True, auth=None, headers=None, **kwargs):
        if kwargs:
            return self.s.post(url, headers=headers, data=kwargs, allow_redirects=allow_redirects, verify=self.verify, auth=auth)
        return self.s.get(url, headers=headers, allow_redirects=allow_redirects, verify=self.verify, auth=auth)

    def curlify(self):
        if self.response is None:
            return None
        return curlify.to_curl(self.response.request)

    def get(self, url, auth=None, parser="lxml", headers=None, **kwargs):
        if self.refer:
            self.s.headers.update({'referer': self.refer})
        self.response = self._get(url, auth=auth, headers=headers, **kwargs)
        self.refer = self.response.url
        self.soup = buildSoup(url, self.response.content, parser=parser)
        return self.soup

    def prepare_submit(self, slc, silent_in_fail=False, **kwargs):
        data = {}
        self.form = self.soup.select_one(slc)
        if silent_in_fail and self.form is None:
            return None, None
        for i in self.form.select("input[name]"):
            name = i.attrs["name"]
            data[name] = i.attrs.get("value")
        for i in self.form.select("select[name]"):
            name = i.attrs["name"]
            slc = i.select_one("option[selected]")
            slc = slc.attrs.get("value") if slc else None
            data[name] = slc
        data = {**data, **kwargs}
        action = self.form.attrs.get("action")
        action = action.rstrip() if action else None
        if action is None:
            action = self.response.url
        return action, data

    def submit(self, slc, silent_in_fail=False, **kwargs):
        action, data = self.prepare_submit(
            slc, silent_in_fail=silent_in_fail, **kwargs)
        if silent_in_fail and not action:
            return None
        return self.get(action, **data)

    def val(self, slc):
        n = self.soup.select_one(slc)
        if n is None:
            return None
        v = n.attrs.get("value", n.get_text())
        v = v.strip()
        return v if v else None

    @property
    def url(self):
        if self.response is None:
            return None
        return self.response.url

    def json(self, url, **kwargs):
        r = self._get(url, **kwargs)
        return r.json()

    def resolve(self, url, **kwargs):
        if self.refer:
            self.s.headers.update({'referer': self.refer})
        r = self._get(url, allow_redirects=False, **kwargs)
        if r.status_code in (302, 301):
            return r.headers['location']


FF_DEFAULT_PROFILE = {
    "browser.tabs.drawInTitlebar": True,
    "browser.uidensity": 1,
    "dom.webdriver.enabled": False
}


class Driver:
    DRIVER_PATH = None

    @staticmethod
    def find_driver_path():
        if Driver.DRIVER_PATH is None:
            def get_version(path):
                if os.path.isfile(path):
                    return read_version_from_cmd(
                        path+" --version",
                        PATTERN[ChromeType.CHROMIUM]
                    )
            Driver.DRIVER_PATH = ChromeDriverManager(
                driver_version=get_version("/usr/bin/chromium"),
                chrome_type=ChromeType.CHROMIUM
            ).install()
        return Driver.DRIVER_PATH

    def __init__(self, browser=None, wait=60, useragent=None, human_delay=-1):
        # Driver.find_driver_path()
        self.__driver: WebDriver = None
        self.__visible = (os.environ.get("DRIVER_VISIBLE") == "1")
        self.__wait = wait
        self.__useragent = useragent
        self.__browser = browser
        self.__human_delay = human_delay

    def __enter__(self, *args, **kwargs):
        return self

    def __exit__(self, *args, **kwargs):
        self.close()

    def _create_firefox(self):
        options = FFoptions()
        options.headless = not self.__visible
        profile = webdriver.FirefoxProfile()
        if self.__useragent:
            profile.set_preference(
                "general.useragent.override", self.__useragent)
        for k, v in FF_DEFAULT_PROFILE.items():
            profile.set_preference(k, v)
            profile.DEFAULT_PREFERENCES['frozen'][k] = v
        profile.update_preferences()
        driver = webdriver.Firefox(
            options=options, firefox_profile=profile)
        driver.maximize_window()
        driver.implicitly_wait(5)
        return driver

    def _create_chrome(self):
        options = CMoptions()
        if not self.__visible:
            options.add_argument('headless')
        if self.__useragent:
            options.add_argument('user-agent=' + self.__useragent)
        options.add_argument("start-maximized")
        options.add_argument("--disable-extensions")
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument("--lang=es-ES")
        options.add_experimental_option(
            'excludeSwitches', ['enable-automation'])
        options.add_experimental_option('useAutomationExtension', False)

        if is_s5h:
            prox = Proxy()
            prox.proxy_type = ProxyType.MANUAL
            prox.socks_proxy = "{}:{}".format(proxy_ip, proxy_port)
            prox.socksVersion = 5
            capabilities = webdriver.DesiredCapabilities.CHROME
            prox.add_to_capabilities(capabilities)
            driver = webdriver.Chrome(
                Driver.find_driver_path(),
                options=options,
                desired_capabilities=capabilities
            )
        else:
            driver = webdriver.Chrome(
                Driver.find_driver_path(),
                options=options
            )
        driver.maximize_window()
        driver.implicitly_wait(5)
        return driver

    def _create_wirefirefox(self):
        options = FFoptions()
        options.headless = not self.__visible
        profile = wirewebdriver.FirefoxProfile()
        if self.__useragent:
            profile.set_preference(
                "general.useragent.override", self.__useragent)
        for k, v in FF_DEFAULT_PROFILE.items():
            profile.set_preference(k, v)
            profile.DEFAULT_PREFERENCES['frozen'][k] = v
        profile.update_preferences()
        driver = wirewebdriver.Firefox(
            options=options, firefox_profile=profile)
        driver.maximize_window()
        driver.implicitly_wait(5)
        return driver

    def __build_driver(self):
        crt = getattr(self, "_create_" + str(self.__browser), None)
        if crt is None:
            raise Exception("Not implemented yet: %s" % self.__browser)
        driver = crt()
        if self.__human_delay > 1:
            mths = ('get', 'find_element', 'find_elements', 'click', 'send_keys')
            for m in dir(driver):
                if not (m in mths or m.startswith("find_element") or m.startswith("move_to")):
                    continue
                ori = getattr(driver, m, None)
                if not callable(ori):
                    continue
                logger.info(f"Driver.{m} set delay")
                new_mth = mk_delay(f"Driver.{m}", max_delay=self.__human_delay)(ori)

                setattr(
                    driver,
                    m,
                    new_mth
                )
        return driver


    @property
    def driver(self):
        if self.__driver is None:
            self.__driver = self.__build_driver()
        return self.__driver

    def close(self, *windows):
        if self.__driver:
            sz = len(self.__driver.window_handles)
            if len(windows) in (0, sz):
                self.__driver.quit()
                self.__driver = None
                return
            for w in reversed(windows):
                self.__driver.switch_to.window(w)
                self.__driver.close()
            self.__driver.switch_to.window(self.__driver.window_handles[0])

    def close_others(self, current=None):
        if self.__driver:
            if current is None:
                current = self.__driver.current_window_handle
            elif isinstance(current, int):
                current = self.__driver.window_handles[current]
            windows = [w for w in self.__driver.window_handles if w != current]
            if windows:
                self.close(*windows)

    def switch(self, window):
        if isinstance(window, int):
            window = self.__driver.window_handles[window]
        self.__driver.switch_to.window(window)

    def reintentar(self, intentos, sleep=1):
        if intentos > 50:
            return False, sleep
        if intentos % 3 == 0:
            sleep = int(sleep / 3)
            self.close()
        else:
            sleep = sleep*2
        if intentos > 20:
            time.sleep(10)
        time.sleep(2 * (int(intentos/10)+1))
        return True, sleep

    def get(self, url):
        logger.debug(url)
        self.driver.get(url)

    def get_soup(self, root: str = None):
        if self.__driver is None:
            return None
        if root is None:
            root = self.__driver.current_url
        return buildSoup(root, self.__driver.page_source)

    @property
    def current_url(self):
        if self.__driver is None:
            return None
        return self.__driver.current_url

    @property
    def source(self):
        if self.__driver is None:
            return None
        return self.__driver.page_source

    def wait(self, id: Union[int, float, str], seconds=None, presence=False, by=None) -> WebElement:
        if isinstance(id, (int, float)):
            time.sleep(id)
            return
        if seconds is None:
            seconds = self.__wait
        if by is None:
            by = By.ID
            if id.startswith("//"):
                by = By.XPATH
            if id.startswith("."):
                by = By.CSS_SELECTOR
        wait = WebDriverWait(self.__driver, seconds)
        if presence:
            wait.until(ec.presence_of_element_located((by, id)))
        else:
            wait.until(ec.visibility_of_element_located((by, id)))
        if by == By.CLASS_NAME:
            return self.__driver.find_element_by_class_name(id)
        if by == By.CSS_SELECTOR:
            return self.__driver.find_element_by_css_selector(id)
        if by == By.XPATH:
            return self.__driver.find_element_by_xpath(id)
        return self.__driver.find_element_by_id(id)

    def waitjs(self, js: str, val=True, seconds=None):
        if seconds is None:
            seconds = self.__wait
        js = js.strip()

        if not js.startswith("return "):
            js = 'return '+js

        def do_js(w: WebDriver):
            rt = w.execute_script(js)
            if callable(val):
                return val(rt)
            return rt == val

        wait = WebDriverWait(self.__driver, seconds)
        wait.until(do_js)

    def safe_wait(self, *ids, **kvarg):
        for id in ids:
            if isinstance(id, WebElement):
                return id
            try:
                return self.wait(id, **kvarg)
            except TimeoutException:
                pass
        return None

    def val(self, n, val=None, **kwargs):
        if n is None or self.__driver is None:
            return None
        if isinstance(n, str):
            n = self.wait(n, **kwargs)
        if val is not None:
            n.clear()
            n.send_keys(val)
        return n.text

    def click(self, n, **kvarg):
        if n is None or self.__driver is None:
            return None
        if isinstance(n, str):
            n = self.wait(n, **kvarg)
        if n.is_displayed():
            ActionChains(self.__driver).move_to_element(n).click(n).perform()
            # n.click()
        else:
            n.send_keys(Keys.RETURN)
        return True

    def safe_click(self, *ids, after=None, force_return=False, **kvarg):
        if len(ids) == 1 and not isinstance(ids[0], str):
            n = ids[0]
        else:
            n = self.safe_wait(*ids, **kvarg)
        if n is None:
            return -1
        try:
            if n.is_displayed() and not force_return:
                n.click()
            else:
                n.send_keys(Keys.RETURN)
        except (
                ElementNotInteractableException,
                StaleElementReferenceException,
                ElementNotVisibleException,
                WebDriverException
        ):
            return 0
        if after is not None:
            time.sleep(after)
        return 1

    def execute_script(self, *args, **kwargs):
        return self.driver.execute_script(*args, **kwargs)

    def pass_cookies(self, session=None):
        if self.__driver is None:
            return session
        if session is None:
            session = requests.Session()
        for cookie in self.__driver.get_cookies():
            session.cookies.set(cookie['name'], cookie['value'])
        return session

    def to_web(self):
        w = Web()
        self.pass_cookies(w.s)
        return w

    def run_script(self, file: str):
        with open(file, "r") as f:
            js = f.read()
        return self.execute_script(js)
