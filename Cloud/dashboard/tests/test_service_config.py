from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from eg_dashboard.service_config import parse_command


class ServiceConfigTests(unittest.TestCase):
    def command(self, source='/opt/evidenceguard-demo/releases/briefings-20261015/Cloud/server', port='8792'):
        return '{ path=/opt/evidenceguard-demo/venv-build10/bin/uvicorn ; argv[]=/opt/evidenceguard-demo/venv-build10/bin/uvicorn evidenceguard.app:app --app-dir '+source+' --host 127.0.0.1 --port '+port+' --no-access-log ; ignore_errors=no ; pid=123 ; }'

    def test_preserves_current_release_and_flags(self):
        source,venv,command=parse_command(self.command(),'/opt/evidenceguard-demo',8792)
        self.assertEqual(source,'/opt/evidenceguard-demo/releases/briefings-20261015/Cloud/server')
        self.assertEqual(venv,'/opt/evidenceguard-demo/venv-build10')
        self.assertIn('"eg_dashboard.bootstrap:app"',command)
        self.assertIn('"--no-access-log"',command)
        self.assertIn(source,command)

    def test_unexpected_service_cannot_be_overwritten(self):
        for raw in (self.command('/tmp/Cloud/server'),self.command(port='8888'),self.command().replace('127.0.0.1','0.0.0.0'),self.command().replace('evidenceguard.app:app','another.app:app')):
            with self.assertRaises(ValueError):parse_command(raw,'/opt/evidenceguard-demo',8792)


if __name__=='__main__':unittest.main()
