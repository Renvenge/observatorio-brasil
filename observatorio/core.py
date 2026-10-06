import hashlib
import json
import math
import sqlite3
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = 'https://pncp.gov.br/api/consulta/v1/contratos'


def now():
    return datetime.now(timezone.utc).isoformat()


def connect(path):
    db = sqlite3.connect(path)
    db.execute('PRAGMA journal_mode=WAL')
    db.executescript('''
      CREATE TABLE IF NOT EXISTS runs (
        id INTEGER PRIMARY KEY, started TEXT, finished TEXT,
        start_date TEXT, end_date TEXT, status TEXT, records INTEGER DEFAULT 0,
        pages INTEGER DEFAULT 0, error TEXT);
      CREATE TABLE IF NOT EXISTS snapshots (
        id INTEGER PRIMARY KEY, contract_id TEXT NOT NULL, digest TEXT NOT NULL,
        collected_at TEXT NOT NULL, source_url TEXT NOT NULL,
        payload TEXT NOT NULL, UNIQUE(contract_id, digest));
      CREATE TABLE IF NOT EXISTS contracts (
        id TEXT PRIMARY KEY, snapshot_id INTEGER NOT NULL, last_seen TEXT NOT NULL);
    ''')
    return db


def request_json(url):
    for attempt in range(4):
        try:
            req = Request(url, headers={'Accept': 'application/json',
                                        'User-Agent': 'ObservatorioBrasil/0.1'})
            with urlopen(req, timeout=45) as response:
                if response.status == 204:
                    return None
                return json.load(response)
        except HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 3:
                raise
            retry = exc.headers.get('Retry-After', '')
            delay = min(int(retry), 60) if retry.isdigit() else 2 ** attempt
        except (URLError, TimeoutError):
            if attempt == 3:
                raise
            delay = 2 ** attempt
        time.sleep(delay)


def save(db, record, url):
    cid = record.get('numeroControlePNCP')
    if not isinstance(cid, str) or not cid.strip():
        raise ValueError('Registro sem identificador PNCP: coleta não concluída.')
    raw = json.dumps(record, ensure_ascii=False, sort_keys=True, allow_nan=False)
    digest = hashlib.sha256(raw.encode()).hexdigest()
    timestamp = now()
    db.execute('INSERT OR IGNORE INTO snapshots '
               '(contract_id,digest,collected_at,source_url,payload) VALUES (?,?,?,?,?)',
               (cid, digest, timestamp, url, raw))
    sid = db.execute('SELECT id FROM snapshots WHERE contract_id=? AND digest=?',
                     (cid, digest)).fetchone()[0]
    db.execute('INSERT INTO contracts VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET '
               'snapshot_id=excluded.snapshot_id,last_seen=excluded.last_seen',
               (cid, sid, timestamp))


def collect(db, start, end, max_pages=None, fetch=request_json):
    start_date = datetime.strptime(start, '%Y-%m-%d').date()
    end_date = datetime.strptime(end, '%Y-%m-%d').date()
    if start_date > end_date:
        raise ValueError('Data inicial posterior à final.')
    if max_pages is not None and max_pages < 1:
        raise ValueError('Limite de páginas deve ser positivo.')
    cursor = db.execute('INSERT INTO runs(started,start_date,end_date,status) '
                        'VALUES (?,?,?,?)', (now(), start, end, 'running'))
    run_id = cursor.lastrowid
    db.commit()
    page, count, seen = 1, 0, set()
    try:
        while True:
            url = BASE + '?' + urlencode(dict(dataInicial=start_date.strftime('%Y%m%d'),
                dataFinal=end_date.strftime('%Y%m%d'), pagina=page, tamanhoPagina=500))
            payload = fetch(url)
            if payload is None:
                if page != 1:
                    raise ValueError('Resposta vazia antes de concluir a paginação.')
                status = 'complete'
                break
            if not isinstance(payload, dict) or not isinstance(payload.get('data'), list):
                raise ValueError('Formato inesperado da API.')
            pages = payload.get('totalPaginas')
            if not isinstance(pages, int) or pages < 0:
                raise ValueError('Metadados de paginação ausentes.')
            if payload.get('numeroPagina') != page:
                raise ValueError('API retornou página diferente da solicitada.')
            records = payload['data']
            if not records and pages > 0:
                raise ValueError('Página inesperadamente vazia.')
            with db:
                for record in records:
                    cid = record.get('numeroControlePNCP')
                    if cid in seen:
                        raise ValueError('Registro repetido entre páginas; executar novamente.')
                    seen.add(cid)
                    save(db, record, url)
                count += len(records)
                db.execute('UPDATE runs SET records=?,pages=? WHERE id=?', (count, page, run_id))
            if page >= pages:
                total = payload.get('totalRegistros')
                if not isinstance(total, int) or count != total:
                    raise ValueError('Total recebido difere do total informado pela fonte.')
                status = 'complete'
                break
            if max_pages and page >= max_pages:
                status = 'partial'
                break
            page += 1
            time.sleep(0.25)
        with db:
            db.execute('UPDATE runs SET finished=?,status=? WHERE id=?', (now(), status, run_id))
        return {'run_id': run_id, 'status': status, 'records': count}
    except Exception as exc:
        with db:
            db.execute('UPDATE runs SET finished=?,status=?,error=? WHERE id=?',
                       (now(), 'failed', str(exc), run_id))
        raise


def current(db):
    rows = db.execute('SELECT s.contract_id,s.payload,s.source_url,s.digest,c.last_seen '
                      'FROM contracts c JOIN snapshots s ON s.id=c.snapshot_id ORDER BY c.id')
    return [dict(id=r[0], data=json.loads(r[1]), source=r[2], sha256=r[3], checked_at=r[4]) for r in rows]


def amount(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) and number >= 0 else None
    except (ValueError, TypeError):
        return None


def rules(records):
    findings = []
    for record in records:
        data = record['data']
        initial, global_value = amount(data.get('valorInicial')), amount(data.get('valorGlobal'))
        if initial and global_value is not None and global_value >= initial * 1.25:
            findings.append(dict(contract_id=record['id'], rule='variacao-valor-v1',
                title='Valor global ao menos 25% acima do inicial',
                classification='diferença nos campos da fonte; não comprova irregularidade',
                evidence={'valorInicial': initial, 'valorGlobal': global_value,
                          'percentual': round(100 * (global_value / initial - 1), 2)},
                explanation='O percentual é um filtro exploratório, não um limite legal. '
                            'Consultar aditivos, reajustes, escopo e justificativas.',
                source=record['source'], sha256=record['sha256']))
    return findings
