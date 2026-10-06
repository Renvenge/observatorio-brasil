import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from observatorio.core import connect
from observatorio.sources import collect_cgu


class CGUTest(unittest.TestCase):
    def test_required_scope_and_independent_cursor(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'TRANSPARENCIA_API_KEY': 'example', 'CGU_GESTAO': '00001'}):
            db = connect(folder + '/state.db')
            queries = []
            def fetch(url, headers=None):
                queries.append(parse_qs(urlsplit(url).query))
                return []
            collect_cgu(db, '2026-10-05', fetch=fetch)
            self.assertEqual(len(queries), 4)
            self.assertEqual([q['fase'][0] for q in queries[:3]], ['1', '2', '3'])
            self.assertTrue(all(q['gestao'] == ['00001'] for q in queries[:3]))
            self.assertNotIn('gestao', queries[3])
            self.assertEqual(db.execute("SELECT value FROM cursors WHERE name='cgu_day:gestao:00001'").fetchone()[0], '2026-10-06')
            db.close()

    def test_error_exposes_code_without_exception_body_or_key(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'TRANSPARENCIA_API_KEY': 'DO_NOT_PRINT', 'CGU_GESTAO': '00001'}):
            db = connect(folder + '/state.db')
            def fetch(*args, **kwargs):
                raise HTTPError('https://example.invalid/DO_NOT_PRINT', 400, 'DO_NOT_PRINT', {}, None)
            output = io.StringIO()
            with contextlib.redirect_stdout(output), self.assertRaises(HTTPError):
                collect_cgu(db, '2026-10-05', fetch=fetch)
            raw = db.execute("SELECT metadata FROM source_status WHERE source='cgu'").fetchone()[0]
            self.assertEqual(json.loads(raw)['http_status'], 400)
            self.assertNotIn('DO_NOT_PRINT', raw + output.getvalue())
            self.assertEqual(db.execute("SELECT value FROM cursors WHERE name='cgu_day:gestao:00001'").fetchone()[0], '2026-10-05')
            db.close()
