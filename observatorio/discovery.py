"""IA sem supervisão: outliers estatísticos, nunca probabilidades de fraude."""
import hashlib
import math
from collections import defaultdict
from datetime import date
from statistics import median

from .core import amount

FEATURES = ('valor global', 'variação relativa de valor', 'duração contratual')


def features(data):
    initial, total = amount(data.get('valorInicial')), amount(data.get('valorGlobal'))
    if not initial or total is None or data.get('receita') is not False:
        return None
    try:
        duration = (date.fromisoformat(data['dataVigenciaFim'][:10]) -
                    date.fromisoformat(data['dataVigenciaInicio'][:10])).days
    except (KeyError, TypeError, ValueError):
        return None
    if duration < 0:
        return None
    return [math.log1p(total), total / initial - 1, math.log1p(duration)]


def discover(records, min_group=30):
    from sklearn.ensemble import IsolationForest

    groups = defaultdict(list)
    excluded = 0
    for record in records:
        data = record['data']
        vector = features(data)
        org = data.get('orgaoEntidade') or {}
        category = (data.get('categoriaProcesso') or {}).get('id')
        uf = (data.get('unidadeOrgao') or {}).get('ufSigla')
        kind = (data.get('tipoContrato') or {}).get('id')
        if vector is None or not org.get('esferaId') or category is None or not uf or kind is None:
            excluded += 1
            continue
        groups[(uf, org['esferaId'], category, kind)].append((record, vector))
    hypotheses, assessed, insufficient = [], 0, 0
    for key, group in sorted(groups.items(), key=lambda entry: str(entry[0])):
        if len(group) < min_group:
            insufficient += len(group)
            continue
        vectors = [v for _, v in group]
        if len({tuple(v) for v in vectors}) < 5:
            insufficient += len(group)
            continue
        assessed += len(group)
        model = IsolationForest(n_estimators=200, contamination='auto', random_state=42, n_jobs=1)
        predictions = model.fit_predict(vectors)
        scores = model.score_samples(vectors)
        centers = [median(v[i] for v in vectors) for i in range(3)]
        scales = [max(median(abs(v[i] - centers[i]) for v in vectors), 0.01) for i in range(3)]
        for (record, vector), prediction, score in zip(group, predictions, scores):
            deviations = sorted(range(3), key=lambda i: abs(vector[i] - centers[i]) / scales[i], reverse=True)
            strong = [i for i in deviations if abs(vector[i] - centers[i]) / scales[i] >= 3]
            if prediction != -1 or len(strong) < 2:
                continue
            # Labels describe observations only. They are not new crime classifications.
            signature = [(i, 'acima' if vector[i] > centers[i] else 'abaixo') for i in strong[:2]]
            name = 'Combinação incomum: ' + ' e '.join(FEATURES[i] + ' ' + direction + ' da mediana' for i, direction in signature)
            pattern_id = hashlib.sha256(repr(signature).encode()).hexdigest()[:12]
            hypotheses.append(dict(pattern_id=pattern_id, suggested_name=name,
                status='hipótese estatística não revisada', contract_id=record['id'],
                group=dict(uf=key[0], esfera=key[1], categoria=key[2], tipo_contrato=key[3], size=len(group)),
                model='IsolationForest; seed=42; 200 árvores; v1',
                anomaly_score=round(float(-score), 6),
                score_meaning='Atipicidade no grupo; não é probabilidade de fraude.',
                evidence={field: record['data'].get(field) for field in
                          ('valorInicial', 'valorGlobal', 'dataVigenciaInicio', 'dataVigenciaFim')},
                comparison={'transformed_features': vector, 'group_medians': centers,
                            'transform': ['log1p(valorGlobal)', 'valorGlobal/valorInicial-1', 'log1p(dias)']},
                alternatives=['Diferença legítima de escopo ou quantidade', 'Reajuste ou prorrogação justificados',
                              'Erro de cadastro ou grupo heterogêneo'],
                next_steps=['Conferir documentos e aditivos', 'Comparar objetos e condições equivalentes'],
                source=record['source'], sha256=record['sha256']))
    return dict(method='Detecção exploratória sem supervisão; nomes descritivos automáticos.',
                limitations='Não detecta toda fraude, não prova crime ou novidade de um esquema. '
                             'Grupos não garantem objetos equivalentes; não é comparação de preços unitários.',
                assessed=assessed, excluded_missing_data=excluded,
                excluded_small_or_constant_groups=insufficient, hypotheses=hypotheses)
