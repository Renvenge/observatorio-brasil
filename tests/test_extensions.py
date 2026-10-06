import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from manage import backup, restore
from observatorio.core import connect, current, save
from observatorio.export import export_public
from observatorio.intelligence import calibration, duplication, finding_id, price_comparison
from observatorio.sources import collect_cgu, collect_obras, cursor, refresh_contracts, resource, resources


class ExtensionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / 'db.sqlite3'
        self.db = connect(self.path)

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def contract(self, n=1):
        row = dict(numeroControlePNCP=f'00000000000001-2-{n:06d}/2026', receita=False,
                   valorInicial=100, valorGlobal=150, niFornecedor='123', numeroControlePncpCompra='compra1',
                   objetoContrato='objeto', dataAssinatura='2026-01-01', orgaoEntidade={'cnpj': '1'})
        with self.db:
            save(self.db, row, 'https://pncp.gov.br/')
        return row

    def test_backup_restore_and_corruption(self):
        self.contract()
        file = self.root / 'backup.gz'
        backup(self.path, file)
        restored = self.root / 'restored.sqlite3'
        restore(file, restored)
        db = connect(restored)
        self.assertEqual(len(current(db)), 1)
        db.close()
        file.write_bytes(file.read_bytes() + b'corrupted')
        with self.assertRaises(ValueError):
            restore(file, restored)

    def test_failed_refresh_rotates_without_deleting(self):
        first, second = self.contract(), self.contract(2)
        seen = []
        def fail(url):
            seen.append(url)
            raise TimeoutError()
        refresh_contracts(self.db, 1, fail)
        refresh_contracts(self.db, 1, fail)
        self.assertNotEqual(seen[0], seen[1])
        self.assertEqual(len(current(self.db)), 2)

    def test_resource_versions_and_resumable_pages(self):
        response = dict(data=[{'id_projeto_investimento': 'x'}], total_items=2, total_pages=2, page_number=1)
        collect_obras(self.db, 1, lambda _: response)
        self.assertEqual(cursor(self.db, 'obras_page'), '2')
        with self.assertRaises(ValueError):
            collect_obras(self.db, 1, lambda _: response)
        self.assertEqual(cursor(self.db, 'obras_page'), '2')
        self.assertEqual(len(resources(self.db, 'obras')), 1)
        with self.db:
            resource(self.db, 'obras', 'x', {'id_projeto_investimento': 'x', 'situacao': 'nova'}, 'https://example.org')
        self.assertEqual(self.db.execute('SELECT count(*) FROM resources').fetchone()[0], 2)

    def test_credentials_absent_never_queries(self):
        with patch.dict(os.environ, {}, clear=True):
            collect_cgu(self.db, '2026-10-05', fetch=lambda _: self.fail('network should not run'))
        self.assertEqual(self.db.execute('SELECT status FROM source_status').fetchone()[0], 'credentials_required')

    def test_price_equivalence_and_zero(self):
        row = dict(item_code='x', specification='x', unit='m', uf='PE', month='2026-09',
                   tax_regime='x', price_basis='x', source='https://example.org', unit_price=100)
        self.assertEqual(price_comparison({**row, 'unit_price': 125}, row)['difference_percent'], 25)
        self.assertEqual(price_comparison({**row, 'unit': 'm2'}, row)['status'], 'incomparable')
        self.assertEqual(price_comparison(row, {**row, 'unit_price': 0})['status'], 'incomparable')

    def test_duplicate_signals_and_stale_reviews(self):
        self.contract()
        self.contract(2)
        findings = duplication(current(self.db))
        self.assertEqual(len(findings), 2)
        f = findings[0]
        with self.db:
            self.db.execute('INSERT INTO reviews VALUES (?,?,?,?,?)',
                            (finding_id(f), f['sha256'], 'false_positive', 'Lotes distintos', '2026-10-06'))
        self.assertEqual(calibration(self.db, findings)['precision_among_reviewed'], 0)
        self.assertEqual(calibration(self.db, [])['counts']['stale'], 1)

    def test_export_missing_money_is_not_zero(self):
        self.contract()
        with self.db:
            resource(self.db, 'obras', 'x', {'desc_nome': 'Obra'}, 'https://example.org')
        meta = export_public(self.db, self.root / 'out')
        data = json.loads((self.root / 'out/current.json').read_text(encoding='utf-8'))
        self.assertIsNone(data['works'][0]['expenses'])
        self.assertIsNone(meta['calibration']['precision_among_reviewed'])
        self.assertNotIn('123', data['contracts'][0]['supplier'])


if __name__ == '__main__':
    unittest.main()
