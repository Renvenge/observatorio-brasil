"""Conectores oficiais e filas retomáveis. Nenhum vínculo é inferido por nome."""
import hashlib
import json
import os
import re
import time
from datetime import date, timedelta
from urllib.parse import urlencode

from .core import current, now, request_json, save

PNCP = 'https://pncp.gov.br/api/pncp/v1/orgaos/'
OBRAS = 'https://api-publica.obrasgov.gestao.gov.br/obras/'
CGU = 'https://api.portaldatransparencia.gov.br/api-de-dados/'


def status(db, source, state, message, **metadata):
    with db:
        db.execute('INSERT OR REPLACE INTO source_status VALUES (?,?,?,?,?)',
                   (source, now(), state, message, json.dumps(metadata, ensure_ascii=False)))


def cursor(db, name, default='1'):
    row = db.execute('SELECT value FROM cursors WHERE name=?', (name,)).fetchone()
    return row[0] if row else default


def set_cursor(db, name, value):
    db.execute('INSERT OR REPLACE INTO cursors VALUES (?,?)', (name, str(value)))


def resource(db, source, rid, payload, url):
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False)
    digest = hashlib.sha256(raw.encode()).hexdigest()
    db.execute('INSERT OR IGNORE INTO resources VALUES (?,?,?,?,?,?)',
               (source, str(rid), digest, raw, url, now()))
    db.execute('INSERT OR REPLACE INTO resource_latest VALUES (?,?,?)', (source, str(rid), digest))


def resources(db, source):
    return [dict(id=r[0], data=json.loads(r[1]), source=r[2], sha256=r[3], checked_at=r[4])
            for r in db.execute('SELECT r.resource_id,r.payload,r.url,r.digest,r.collected_at '
                'FROM resource_latest l JOIN resources r USING(source,resource_id,digest) '
                'WHERE r.source=? ORDER BY r.resource_id', (source,))]


def contract_url(cid):
    match = re.fullmatch(r'(\d{14})-2-(\d+)/(\d{4})', cid)
    if not match:
        raise ValueError('Identificador PNCP inválido')
    cnpj, seq, year = match.groups()
    return f'{PNCP}{cnpj}/contratos/{year}/{int(seq)}'


def refresh_contracts(db, limit=40, fetch=request_json):
    if not 1 <= limit <= 1000:
        raise ValueError('Limite deve estar entre 1 e 1000')
    rows = db.execute('SELECT c.id FROM contracts c LEFT JOIN refresh_queue q ON c.id=q.contract_id '
                      "ORDER BY COALESCE(q.attempted_at,''),c.id LIMIT ?", (limit,)).fetchall()
    errors, success = [], 0
    for (cid,) in rows:
        stamp = now()
        try:
            url = contract_url(cid)
            data = fetch(url)
            if not isinstance(data, dict) or data.get('numeroControlePNCP') != cid:
                raise ValueError('Resposta não corresponde ao contrato solicitado')
            with db:
                save(db, data, url)
            for name in ('termos', 'arquivos', 'historico'):
                try:
                    linked = fetch(url + '/' + name)
                    if linked is not None and not isinstance(linked, (dict, list)):
                        raise ValueError('Formato de recurso inesperado')
                    with db:
                        resource(db, 'pncp_' + name, cid, linked, url + '/' + name)
                except Exception as exc:
                    errors.append({'id': cid, 'resource': name, 'error': type(exc).__name__})
            with db:
                db.execute('INSERT INTO refresh_queue VALUES (?,?,?,NULL) '
                           'ON CONFLICT(contract_id) DO UPDATE SET attempted_at=excluded.attempted_at,'
                           'succeeded_at=excluded.succeeded_at,error=NULL', (cid, stamp, stamp))
            success += 1
        except Exception as exc:
            errors.append({'id': cid, 'resource': 'contrato', 'error': type(exc).__name__})
            with db:
                db.execute('INSERT INTO refresh_queue VALUES (?,?,NULL,?) '
                           'ON CONFLICT(contract_id) DO UPDATE SET attempted_at=excluded.attempted_at,error=excluded.error',
                           (cid, stamp, type(exc).__name__))
        print(f'Revisita PNCP: {success}/{len(rows)} atualizados; {len(errors)} falhas.', flush=True)
    total = db.execute('SELECT count(*) FROM contracts').fetchone()[0]
    revisited = db.execute('SELECT count(*) FROM refresh_queue WHERE succeeded_at IS NOT NULL').fetchone()[0]
    status(db, 'pncp_revisitas', 'partial' if errors or revisited < total else 'ok',
           'Fila rotativa de contratos já conhecidos; falhas não apagam registros anteriores.',
           attempted=len(rows), success=success, ever_revisited=revisited, total=total, errors=errors[:20])
    return success


def collect_obras(db, pages=10, fetch=request_json):
    page = int(cursor(db, 'obras_page'))
    received, total, completed = 0, None, False
    try:
        for _ in range(pages):
            url = OBRAS + 'projeto-investimento?' + urlencode({'pagina': page, 'tamanho_da_pagina': 200})
            result = fetch(url)
            if not isinstance(result, dict) or not isinstance(result.get('data'), list) or result.get('page_number') != page:
                raise ValueError('Formato/paginação Obrasgov inválido')
            total = result['total_items']
            if not isinstance(total, int) or not isinstance(result.get('total_pages'), int):
                raise ValueError('Totais da fonte inválidos')
            if not result['data'] and total:
                raise ValueError('Página vazia antes do fim')
            with db:
                for row in result['data']:
                    rid = row.get('id_projeto_investimento')
                    if not rid:
                        raise ValueError('Obra sem identificador')
                    resource(db, 'obras', rid, row, url)
                received += len(result['data'])
                page += 1
                completed = page > result['total_pages']
                set_cursor(db, 'obras_page', 1 if completed else page)
            print(f'Obrasgov: {received} recebidos neste ciclo; próxima página {page}.', flush=True)
            if completed:
                break
            time.sleep(.3)
        count = db.execute("SELECT count(*) FROM resource_latest WHERE source='obras'").fetchone()[0]
        status(db, 'obras', 'partial', 'Varredura incremental do cadastro; paginação não é fotografia transacional.',
               collected=count, total_reported=total, next_page=1 if completed else page, scan_pass_finished=completed)
    except Exception as exc:
        status(db, 'obras', 'failed', 'Coleta interrompida; dados anteriores preservados.', error=type(exc).__name__, next_page=page)
        raise


def enrich_obras(db, limit=10, fetch=request_json):
    work = resources(db, 'obras')
    if not work:
        return
    start = int(cursor(db, 'obras_enrich', '0')) % len(work)
    errors = 0
    for offset in range(min(limit, len(work))):
        row = work[(start + offset) % len(work)]
        for endpoint in ('empenho', 'execucao-fisica', 'contrato', 'historico-situacao-cancelada-paralisada'):
            data = []
            try:
                page = 1
                while True:
                    url = OBRAS + endpoint + '?' + urlencode(dict(id_projeto_investimento=row['id'], pagina=page, tamanho_da_pagina=200))
                    result = fetch(url)
                    if not isinstance(result, dict) or not isinstance(result.get('data'), list) or result.get('page_number') != page:
                        raise ValueError('Resposta de execução da obra inválida')
                    data.extend(result['data'])
                    if page >= result['total_pages']:
                        break
                    if page >= 50:
                        raise ValueError('Limite de paginação; recurso não será substituído por amostra')
                    page += 1
                with db:
                    resource(db, 'obras_' + endpoint, row['id'], data, OBRAS + endpoint + '?' + urlencode(dict(id_projeto_investimento=row['id'])))
            except Exception:
                errors += 1
        with db:
            set_cursor(db, 'obras_enrich', (start + offset + 1) % len(work))
        print(f'Execução de obras: {offset + 1}/{min(limit, len(work))}; {errors} falhas.', flush=True)
    status(db, 'obras_execucao', 'partial', 'Fila de enriquecimento por identificador oficial. Empenho, liquidado e pago são campos distintos.',
           attempted=min(limit, len(work)), errors=errors,
           with_financial_data=db.execute("SELECT count(*) FROM resource_latest WHERE source='obras_empenho'").fetchone()[0])


def collect_cgu(db, day, pages=10, fetch=request_json):
    key = os.environ.get('TRANSPARENCIA_API_KEY')
    if not key:
        status(db, 'cgu', 'credentials_required', 'Aguardando TRANSPARENCIA_API_KEY no ambiente/GitHub Secrets. Nenhum pagamento foi inferido.')
        return
    pending = cursor(db, 'cgu_day', day)
    if pending > day:
        status(db, 'cgu', 'partial', 'Fila consultada até a data anterior; sem garantia de atualizações retroativas.', next_date=pending)
        return
    day = pending
    target = date.fromisoformat(day)
    expenses_complete = True
    all_queries = [('despesas/documentos', {'dataEmissao': target.strftime('%d/%m/%Y'), 'fase': phase}) for phase in (1, 2, 3)]
    all_queries.append(('emendas', {'ano': target.year}))
    try:
        for endpoint, params in all_queries:
            name = 'cgu_' + endpoint.replace('/', '_') + '_' + str(params.get('fase', 'emendas'))
            ck = name + ':' + (day if 'fase' in params else str(target.year))
            page = int(cursor(db, ck))
            done = False
            for _ in range(pages):
                url = CGU + endpoint + '?' + urlencode({**params, 'pagina': page})
                rows = fetch(url, headers={'chave-api-dados': key})
                if not isinstance(rows, list):
                    raise ValueError('Resposta CGU inválida')
                if not rows:
                    done = True
                    break
                with db:
                    for row in rows:
                        # Record pages exactly, without guessing cross-source joins or field meanings.
                        rid = hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()
                        resource(db, name, rid, row, url)
                    page += 1
                    set_cursor(db, ck, page)
                time.sleep(.6)
            status(db, name, 'ok' if done else 'partial', 'Documentos oficiais preservados; sem vínculo automático a contratos PNCP.',
                   date=day, phase=params.get('fase'), next_page=page)
            if 'fase' in params:
                expenses_complete = expenses_complete and done
        if expenses_complete:
            with db:
                set_cursor(db, 'cgu_day', str(target + timedelta(days=1)))
        status(db, 'cgu', 'partial', 'Integração ativa; cobertura limitada às datas e páginas consultadas.')
    except Exception as exc:
        status(db, 'cgu', 'failed', 'Erro na consulta; chave não é registrada em logs.', error=type(exc).__name__)
        raise
