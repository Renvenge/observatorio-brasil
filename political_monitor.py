"""Atualização independente do cruzamento TSE/Receita/fornecedores PNCP."""
import argparse
from pathlib import Path
from observatorio.core import connect
from observatorio.politics import collect_links


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', default='data/observatorio.sqlite3')
    parser.add_argument('--parts', type=int, default=1)
    args = parser.parse_args()
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    db = connect(args.db)
    try:
        collect_links(db, args.parts)
    finally:
        db.close()
