"""Monitor local. Executar explicitamente; não instala tarefas no sistema."""
import argparse
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--interval-minutes', type=int, default=360)
    parser.add_argument('--lookback-days', type=int, default=7)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    if args.interval_minutes < 60 or not 1 <= args.lookback_days <= 30:
        parser.error('Intervalo mínimo de 60 minutos e janela entre 1 e 30 dias.')
    root = Path(__file__).resolve().parent
    while True:
        today = datetime.now(timezone(timedelta(hours=-3))).date()
        first = today - timedelta(days=args.lookback_days - 1)
        result = subprocess.run([sys.executable, '-m', 'observatorio', 'collect',
                                 '--start', str(first), '--end', str(today)], cwd=root)
        report = subprocess.run([sys.executable, '-m', 'observatorio', 'report', '--ai'], cwd=root)
        if result.returncode or report.returncode:
            print('Ciclo com falha; conferir status e cobertura no relatório.', flush=True)
        if args.once:
            raise SystemExit(result.returncode or report.returncode)
        try:
            time.sleep(args.interval_minutes * 60)
        except KeyboardInterrupt:
            return


if __name__ == '__main__':
    main()
