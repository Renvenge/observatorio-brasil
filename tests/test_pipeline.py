import copy
import tempfile
import unittest
from pathlib import Path

from observatorio.core import collect, connect, current, rules, save
from observatorio.discovery import discover
from observatorio.__main__ import safe_cell


def record(n=1):
    return dict(numeroControlePNCP=f'test-{n}', valorInicial=100, valorGlobal=100,
        receita=False, dataVigenciaInicio='2026-01-01', dataVigenciaFim='2027-01-01',
        orgaoEntidade={'esferaId': 'M'}, unidadeOrgao={'ufSigla': 'PE'},
        tipoContrato={'id': 1}, categoriaProcesso={'id': 1})


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = connect(Path(self.tmp.name) / 'test.sqlite3')

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_versions_and_idempotence(self):
        a = record()
        save(self.db, a, 'https://pncp.gov.br/')
        save(self.db, a, 'https://pncp.gov.br/')
        b = copy.deepcopy(a)
        b['valorGlobal'] = 140
        save(self.db, b, 'https://pncp.gov.br/')
        self.assertEqual(self.db.execute('SELECT count(*) FROM snapshots').fetchone()[0], 2)
        self.assertEqual(len(current(self.db)), 1)
        self.assertEqual(rules(current(self.db))[0]['evidence']['percentual'], 40)

    def test_no_invented_zero_or_nan(self):
        for value in [None, 'NaN', -10, True]:
            a = record()
            a['valorInicial'] = value
            save(self.db, a, 'https://pncp.gov.br/')
            self.assertEqual(rules(current(self.db)), [])

    def test_partial_is_not_success(self):
        result = collect(self.db, '2026-01-01', '2026-01-01', 1, lambda _: dict(
            data=[record()], numeroPagina=1, totalPaginas=2, totalRegistros=2))
        self.assertEqual(result['status'], 'partial')

    def test_failed_page_preserves_prior_data(self):
        calls = []
        def fetch(url):
            calls.append(url)
            if len(calls) == 2:
                raise TimeoutError('test')
            return dict(data=[record()], numeroPagina=1, totalPaginas=2, totalRegistros=2)
        with self.assertRaises(TimeoutError):
            collect(self.db, '2026-01-01', '2026-01-01', fetch=fetch)
        self.assertEqual(len(current(self.db)), 1)
        self.assertEqual(self.db.execute('SELECT status FROM runs').fetchone()[0], 'failed')

    def test_repeated_page_rejected(self):
        with self.assertRaises(ValueError):
            collect(self.db, '2026-01-01', '2026-01-01', fetch=lambda _: dict(
                data=[record()], numeroPagina=1, totalPaginas=2, totalRegistros=2))

    def test_full_pagination(self):
        responses = iter([dict(data=[record(1)], numeroPagina=1, totalPaginas=2, totalRegistros=2),
                          dict(data=[record(2)], numeroPagina=2, totalPaginas=2, totalRegistros=2)])
        result = collect(self.db, '2026-01-01', '2026-01-01', fetch=lambda _: next(responses))
        self.assertEqual((result['status'], result['records']), ('complete', 2))

    def test_no_content_and_invalid_schema(self):
        self.assertEqual(collect(self.db, '2026-01-01', '2026-01-01', fetch=lambda _: None)['records'], 0)
        with self.assertRaises(ValueError):
            collect(self.db, '2026-01-01', '2026-01-01', fetch=lambda _: {'unexpected': []})

    def test_csv_formula(self):
        self.assertTrue(safe_cell(' =HYPERLINK("example")').startswith("'"))

    def test_ai_requires_group_and_detects_synthetic_combination(self):
        for n in range(60):
            a = record(n)
            a['valorInicial'] = 100 + n
            a['valorGlobal'] = 100 + n
            save(self.db, a, 'https://pncp.gov.br/')
        a = record(100)
        a['valorGlobal'] = 10000000
        a['dataVigenciaFim'] = '2040-01-01'
        save(self.db, a, 'https://pncp.gov.br/')
        result = discover(current(self.db))
        self.assertTrue(any(h['contract_id'] == 'test-100' for h in result['hypotheses']))
        self.assertEqual(discover(current(self.db)[:2])['hypotheses'], [])
        self.assertEqual(result, discover(current(self.db)))


if __name__ == '__main__':
    unittest.main()
