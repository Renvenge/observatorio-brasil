"""Varredura histórica nacional, por dia e página, retomada após falhas."""
from datetime import date, timedelta
from urllib.parse import urlencode
from .core import BASE, now, request_json, save
from .sources import cursor, set_cursor, status


def backfill(db, pages=5, earliest='2021-01-01', fetch=request_json, today=None):
    earliest = date.fromisoformat(earliest).isoformat()
    if type(pages) is not int or not 1 <= pages <= 100 or date.fromisoformat(earliest) > (today or date.today()):
        raise ValueError('Janela histórica inválida')
    db.executescript('''CREATE TABLE IF NOT EXISTS history_days (
      day TEXT PRIMARY KEY, next_page INTEGER, status TEXT, records INTEGER, checked_at TEXT, error TEXT);
      CREATE TABLE IF NOT EXISTS history_seen (day TEXT, id TEXT, PRIMARY KEY(day,id));''')
    day = cursor(db, 'history_day', str((today or date.today()) - timedelta(days=7)))
    with db:
        set_cursor(db, 'history_day', day)
    try:
        for _ in range(pages):
            if day < earliest:
                break
            state = db.execute('SELECT next_page FROM history_days WHERE day=?', (day,)).fetchone()
            page = state[0] if state else 1
            target = date.fromisoformat(day).strftime('%Y%m%d')
            url = BASE + '?' + urlencode(dict(dataInicial=target, dataFinal=target, pagina=page, tamanhoPagina=500))
            result = fetch(url)
            if result is None:
                if page != 1:
                    raise ValueError('Resposta vazia no meio de uma janela histórica')
                result = dict(data=[], numeroPagina=1, totalPaginas=0, totalRegistros=0)
            if not isinstance(result, dict) or not isinstance(result.get('data'), list) or type(result.get('numeroPagina')) is not int or result.get('numeroPagina') != page:
                raise ValueError('Resposta histórica inválida')
            total_pages, total = result.get('totalPaginas'), result.get('totalRegistros')
            if type(total_pages) is not int or type(total) is not int or total < 0 or total_pages < 0:
                raise ValueError('Totais históricos inválidos')
            if ((total == 0 and (total_pages not in (0, 1) or page != 1 or result['data']))
                    or (total > 0 and (total_pages < page or total_pages > total))
                    or len(result['data']) > 500):
                raise ValueError('Paginação histórica inválida')
            if not result['data'] and total:
                raise ValueError('Página histórica inesperadamente vazia')
            with db:
                for row in result['data']:
                    if not isinstance(row, dict):
                        raise ValueError('Registro histórico inválido')
                    cid = row.get('numeroControlePNCP')
                    if not isinstance(cid, str) or not cid.strip():
                        raise ValueError('Identificador histórico ausente')
                    if db.execute('SELECT 1 FROM history_seen WHERE day=? AND id=?', (day, cid)).fetchone():
                        raise ValueError('Paginação histórica mudou; janela precisa ser reconsultada')
                    # Old listings must not replace a more recently fetched detail record.
                    if not db.execute('SELECT 1 FROM contracts WHERE id=?', (cid,)).fetchone():
                        save(db, row, url)
                    db.execute('INSERT INTO history_seen VALUES (?,?)', (day, cid))
                received = db.execute('SELECT count(*) FROM history_seen WHERE day=?', (day,)).fetchone()[0]
                done = page >= total_pages
                if received > total or (not done and received >= total) or (done and received != total):
                    raise ValueError('Total histórico divergente')
                db.execute('INSERT OR REPLACE INTO history_days VALUES (?,?,?,?,?,NULL)',
                           (day, page + 1, 'complete' if done else 'partial', received, now()))
                if done:
                    db.execute('DELETE FROM history_seen WHERE day=?', (day,))
                    day = str(date.fromisoformat(day) - timedelta(days=1))
                set_cursor(db, 'history_day', day)
            print(f'Histórico PNCP: próxima janela {day}; página processada {page}.', flush=True)
        completed = db.execute("SELECT count(*) FROM history_days WHERE status='complete'").fetchone()[0]
        status(db, 'pncp_historico', 'partial', 'Coleta retroativa por data de publicação; não representa todos os gastos públicos.',
               next_date=day, completed_days=completed, earliest_requested=earliest, requested_range_complete=day < earliest)
    except Exception as exc:
        # Reset only this day's cursor after inconsistent paging; never delete contracts.
        if isinstance(exc, ValueError):
            with db:
                db.execute('DELETE FROM history_seen WHERE day=?', (day,))
                db.execute('INSERT OR REPLACE INTO history_days VALUES (?,1,?,0,?,?)', (day, 'failed', now(), type(exc).__name__))
        status(db, 'pncp_historico', 'failed', 'Janela histórica interrompida; contratos anteriores preservados.', next_date=day, error=type(exc).__name__)
        raise
