import io
import os
import tempfile
import unittest
from http.client import RemoteDisconnected
from unittest.mock import patch, Mock
from observatorio.public_data import download, read_url


class DownloadTest(unittest.TestCase):
    def test_catalog_retries_disconnect(self):
        response = io.BytesIO(b'catalog')
        transport = Mock()
        transport.open.side_effect = [RemoteDisconnected(), response]
        with patch('observatorio.public_data.opener', return_value=transport), patch('observatorio.public_data.time.sleep'):
            self.assertEqual(read_url('https://arquivos.receitafederal.gov.br/public.php/webdav/', method='PROPFIND'), b'catalog')
        self.assertEqual(transport.open.call_count, 2)

    def test_truncated_transfer_restarts_without_mixing_versions(self):
        first, second = io.BytesIO(b'bad'), io.BytesIO(b'correct')
        first.headers = {'Content-Length': '7'}
        second.headers = {'Content-Length': '7'}
        transport = Mock()
        transport.open.side_effect = [first, second]
        previous = os.getcwd()
        with tempfile.TemporaryDirectory() as folder:
            try:
                os.chdir(folder)
                with patch('observatorio.public_data.opener', return_value=transport), patch('observatorio.public_data.time.sleep'):
                    path, digest = download('https://arquivos.receitafederal.gov.br/example.zip')
                self.assertEqual(path.read_bytes(), b'correct')
                self.assertEqual(len(digest), 64)
            finally:
                os.chdir(previous)
