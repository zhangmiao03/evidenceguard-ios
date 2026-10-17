from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from eg_dashboard.nginx_routes import with_dashboard, BEGIN, END

SOURCE='''server {
 listen 80;
 server_name demo.example;
 location / { return 301 https://demo.example$request_uri; }
}
server {
 listen 443 ssl;
 server_name demo.example;
 ssl_certificate /existing/cert;
 location / { proxy_pass http://127.0.0.1:8792; }
}
'''

class RouteTests(unittest.TestCase):
    def test_additive_idempotent_route_preserves_existing_app_and_certificate(self):
        result=with_dashboard(SOURCE,'demo.example')
        self.assertEqual(with_dashboard(result,'demo.example'),result)
        original=result[:result.index(BEGIN)]+result[result.index(END)+len(END)+1:]
        self.assertEqual(original,SOURCE)
        self.assertEqual(result.count('proxy_pass http://127.0.0.1:8795;'),2)
        self.assertNotIn('location /api',result)
    def test_unknown_host_or_preexisting_route_is_not_overwritten(self):
        with self.assertRaises(ValueError):with_dashboard(SOURCE,'other.example')
        with self.assertRaises(ValueError):with_dashboard(SOURCE.replace('ssl_certificate','location /dashboard { return 403; }\n ssl_certificate'),'demo.example')

if __name__=='__main__':unittest.main()
