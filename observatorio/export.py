import json
import re
from collections import defaultdict
from pathlib import Path

from .core import amount, current, now, rules
from .discovery import discover
from .intelligence import calibration, duplication, finding_id
from .sources import resources, contract_url
from .politics import political_links, link_coverage


def export_public(db, out='reports'):
    records = current(db)
    ai = discover(records)
    findings = rules(records) + duplication(records) + ai['hypotheses']
    by_id = defaultdict(list)
    for finding in findings:
        finding['finding_id'] = finding_id(finding)
        by_id[finding['contract_id']].append(finding)
    histories = defaultdict(list)
    for cid, raw, stamp, digest in db.execute('SELECT contract_id,payload,collected_at,digest FROM snapshots ORDER BY id'):
        row = json.loads(raw)
        histories[cid].append(dict(at=stamp, value=amount(row.get('valorGlobal')), end=row.get('dataVigenciaFim'), sha256=digest))
    links = {name: {r['id']: r for r in resources(db, 'pncp_' + name)} for name in ('termos', 'arquivos', 'historico')}
    contracts = []
    company_links = political_links(db)
    associations = []
    for record in records:
        d = record['data']
        cid = record['id']
        supplier_id = re.sub(r'[^A-Z0-9]', '', str(d.get('niFornecedor') or '').upper()) if d.get('tipoPessoa') == 'PJ' else ''
        matched = company_links.get(supplier_id[:8], []) if re.fullmatch(r'[A-Z0-9]{12}[0-9]{2}', supplier_id) else []
        for match in matched:
            entry = match.get('entry_date', '')
            start = str(d.get('dataVigenciaInicio') or '')[:10].replace('-', '')
            timing = 'sem_confirmacao_historica'
            if re.fullmatch(r'\d{8}', entry) and len(start) == 8 and entry > start:
                timing = 'entrada_posterior_ao_inicio_do_contrato'
            associations.append(dict(**match, contract_id=cid, supplier=d.get('nomeRazaoSocialFornecedor'),
                supplier_cnpj=supplier_id, organization=(d.get('orgaoEntidade') or {}).get('razaoSocial'),
                uf=(d.get('unidadeOrgao') or {}).get('ufSigla'), city=(d.get('unidadeOrgao') or {}).get('municipioNome'),
                contract_value=amount(d.get('valorGlobal')), contract_start=d.get('dataVigenciaInicio'), timing=timing))
        try:
            source = contract_url(cid)
        except ValueError:
            source = record['source']
        contracts.append(dict(id=cid, organization=(d.get('orgaoEntidade') or {}).get('razaoSocial'),
            uf=(d.get('unidadeOrgao') or {}).get('ufSigla'), city=(d.get('unidadeOrgao') or {}).get('municipioNome'),
            sphere=(d.get('orgaoEntidade') or {}).get('esferaId'), object=d.get('objetoContrato'),
            supplier=d.get('nomeRazaoSocialFornecedor') if d.get('tipoPessoa') == 'PJ' else 'Pessoa física — consulte a fonte',
            value=amount(d.get('valorGlobal')), initial=amount(d.get('valorInicial')), revenue=d.get('receita'),
            published=d.get('dataPublicacaoPncp'), start=d.get('dataVigenciaInicio'), end=d.get('dataVigenciaFim'),
            checked_at=record['checked_at'], source=source, sha256=record['sha256'],
            work_id=d.get('identificadorCipi'), revisions=histories[cid], findings=by_id[cid], political_matches=len(matched),
            documents=[dict(type=name, source=links[name][cid]['source'], checked_at=links[name][cid]['checked_at'])
                       for name in links if cid in links[name]]))
    sources = [dict(name=r[0], checked_at=r[1], status=r[2], message=r[3], metadata=json.loads(r[4]))
               for r in db.execute('SELECT * FROM source_status ORDER BY source')]
    runs = [dict(id=r[0], started=r[1], finished=r[2], start=r[3], end=r[4], status=r[5], records=r[6], pages=r[7], error=r[8])
            for r in db.execute('SELECT * FROM runs ORDER BY id DESC LIMIT 30')]
    works = []
    financial = {r['id']: r for r in resources(db, 'obras_empenho')}
    physical = {r['id']: r for r in resources(db, 'obras_execucao-fisica')}
    for record in resources(db, 'obras'):
        d = record['data']
        money = financial.get(record['id'])
        # Preserve original phases, dates and source; never add them to contract values.
        expenses = [{k: row.get(k) for k in ('nr_empenho', 'data_emissao', 'valor_empenho', 'liquidado', 'pago', 'rppago')}
                    for row in money['data']] if money else None
        works.append(dict(id=record['id'], name=d.get('desc_nome'), uf=d.get('uf_principal'),
                          status=d.get('situacao'), organization=d.get('organizacao_resp'),
                          expected_end=d.get('dt_final_prevista'), actual_end=d.get('dt_final_efetiva'),
                          investments=d.get('investimentos_previstos'), pins=d.get('pins'),
                          source=record['source'], checked_at=record['checked_at'], expenses=expenses,
                          financial_source=money['source'] if money else None,
                          physical=physical.get(record['id'], {}).get('data')))
    destination = Path(out)
    destination.mkdir(parents=True, exist_ok=True)
    metadata = dict(schema_version=2, generated_at=now(), contracts=len(contracts), works=len(works),
        political_links=dict(**link_coverage(db), contract_correspondences=len(associations),
                             linked_contracts=len({r['contract_id'] for r in associations})),
        findings=len(findings), runs=runs, sources=sources, calibration=calibration(db, findings),
        ai={k: v for k, v in ai.items() if k != 'hypotheses'},
        limitations=['Cobertura depende dos períodos consultados e das fontes disponíveis.',
                     'Alertas são hipóteses, não corrupção comprovada.',
                     'Valor contratado, investimento previsto e pagamento não são somáveis.',
                     'Mudança de gestão não estabelece responsabilidade pessoal.'],
        repository='https://github.com/Renvenge/observatorio-brasil')
    (destination / 'current.json').write_text(json.dumps(dict(meta=metadata, contracts=contracts, works=works, associations=associations),
                                                       ensure_ascii=False, allow_nan=False, separators=(',', ':')), encoding='utf-8')
    (destination / 'summary.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    return metadata
