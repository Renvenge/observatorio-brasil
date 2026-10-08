"""Extração local de PDFs oficiais; texto não é exportado para o painel público."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

from .public_data import download, official_url

MAX_BYTES = 20_000_000
MAX_PAGES = 150
MAX_CHARACTERS = 500_000


def extract_pdf(path, source):
    from pypdf import PdfReader
    official_url(source)
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise ValueError('Documento excede 20 MB')
    raw = path.read_bytes()
    if not raw.startswith(b'%PDF-'):
        raise ValueError('Arquivo recebido não é PDF')
    reader = PdfReader(path)
    if reader.is_encrypted:
        raise ValueError('PDF protegido; requer conferência manual')
    total = len(reader.pages)
    if not total:
        raise ValueError('PDF sem páginas')
    pages, pending, characters = [], [], 0
    truncated = total > MAX_PAGES
    for index in range(min(total, MAX_PAGES)):
        try:
            # Limit decompressed page streams before text processing as well as file size.
            contents = reader.pages[index].get_contents()
            if contents and len(contents.get_data()) > MAX_BYTES:
                raise ValueError('Conteúdo da página excede limite')
            text = reader.pages[index].extract_text() or ''
            text = text.strip()
        except Exception:
            pending.append(dict(page=index + 1, reason='Falha de leitura; conferir documento original.'))
            continue
        if not text:
            pending.append(dict(page=index + 1, reason='Sem texto extraível; verificar imagem ou necessidade de OCR.'))
        remaining = MAX_CHARACTERS - characters
        if len(text) > remaining:
            text = text[:remaining]
            truncated = True
        pages.append(dict(page=index + 1, text=text))
        characters += len(text)
        if characters >= MAX_CHARACTERS:
            truncated = truncated or index + 1 < total
            break
    return dict(source=source, sha256=hashlib.sha256(raw).hexdigest(), total_pages=total,
                status='partial' if pending or truncated else 'extracted',
                pages=pages, pending_pages=pending, truncated=truncated,
                note='Extração textual para revisão. Não confirma valores, pagamentos ou irregularidades.')


def analyze_url(url, output):
    official_url(url)
    if urlsplit(url).hostname != 'pncp.gov.br':
        raise ValueError('Esta etapa aceita somente anexos oficiais do PNCP')
    path, digest = download(url, limit=MAX_BYTES, seconds=90)
    # A malformed document cannot hold up the collector indefinitely.
    result = subprocess.run([sys.executable, '-m', 'observatorio.documents', str(path), url],
                            capture_output=True, timeout=60, check=False)
    if result.returncode:
        raise ValueError('PDF não pôde ser lido; conferir documento original')
    report = json.loads(result.stdout)
    if report.get('sha256') != digest:
        raise ValueError('A cópia do documento mudou durante a leitura')
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + '.tmp')
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(target)
    return {key: report[key] for key in ('source', 'sha256', 'total_pages', 'status', 'truncated')}


if __name__ == '__main__':
    report = extract_pdf(sys.argv[1], sys.argv[2])
    sys.stdout.buffer.write(json.dumps(report, ensure_ascii=False).encode('utf-8'))
