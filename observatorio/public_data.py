"""Downloads oficiais com limites, cookies públicos e rastreabilidade."""
import hashlib
import http.cookiejar
import json
import re
import time
import unicodedata
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit, unquote
from urllib.request import Request, build_opener, HTTPCookieProcessor, HTTPRedirectHandler

HOSTS = {'pncp.gov.br', 'cdn.tse.jus.br', 'dadosabertos.tse.jus.br', 'www.caixa.gov.br',
         'www.gov.br', 'arquivos.receitafederal.gov.br', 'api.portaldatransparencia.gov.br',
         'portaldatransparencia.gov.br'}


def official_url(url):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname not in HOSTS or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('URL fora da lista de fontes oficiais HTTPS')
    return url


class OfficialRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        official_url(newurl)
        if req.has_header('Authorization') and urlsplit(req.full_url).hostname != urlsplit(newurl).hostname:
            raise ValueError('Credencial não pode acompanhar redirecionamento externo')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def opener():
    return build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()), OfficialRedirect())


def transient(exc):
    if isinstance(exc, HTTPError):
        return exc.code in (408, 429, 500, 502, 503, 504)
    return isinstance(exc, (HTTPException, URLError, TimeoutError, ConnectionError, OSError))


def read_url(url, *, headers=None, method='GET', limit=12_000_000):
    request = Request(official_url(url), headers={'User-Agent': 'ObservatorioBrasil/0.3', **(headers or {})}, method=method)
    for attempt in range(5):
        try:
            with opener().open(request, timeout=45) as response:
                raw = response.read(limit + 1)
                if len(raw) > limit:
                    raise ValueError('Resposta excede limite')
                return raw
        except Exception as exc:
            if not transient(exc) or attempt == 4:
                raise
            print(f'Fonte {urlsplit(url).hostname}: {method}, {type(exc).__name__}; nova tentativa {attempt + 2}/5.', flush=True)
            time.sleep(2 ** attempt)


def download(url, *, headers=None, version='', limit=350_000_000, seconds=600):
    official_url(url)
    folder = Path('data/downloads')
    folder.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256((url + version).encode()).hexdigest()
    target = folder / key
    manifest = folder / (key + '.json')
    if target.exists() and manifest.exists():
        meta = json.loads(manifest.read_text())
        with target.open('rb') as cached:
            valid = hashlib.file_digest(cached, 'sha256').hexdigest() == meta['sha256']
        if target.stat().st_size <= limit and valid:
            return target, meta['sha256']
    temp = folder / (key + '.part')
    size, digest, start = 0, hashlib.sha256(), time.monotonic()
    try:
        # Retry a disconnected stream from the start: never combine different source versions.
        for attempt in range(5):
            request = Request(url, headers={'User-Agent': 'ObservatorioBrasil/0.3', **(headers or {})})
            size, digest = 0, hashlib.sha256()
            try:
                with opener().open(request, timeout=45) as response, temp.open('wb') as file:
                    expected = response.headers.get('Content-Length')
                    if expected and int(expected) > limit:
                        raise ValueError('Download excede limite de tamanho')
                    while True:
                        if time.monotonic() - start > seconds:
                            raise ValueError('Download excede limite de tempo')
                        block = response.read1(64 * 1024)
                        if not block:
                            break
                        size += len(block)
                        if size > limit:
                            raise ValueError('Download excede limite de tamanho')
                        digest.update(block)
                        file.write(block)
                    if expected and size != int(expected):
                        raise ConnectionError('Transferência incompleta')
                break
            except Exception as exc:
                if not transient(exc) or attempt == 4 or time.monotonic() - start > seconds:
                    raise
                print(f'Download {urlsplit(url).hostname}: {type(exc).__name__}; nova tentativa {attempt + 2}/5.', flush=True)
                time.sleep(2 ** attempt)
        temp.replace(target)
        manifest.write_text(json.dumps(dict(url=url, sha256=digest.hexdigest(), bytes=size)), encoding='utf-8')
        return target, digest.hexdigest()
    finally:
        temp.unlink(missing_ok=True)


def normalize(text):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFKD', str(text or '')) if not unicodedata.combining(c)).upper().split())


class Links(HTMLParser):
    def __init__(self, base):
        super().__init__()
        self.base, self.links = base, []

    def handle_starttag(self, tag, attrs):
        if tag == 'a' and dict(attrs).get('href'):
            self.links.append(urljoin(self.base, dict(attrs)['href']))


def page_links(url):
    parser = Links(url)
    parser.feed(read_url(url).decode('utf-8', 'replace'))
    return sorted(set(parser.links))


def safe_member(name):
    parts = unquote(name.replace('\\', '/')).split('/')
    if name.startswith(('/', '\\')) or ':' in name or '..' in parts:
        raise ValueError('Nome de arquivo inseguro no pacote')
    return name
