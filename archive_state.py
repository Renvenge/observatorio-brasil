"""Checkpoint durável no ramo data, separado do código; sem force push."""
import argparse
import json
import os
import subprocess
from pathlib import Path

from manage import backup, restore

ROOT = Path(__file__).resolve().parent


def git(*args, env=None, data=None, check=True):
    result = subprocess.run(['git', *args], cwd=ROOT, input=data, capture_output=True, env=env, check=check)
    return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['restore', 'save'])
    args = parser.parse_args()
    existing = subprocess.run(['git', 'ls-remote', '--exit-code', 'origin', 'refs/heads/data'], cwd=ROOT,
                              capture_output=True)
    if existing.returncode not in (0, 2):
        raise RuntimeError('Não foi possível verificar o checkpoint remoto; não será criado histórico substituto.')
    parent = None
    if existing.returncode == 0:
        git('fetch', '--no-tags', 'origin', 'data')
        parent = git('rev-parse', 'FETCH_HEAD').decode()
    checkpoint = ROOT / 'data' / 'checkpoint.sqlite3.gz'
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    if args.command == 'restore':
        if not parent:
            print('Primeiro checkpoint: usando banco local/cache, se disponível.')
            return
        # Binary output must not be stripped: gzip data may end in whitespace bytes.
        for filename in ('state.sqlite3.gz', 'state.sqlite3.gz.sha256'):
            dest = checkpoint if filename.endswith('.gz') else checkpoint.with_suffix('.gz.sha256')
            content = subprocess.run(['git', 'show', f'{parent}:{filename}'], cwd=ROOT, capture_output=True, check=True).stdout
            dest.write_bytes(content)
        restore(checkpoint, ROOT / 'data' / 'observatorio.sqlite3')
        print('Checkpoint remoto restaurado e verificado.')
        return
    backup(ROOT / 'data' / 'observatorio.sqlite3', checkpoint)
    env = dict(os.environ, GIT_INDEX_FILE=str(ROOT / 'data' / 'archive.index'))
    # New index tracks an exact checkpoint, while prior commits preserve the archive history.
    git('read-tree', '--empty', env=env)
    files = {'state.sqlite3.gz': checkpoint,
             'state.sqlite3.gz.sha256': checkpoint.with_suffix('.gz.sha256')}
    for name in ('current.json', 'summary.json', 'contratos.csv', 'analise.json'):
        file = ROOT / 'reports' / name
        if file.exists():
            files[name] = file
    for name, file in files.items():
        if file.stat().st_size > 90 * 1024 * 1024:
            raise ValueError('Arquivo acima do limite operacional; migrar armazenamento antes de publicar.')
        digest = git('hash-object', '-w', str(file)).decode()
        git('update-index', '--add', '--cacheinfo', f'100644,{digest},{name}', env=env)
    tree = git('write-tree', env=env).decode()
    env.update(GIT_AUTHOR_NAME='Observatório Brasil', GIT_AUTHOR_EMAIL='observatorio@users.noreply.github.com',
               GIT_COMMITTER_NAME='Observatório Brasil', GIT_COMMITTER_EMAIL='observatorio@users.noreply.github.com')
    args_commit = ['commit-tree', tree] + (['-p', parent] if parent else [])
    commit = git(*args_commit, env=env, data=b'Checkpoint de dados publicos e relatorios\n').decode()
    git('push', 'origin', f'{commit}:refs/heads/data')
    print(json.dumps({'checkpoint_commit': commit, 'branch': 'data', 'files': list(files)}))


if __name__ == '__main__':
    main()
