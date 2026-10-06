"""Indicadores verificáveis, revisão humana e comparações explicitamente equivalentes."""
import hashlib
import json
from collections import defaultdict
from decimal import Decimal, InvalidOperation


def finding_id(finding):
    identity = [finding.get('contract_id'), finding.get('rule', finding.get('pattern_id')), finding.get('sha256')]
    return hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:24]


def duplication(records):
    groups = defaultdict(list)
    for record in records:
        d = record['data']
        keys = [(d.get('orgaoEntidade') or {}).get('cnpj'), d.get('niFornecedor'),
                d.get('numeroControlePncpCompra'), d.get('objetoContrato'), d.get('dataAssinatura'), d.get('valorGlobal')]
        if d.get('receita') is False and all(k is not None and k != '' for k in keys):
            groups[tuple(keys)].append(record)
    results = []
    for group in groups.values():
        if len(group) < 2:
            continue
        for record in group:
            results.append(dict(contract_id=record['id'], rule='campos-coincidentes-v1',
                title='Contratos distintos com campos coincidentes',
                evidence={'related_ids': [r['id'] for r in group],
                          'matching_fields': ['órgão', 'fornecedor', 'compra PNCP', 'objeto', 'assinatura', 'valor global']},
                classification='hipótese de duplicidade; não demonstra pagamento duplicado',
                explanation='Pode haver contratos separados legítimos, lotes ou repetição de cadastro. Conferir documentos.',
                source=record['source'], sha256=record['sha256']))
    return results


def price_comparison(item, reference):
    required = ('item_code', 'specification', 'unit', 'uf', 'month', 'tax_regime', 'price_basis')
    if any(not item.get(k) or not reference.get(k) or item[k] != reference[k] for k in required):
        return {'status': 'incomparable', 'reason': 'Especificação, unidade, local, mês, encargos ou base de preço diferentes/ausentes.'}
    if not item.get('source') or not reference.get('source'):
        return {'status': 'incomparable', 'reason': 'Fontes dos dois valores são obrigatórias.'}
    try:
        actual, baseline = Decimal(str(item['unit_price'])), Decimal(str(reference['unit_price']))
        if not actual.is_finite() or not baseline.is_finite() or baseline <= 0 or actual < 0:
            raise ValueError()
    except (InvalidOperation, ValueError, KeyError):
        return {'status': 'incomparable', 'reason': 'Valores unitários inválidos.'}
    return dict(status='comparable', difference_percent=float((actual / baseline - 1) * 100),
                actual=str(actual), reference=str(baseline), sources=[item['source'], reference['source']],
                meaning='Diferença de preço unitário em condições declaradas equivalentes; não prova sobrepreço ilegal.')


def calibration(db, findings):
    valid_ids = {finding_id(f): f.get('sha256') for f in findings}
    counts = {'supported': 0, 'false_positive': 0, 'inconclusive': 0, 'stale': 0}
    for fid, digest, label in db.execute('SELECT finding_id,digest,label FROM reviews'):
        if valid_ids.get(fid) != digest:
            counts['stale'] += 1
        else:
            counts[label] += 1
    resolved = counts['supported'] + counts['false_positive']
    return dict(counts=counts, total_findings=len(findings),
                precision_among_reviewed=counts['supported'] / resolved if resolved else None,
                limitation='Proporção de hipóteses sustentadas entre revisadas, não precisão de detecção de corrupção. '
                           'Amostra pode ter viés. Sensibilidade/recall não medido.')
