import argparse
import csv
import json
from pathlib import Path

from .core import collect, connect, current, now, rules


def safe_cell(value):
    text = '' if value is None else str(value)
    return "'" + text if text.lstrip().startswith(('=', '+', '-', '@')) else text


def main():
    parser = argparse.ArgumentParser(description='Observatório Brasil — contratos públicos e evidências')
    parser.add_argument('--db', default='data/observatorio.sqlite3')
    commands = parser.add_subparsers(dest='command', required=True)
    gather = commands.add_parser('collect', help='Consultar contratos por data de publicação')
    gather.add_argument('--start', required=True, help='AAAA-MM-DD')
    gather.add_argument('--end', required=True, help='AAAA-MM-DD')
    gather.add_argument('--max-pages', type=int)
    report = commands.add_parser('report', help='Exportar contratos, diferenças e hipóteses')
    report.add_argument('--out', default='reports')
    report.add_argument('--ai', action='store_true')
    commands.add_parser('status')
    args = parser.parse_args()
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    with connect(args.db) as db:
        if args.command == 'collect':
            result = collect(db, args.start, args.end, args.max_pages)
            print(json.dumps(result, ensure_ascii=False))
            return
        runs = [dict(zip(('id', 'started', 'finished', 'start', 'end', 'status', 'records', 'pages', 'error'), row))
                for row in db.execute('SELECT * FROM runs ORDER BY id DESC LIMIT 30')]
        records = current(db)
        if args.command == 'status':
            print(json.dumps(dict(contracts=len(records), runs=runs), ensure_ascii=False, indent=2))
            return
        discovery = {'status': 'não executada; usar --ai'}
        if args.ai:
            from .discovery import discover
            discovery = discover(records)
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        result = dict(generated_at=now(), scope='Contratos publicados no PNCP nos períodos consultados.',
            coverage='Cobertura parcial do gasto público brasileiro. Valor contratado não é pagamento. '
                     'Consulta por publicação não garante detectar atualizações de contratos antigos.',
            runs=runs, contracts=len(records), findings=rules(records), discovery=discovery)
        (out / 'analise.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        # Full source snapshots remain in SQLite; public export avoids personal supplier identifiers.
        with (out / 'contratos.csv').open('w', newline='', encoding='utf-8-sig') as stream:
            writer = csv.writer(stream)
            writer.writerow(['id', 'orgao', 'uf', 'municipio', 'objeto', 'valor_inicial', 'valor_global', 'fonte', 'sha256', 'verificado_em'])
            for record in records:
                d = record['data']
                writer.writerow([safe_cell(v) for v in [record['id'], (d.get('orgaoEntidade') or {}).get('razaoSocial'),
                    (d.get('unidadeOrgao') or {}).get('ufSigla'), (d.get('unidadeOrgao') or {}).get('municipioNome'),
                    d.get('objetoContrato'), d.get('valorInicial'), d.get('valorGlobal'),
                    record['source'], record['sha256'], record['checked_at']]])
        print(str(out.resolve()))


if __name__ == '__main__':
    main()
