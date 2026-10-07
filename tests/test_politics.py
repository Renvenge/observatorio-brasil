import csv
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from observatorio.core import connect, save
from observatorio.politics import import_tse, import_qsa, masked_cpf, possible_match, political_links


class PoliticalLinksTest(unittest.TestCase):
    def test_partial_identifiers_never_stand_alone(self):
        self.assertEqual(masked_cpf('123.456.789-01'), '***456789**')
        self.assertIsNone(masked_cpf('-4'))
        self.assertIsNone(masked_cpf('***.***.789-**'))
        self.assertTrue(possible_match('JOÃO DA SILVA', '12345678901', 'Joao da Silva', '***456789**'))
        self.assertFalse(possible_match('JOÃO DA SILVA', '12345678901', 'Outra Pessoa', '***456789**'))
        self.assertFalse(possible_match('Mesmo Nome', '***456789**', 'Mesmo Nome', '***456788**'))

    def test_import_discards_full_cpf_and_does_not_confirm_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            db = connect(str(path / 'state.db'))
            headers = ['SQ_CANDIDATO', 'NM_CANDIDATO', 'NR_CPF_CANDIDATO', 'DS_SIT_TOT_TURNO', 'ANO_ELEICAO']
            content = io.StringIO()
            writer = csv.writer(content, delimiter=';')
            writer.writerow(headers)
            writer.writerow(['1', 'JOAO DA SILVA', '12345678901', 'ELEITO', '2022'])
            writer.writerow(['2', 'JOAO DA SILVA', '-4', 'ELEITO', '2022'])
            with zipfile.ZipFile(path / 'tse.zip', 'w') as archive:
                archive.writestr('consulta_cand_2022_BRASIL.csv', content.getvalue().encode('latin-1'))
            import_tse(db, 2022, path / 'tse.zip', 'https://cdn.tse.jus.br/example', 'digest')
            self.assertNotIn('12345678901', '\n'.join(db.iterdump()))
            with db:
                save(db, {'numeroControlePNCP': '12345678000199-2-1/2026', 'tipoPessoa': 'PJ',
                          'niFornecedor': '12345678000199'}, 'https://pncp.gov.br/example')
            content = io.StringIO()
            csv.writer(content, delimiter=';').writerow(['12345678', '2', 'JOAO DA SILVA', '***456789**', '49', '20250101', '', '', '', '', ''])
            with zipfile.ZipFile(path / 'qsa.zip', 'w') as archive:
                archive.writestr('socios.csv', content.getvalue())
            self.assertEqual(import_qsa(db, '2026-09', 'Socios1.zip', path / 'qsa.zip', 'https://arquivos.receitafederal.gov.br/', 'digest')['matches'], 1)
            link = political_links(db)['12345678'][0]
            self.assertEqual(link['classification'], 'correspondencia_a_conferir')
            self.assertEqual(link['candidate']['id'], ':1')
            # A later successful scan that no longer contains the partner removes the match.
            with zipfile.ZipFile(path / 'empty.zip', 'w') as archive:
                archive.writestr('socios.csv', content.getvalue().replace('JOAO DA SILVA', 'OUTRO NOME'))
            import_qsa(db, '2026-09', 'Socios1.zip', path / 'empty.zip', 'https://arquivos.receitafederal.gov.br/', 'new')
            self.assertEqual(political_links(db), {})
            db.close()
