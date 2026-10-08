import tempfile
import unittest
from datetime import date
from pathlib import Path

from observatorio.core import connect, current, save
from observatorio.history import backfill
from observatorio.sources import cursor


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = connect(Path(self.temp.name) / 'history.sqlite3')

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def run_backfill(self, fetch, pages=1):
        return backfill(self.db, pages=pages, earliest='2026-10-01',
                        today=date(2026, 10, 8), fetch=fetch)

    @staticmethod
    def response(page=1, total=2, pages=2, cid='a', value=10):
        return dict(numeroPagina=page, totalRegistros=total, totalPaginas=pages,
                    data=[dict(numeroControlePNCP=cid, valorGlobal=value)])

    def test_resume_after_network_failure_and_finish_range(self):
        self.run_backfill(lambda _: self.response())
        def fail(_):
            raise TimeoutError()
        with self.assertRaises(TimeoutError):
            self.run_backfill(fail)
        urls = []
        def fetch(url):
            urls.append(url)
            return self.response(page=2, cid='b')
        self.run_backfill(fetch, pages=5)
        self.assertEqual(len(urls), 1)
        self.assertIn('pagina=2', urls[0])
        self.assertEqual(cursor(self.db, 'history_day'), '2026-09-30')
        self.assertEqual(len(current(self.db)), 2)
        self.run_backfill(lambda _: self.fail('Completed range was fetched again'))

    def test_duplicate_page_resets_window_preserving_contracts(self):
        self.run_backfill(lambda _: self.response())
        with self.assertRaises(ValueError):
            self.run_backfill(lambda _: self.response(page=2))
        self.assertEqual(self.db.execute('SELECT next_page FROM history_days').fetchone()[0], 1)
        self.assertEqual(len(current(self.db)), 1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM history_seen').fetchone()[0], 0)

    def test_total_mismatch_rolls_back_new_records(self):
        with self.assertRaises(ValueError):
            self.run_backfill(lambda _: self.response(total=2, pages=1))
        self.assertEqual(len(current(self.db)), 0)

    def test_known_contract_is_not_replaced_by_old_listing(self):
        with self.db:
            save(self.db, dict(numeroControlePNCP='a', valorGlobal=999), 'https://pncp.gov.br/detail')
        self.run_backfill(lambda _: self.response(total=1, pages=1))
        self.assertEqual(current(self.db)[0]['data']['valorGlobal'], 999)
        self.assertEqual(self.db.execute('SELECT count(*) FROM snapshots').fetchone()[0], 1)

    def test_empty_day_advances(self):
        self.run_backfill(lambda _: None)
        self.assertEqual(cursor(self.db, 'history_day'), '2026-09-30')

    def test_invalid_pages_and_rows_are_rejected(self):
        for change in [dict(totalPaginas=0), dict(totalPaginas=True), dict(numeroPagina=True),
                       dict(data=[None]), dict(data=[{}]), dict(totalRegistros=0),
                       dict(totalPaginas=3), dict(data=[])]:
            with self.subTest(change=change):
                response = self.response()
                response.update(change)
                with self.assertRaises(ValueError):
                    self.run_backfill(lambda _: response)
                self.assertEqual(len(current(self.db)), 0)


if __name__ == '__main__':
    unittest.main()
