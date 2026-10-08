"""Operações administrativas locais; não existe escrita pública de revisões."""
import argparse
import gzip
import hashlib
import json
import os
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta, timezone

from observatorio.core import connect, current, now, rules
from observatorio.discovery import discover
from observatorio.sources import collect_cgu, collect_obras, enrich_obras, refresh_contracts
from observatorio.export import export_public
from observatorio.intelligence import price_comparison, duplication, finding_id


def backup(database, target):
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = target.with_suffix('.sqlite3')
    source = sqlite3.connect(database)
    copy = sqlite3.connect(stage)
    try:
        source.backup(copy)
        if copy.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Backup inválido')
    finally:
        source.close()
        copy.close()
    raw = stage.read_bytes()
    packed = gzip.compress(raw, mtime=0)
    if len(packed) > 80 * 1024 * 1024:
        raise ValueError('Backup excede 80 MB. Migrar para armazenamento dedicado; última cópia preservada.')
    temp = target.with_suffix('.tmp')
    temp.write_bytes(packed)
    os.replace(temp, target)
    target.with_suffix(target.suffix + '.sha256').write_text(hashlib.sha256(packed).hexdigest(), encoding='ascii')
    stage.unlink()


def restore(archive, database):
    archive, database = Path(archive), Path(database)
    packed = archive.read_bytes()
    expected = archive.with_suffix(archive.suffix + '.sha256').read_text().strip()
    if hashlib.sha256(packed).hexdigest() != expected:
        raise ValueError('Checksum do backup não confere')
    raw = gzip.decompress(packed)
    temporary = database.with_suffix('.restore.sqlite3')
    database.parent.mkdir(parents=True, exist_ok=True)
    temporary.write_bytes(raw)
    check = sqlite3.connect(temporary)
    try:
        if check.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Banco restaurado inválido')
    finally:
        check.close()
    # Never replace a potentially open WAL database.
    if any(Path(str(database) + suffix).exists() for suffix in ('-wal', '-shm')):
        raise ValueError('Feche as conexões e remova WAL por checkpoint antes de restaurar')
    os.replace(temporary, database)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', default='data/observatorio.sqlite3')
    commands = parser.add_subparsers(dest='command', required=True)
    enrich = commands.add_parser('enrich')
    enrich.add_argument('--contracts', type=int, default=40)
    enrich.add_argument('--work-pages', type=int, default=10)
    enrich.add_argument('--work-details', type=int, default=10)
    commands.add_parser('export')
    document = commands.add_parser('document')
    document.add_argument('url', help='URL oficial HTTPS de um PDF no PNCP')
    document.add_argument('--output', default='data/documents/latest.json')
    history = commands.add_parser('history')
    history.add_argument('--pages', type=int, default=5)
    history.add_argument('--earliest', default='2021-01-01')
    for name in ('backup', 'restore'):
        commands.add_parser(name).add_argument('file')
    review = commands.add_parser('review')
    review.add_argument('finding_id')
    review.add_argument('digest')
    review.add_argument('label', choices=['supported', 'false_positive', 'inconclusive'])
    review.add_argument('--note', required=True)
    compare = commands.add_parser('compare-prices')
    compare.add_argument('file', help='JSON com item e reference; campos equivalentes obrigatórios')
    args = parser.parse_args()
    if args.command == 'document':
        from observatorio.documents import analyze_url
        print(json.dumps(analyze_url(args.url, args.output), ensure_ascii=False, indent=2))
        return
    if args.command == 'backup':
        backup(args.db, args.file)
        return
    if args.command == 'restore':
        restore(args.file, args.db)
        return
    if args.command == 'compare-prices':
        payload = json.loads(Path(args.file).read_text(encoding='utf-8'))
        print(json.dumps(price_comparison(payload['item'], payload['reference']), ensure_ascii=False, indent=2))
        return
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    with connect(args.db) as db:
        if args.command == 'export':
            print(json.dumps(export_public(db), ensure_ascii=False, indent=2))
        elif args.command == 'history':
            from observatorio.history import backfill
            backfill(db, args.pages, args.earliest, today=datetime.now(timezone(timedelta(hours=-3))).date())
        elif args.command == 'review':
            records = current(db)
            findings = rules(records) + duplication(records) + discover(records)['hypotheses']
            if not any(finding_id(f) == args.finding_id and f['sha256'] == args.digest for f in findings):
                parser.error('A revisão precisa referenciar um alerta e uma versão atuais')
            db.execute('INSERT OR REPLACE INTO reviews VALUES (?,?,?,?,?)',
                       (args.finding_id, args.digest, args.label, args.note, now()))
        elif args.command == 'enrich':
            failures = []
            today = datetime.now(timezone(timedelta(hours=-3))).date()
            for name, task in [('revisitas', lambda: refresh_contracts(db, args.contracts)),
                               ('obras', lambda: collect_obras(db, args.work_pages)),
                               ('execucao_obras', lambda: enrich_obras(db, args.work_details)),
                               ('cgu', lambda: collect_cgu(db, str(today - timedelta(days=1))))]:
                try:
                    task()
                except Exception as exc:
                    failures.append(name)
                    print(f'{name}: {type(exc).__name__}; dados anteriores preservados.', flush=True)
            if failures:
                raise SystemExit(1)


if __name__ == '__main__':
    main()
