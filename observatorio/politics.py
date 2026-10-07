"""Correspondências públicas a conferir; CPF parcial nunca prova identidade."""
import base64
import csv
import hashlib
import io
import json
import re
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from urllib.parse import unquote
from xml.etree import ElementTree

from .core import current, now
from .public_data import download, normalize, read_url
from .sources import cursor, set_cursor, status

SHARE = 'YggdBLfdninEJX9'
DAV = 'https://arquivos.receitafederal.gov.br/public.php/webdav/'
QSA_SOURCE = 'https://arquivos.receitafederal.gov.br/index.php/s/' + SHARE


def masked_cpf(value):
    """Keep only the six middle positions; never fill or reconstruct digits."""
    value = re.sub(r'[.\-\s]', '', str(value or ''))
    if len(value) != 11 or not re.fullmatch(r'[0-9*]{11}', value):
        return None
    if value.isdigit() and len(set(value)) == 1:
        return None
    middle = value[3:9]
    return '***' + middle + '**' if middle.isdigit() else None


def possible_match(name_a, cpf_a, name_b, cpf_b):
    left, right = masked_cpf(cpf_a), masked_cpf(cpf_b)
    return bool(left and right and left == right and normalize(name_a)
                and normalize(name_a) == normalize(name_b))


def schema(db):
    db.executescript('''
      CREATE TABLE IF NOT EXISTS candidates (
        year INTEGER, id TEXT, name TEXT, name_key TEXT, cpf_mask TEXT,
        payload TEXT, source TEXT, sha256 TEXT, checked_at TEXT,
        PRIMARY KEY(year,id));
      CREATE INDEX IF NOT EXISTS candidate_match ON candidates(name_key,cpf_mask);
      CREATE TABLE IF NOT EXISTS qsa_matches (
        month TEXT, part TEXT, company TEXT, candidate_year INTEGER, candidate_id TEXT,
        payload TEXT, source TEXT, sha256 TEXT, checked_at TEXT,
        PRIMARY KEY(month,part,company,candidate_year,candidate_id));
      CREATE TABLE IF NOT EXISTS qsa_parts (
        month TEXT, part TEXT, checked_at TEXT, rows_scanned INTEGER,
        PRIMARY KEY(month,part));
    ''')


def import_tse(db, year, path, source, digest):
    schema(db)
    total, kept, identifiable = 0, 0, 0
    with zipfile.ZipFile(path) as archive:
        names = [n for n in archive.namelist() if n.lower().endswith(f'consulta_cand_{year}_brasil.csv')]
        if len(names) != 1:
            raise ValueError('Arquivo nacional de candidatos ausente ou ambíguo')
        with archive.open(names[0]) as raw, io.TextIOWrapper(raw, encoding='latin-1', newline='') as file, db:
            reader = csv.DictReader(file, delimiter=';')
            required = {'SQ_CANDIDATO', 'NM_CANDIDATO', 'NR_CPF_CANDIDATO', 'DS_SIT_TOT_TURNO', 'ANO_ELEICAO'}
            if not required.issubset(reader.fieldnames or []):
                raise ValueError('Layout TSE incompatível')
            db.execute('DELETE FROM candidates WHERE year=?', (year,))
            for row in reader:
                total += 1
                if str(row['ANO_ELEICAO']) != str(year):
                    raise ValueError('Ano eleitoral incompatível')
                elected = normalize(row['DS_SIT_TOT_TURNO']).startswith('ELEITO')
                # Historical elected candidatures, plus all current-year candidates.
                if year < datetime.now(timezone.utc).year and not elected:
                    continue
                mask = masked_cpf(row['NR_CPF_CANDIDATO'])
                cid = row.get('CD_ELEICAO', '') + ':' + row['SQ_CANDIDATO']
                payload = dict(year=year, id=cid, name=row['NM_CANDIDATO'],
                    ballot_name=row.get('NM_URNA_CANDIDATO'), party=row.get('SG_PARTIDO'),
                    uf=row.get('SG_UF'), office=row.get('DS_CARGO'), election=row.get('DS_ELEICAO'),
                    election_status=row['DS_SIT_TOT_TURNO'], candidature_status=row.get('DS_SITUACAO_CANDIDATURA'),
                    elected_in_that_election=elected, cpf_mask=mask)
                db.execute('INSERT OR REPLACE INTO candidates VALUES (?,?,?,?,?,?,?,?,?)',
                    (year, cid, row['NM_CANDIDATO'], normalize(row['NM_CANDIDATO']), mask,
                     json.dumps(payload, ensure_ascii=False), source, digest, now()))
                kept += 1
                identifiable += bool(mask)
    status(db, f'tse_{year}', 'partial', 'Candidaturas não comprovam mandato atual; CPF ausente não é reconstruído.',
           rows_read=total, retained=kept, usable_masks=identifiable, source_url=source)
    return dict(rows=total, retained=kept, usable_masks=identifiable)


def collect_tse(db, year):
    schema(db)
    marker = 'tse_checked_' + str(year)
    today = now()[:10]
    if cursor(db, marker, '') == today:
        return
    catalog = json.loads(read_url(f'https://dadosabertos.tse.jus.br/api/3/action/package_show?id=candidatos-{year}'))
    candidates = [r for r in catalog.get('result', {}).get('resources', [])
                  if r.get('name') == 'Candidatos' and r.get('url', '').endswith('.zip')]
    if len(candidates) != 1:
        raise ValueError('Catálogo TSE sem arquivo inequívoco de candidatos')
    url = candidates[0]['url']
    path, digest = download(url, version=today)
    try:
        result = import_tse(db, year, path, url, digest)
        with db:
            set_cursor(db, marker, today)
        return result
    finally:
        path.unlink(missing_ok=True)


def dav_list(path=''):
    # This is the official anonymous public-share token, not a user credential.
    auth = 'Basic ' + base64.b64encode((SHARE + ':').encode()).decode()
    raw = read_url(DAV + path, headers={'Authorization': auth, 'Depth': '1'}, method='PROPFIND')
    root = ElementTree.fromstring(raw)
    return [(unquote(r.findtext('{DAV:}href') or '').rstrip('/').split('/')[-1],
             r.findtext('.//{DAV:}getetag') or '') for r in root.findall('{DAV:}response')]


def import_qsa(db, month, part, path, source, digest):
    schema(db)
    companies = set()
    for record in current(db):
        data = record['data']
        cnpj = re.sub(r'[^A-Z0-9]', '', str(data.get('niFornecedor') or '').upper())
        if data.get('tipoPessoa') == 'PJ' and re.fullmatch(r'[A-Z0-9]{12}[0-9]{2}', cnpj):
            companies.add(cnpj[:8])
    candidates = defaultdict(list)
    for year, cid, name, mask in db.execute('SELECT year,id,name_key,cpf_mask FROM candidates WHERE cpf_mask IS NOT NULL'):
        candidates[(name, mask)].append((year, cid))
    scanned, matches = 0, []
    with zipfile.ZipFile(path) as archive:
        members = [n for n in archive.namelist() if not n.endswith('/')]
        if len(members) != 1 or archive.getinfo(members[0]).file_size > 3_000_000_000:
            raise ValueError('Pacote QSA inesperado')
        with archive.open(members[0]) as raw, io.TextIOWrapper(raw, encoding='latin-1', newline='') as file:
            for row in csv.reader(file, delimiter=';'):
                scanned += 1
                if len(row) != 11:
                    raise ValueError('Layout QSA incompatível')
                if row[0] not in companies or row[1] != '2':
                    continue
                mask = masked_cpf(row[3])
                for year, cid in candidates.get((normalize(row[2]), mask), []):
                    payload = dict(company_base=row[0], partner_name=row[2], cpf_mask=mask,
                        qualification_code=row[4], entry_date=row[5], reference_month=month,
                        classification='correspondencia_a_conferir',
                        evidence='Nome completo normalizado e seis posições visíveis do CPF coincidem.',
                        limitation='Não confirma identidade, vínculo na data do contrato, conflito de interesses ou corrupção.')
                    matches.append((month, part, row[0], year, cid, json.dumps(payload, ensure_ascii=False), source, digest, now()))
    if not scanned:
        raise ValueError('Arquivo QSA vazio; correspondências anteriores preservadas')
    with db:
        db.execute('DELETE FROM qsa_matches WHERE month=? AND part=?', (month, part))
        db.executemany('INSERT OR REPLACE INTO qsa_matches VALUES (?,?,?,?,?,?,?,?,?)', matches)
        db.execute('INSERT OR REPLACE INTO qsa_parts VALUES (?,?,?,?)', (month, part, now(), scanned))
    return dict(scanned=scanned, matches=len(matches), suppliers_in_scope=len(companies))


def collect_qsa(db):
    schema(db)
    months = sorted(n for n, _ in dav_list() if re.fullmatch(r'20\d{2}-\d{2}', n))
    if not months:
        raise ValueError('Catálogo Receita sem mês disponível')
    month = months[-1]
    parts = sorted((n, etag) for n, etag in dav_list(month + '/') if re.fullmatch(r'Socios\d+\.zip', n))
    if len(parts) != 10:
        raise ValueError('Catálogo QSA não contém as dez partes esperadas')
    attempts = {r[0]: r[1] for r in db.execute('SELECT part,checked_at FROM qsa_parts WHERE month=?', (month,))}
    part, etag = min(parts, key=lambda p: (attempts.get(p[0], ''), p[0]))
    auth = 'Basic ' + base64.b64encode((SHARE + ':').encode()).decode()
    path, digest = download(DAV + month + '/' + part, headers={'Authorization': auth}, version=etag)
    try:
        result = import_qsa(db, month, part, path, QSA_SOURCE, digest)
    finally:
        path.unlink(missing_ok=True)
    count = db.execute('SELECT count(*) FROM qsa_parts WHERE month=?', (month,)).fetchone()[0]
    status(db, 'receita_qsa', 'partial', 'Uma parte por ciclo; correspondências exigem investigação e não confirmam identidade.',
           reference_month=month, parts_scanned=count, total_parts=len(parts), last_part=part, **result)
    return result


def political_links(db):
    schema(db)
    latest = db.execute('SELECT MAX(month) FROM qsa_parts').fetchone()[0]
    result = defaultdict(list)
    for company, payload, source, digest, checked, candidate, tse_source, tse_digest, tse_checked, part in db.execute(
            'SELECT q.company,q.payload,q.source,q.sha256,q.checked_at,c.payload,c.source,c.sha256,c.checked_at,q.part '
            'FROM qsa_matches q JOIN candidates c ON c.year=q.candidate_year AND c.id=q.candidate_id WHERE q.month=?', (latest,)):
        match, candidacy = json.loads(payload), json.loads(candidate)
        if not possible_match(match['partner_name'], match['cpf_mask'], candidacy['name'], candidacy['cpf_mask']):
            continue
        result[company].append(dict(**match, candidate=candidacy,
            source=source, sha256=digest, checked_at=checked, candidate_source=tse_source,
            candidate_sha256=tse_digest, candidate_checked_at=tse_checked, source_file=part))
    return dict(result)


def collect_links(db, parts=1):
    if not 1 <= parts <= 10:
        raise ValueError('Consultar de uma a dez partes por execução')
    failures = []
    for year in (2022, 2024, 2026):
        try:
            result = collect_tse(db, year)
            print(f'TSE {year}: {result or "já atualizado hoje"}', flush=True)
        except Exception as exc:
            failures.append(f'tse_{year}')
            status(db, f'tse_{year}', 'failed', 'Atualização interrompida; dados anteriores preservados.', error=type(exc).__name__)
    for _ in range(parts):
        try:
            print('QSA Receita: ' + json.dumps(collect_qsa(db)), flush=True)
        except Exception as exc:
            failures.append('receita_qsa')
            status(db, 'receita_qsa', 'failed', 'Atualização interrompida; última consulta preservada.', error=type(exc).__name__)
            break
    if failures:
        raise RuntimeError('Fontes pendentes: ' + ', '.join(failures))


def link_coverage(db):
    schema(db)
    latest = db.execute('SELECT MAX(month) FROM qsa_parts').fetchone()[0]
    parts = [dict(file=p, checked_at=t, rows_scanned=n) for p,t,n in
             db.execute('SELECT part,checked_at,rows_scanned FROM qsa_parts WHERE month=? ORDER BY part', (latest,))]
    years = [dict(year=y, candidatures=n, usable_masks=m) for y,n,m in db.execute(
        'SELECT year,count(*),sum(cpf_mask IS NOT NULL) FROM candidates GROUP BY year ORDER BY year')]
    return dict(reference_month=latest, parts=parts, expected_parts=10, elections=years,
                method='Nome completo normalizado e seis posições visíveis coincidentes. Nenhum dígito oculto é reconstruído.',
                limitation='Correspondência a conferir, não identidade confirmada. Candidatura não comprova mandato atual. QSA atual não prova vínculo na data do contrato.')
