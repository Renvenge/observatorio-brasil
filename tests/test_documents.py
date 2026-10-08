import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
from observatorio.documents import analyze_url, extract_pdf

SOURCE = 'https://pncp.gov.br/pncp-api/v1/orgaos/1/arquivos/1'


class DocumentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'document.pdf'

    def tearDown(self):
        self.temp.cleanup()

    def make_pdf(self, text=True, encrypted=False):
        writer = PdfWriter()
        page = writer.add_blank_page(width=300, height=300)
        if text:
            font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                                     NameObject('/Subtype'): NameObject('/Type1'),
                                     NameObject('/BaseFont'): NameObject('/Helvetica')})
            page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'):
                DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
            stream = DecodedStreamObject()
            stream.set_data(b'BT /F1 12 Tf 10 200 Td (Contrato: 10 unidades por R$ 50,00) Tj ET')
            page[NameObject('/Contents')] = writer._add_object(stream)
        if encrypted:
            writer.encrypt('test-password')
        writer.write(self.path)

    def test_extract_preserves_page_and_document_digest(self):
        self.make_pdf()
        report = extract_pdf(self.path, SOURCE)
        self.assertEqual(report['status'], 'extracted')
        self.assertEqual(report['pages'][0]['page'], 1)
        self.assertIn('10 unidades', report['pages'][0]['text'])
        self.assertEqual(report['sha256'], hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertNotIn('findings', report)

    def test_no_text_is_pending_not_a_clean_document(self):
        self.make_pdf(text=False)
        report = extract_pdf(self.path, SOURCE)
        self.assertEqual(report['status'], 'partial')
        self.assertEqual(report['pending_pages'][0]['page'], 1)

    def test_encrypted_or_invalid_document_rejected(self):
        self.make_pdf(encrypted=True)
        with self.assertRaises(ValueError):
            extract_pdf(self.path, SOURCE)
        self.path.write_bytes(b'<html>server unavailable</html>')
        with self.assertRaises(ValueError):
            extract_pdf(self.path, SOURCE)

    def test_text_limit_is_explicit(self):
        self.make_pdf()
        with patch('observatorio.documents.MAX_CHARACTERS', 5):
            report = extract_pdf(self.path, SOURCE)
        self.assertTrue(report['truncated'])
        self.assertEqual(report['status'], 'partial')
        self.assertEqual(len(report['pages'][0]['text']), 5)

    def test_worker_writes_report_only_locally(self):
        self.make_pdf()
        digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
        out = Path(self.temp.name) / 'report.json'
        with patch('observatorio.documents.download', return_value=(self.path, digest)):
            summary = analyze_url(SOURCE, out)
        self.assertNotIn('pages', summary)
        self.assertIn('10 unidades', json.loads(out.read_text(encoding='utf-8'))['pages'][0]['text'])

    def test_external_source_rejected_before_download(self):
        with patch('observatorio.documents.download') as download:
            with self.assertRaises(ValueError):
                analyze_url('https://example.org/document.pdf', self.path)
        download.assert_not_called()


if __name__ == '__main__':
    unittest.main()
