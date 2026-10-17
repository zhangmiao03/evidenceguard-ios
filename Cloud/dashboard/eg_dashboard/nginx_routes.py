"""Publish the existing read-only Dashboard on each existing TLS App origin.

Only /dashboard and /dashboard/ are routed to 8795. The App /api prefix,
certificates, redirects and upstream authentication retain their configuration.
"""
import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess

BEGIN = '    # BEGIN evidenceguard-public-dashboard'
END = '    # END evidenceguard-public-dashboard'
ROUTES = '''    location = /dashboard {
        proxy_pass http://127.0.0.1:8795;
        proxy_set_header Host $host;
        proxy_read_timeout 15s;
    }
    location ^~ /dashboard/ {
        proxy_pass http://127.0.0.1:8795;
        proxy_set_header Host $host;
        proxy_read_timeout 15s;
        # Public snapshots contain no credentials. Keep compression scoped to
        # the read-only Dashboard, not authenticated App API responses.
        gzip on;
        gzip_types application/json application/javascript text/css application/x-ndjson;
        gzip_min_length 1024;
        gzip_comp_level 5;
        gzip_vary on;
    }'''


def with_dashboard(source, hostname):
    # Read the real server block, preserving all original bytes outside our
    # marked additions. Fail closed on pre-existing unowned dashboard routes.
    clean = re.sub(r'(?m)^' + re.escape(BEGIN) + r'\n.*?^' + re.escape(END) + r'\n?', '', source, flags=re.S)
    candidates = []
    for match in re.finditer(r'(?m)^\s*server\s*\{', clean):
        depth = 1; start = match.end(); index = start
        while depth and index < len(clean):
            if clean[index] == '{': depth += 1
            elif clean[index] == '}': depth -= 1
            index += 1
        if depth: raise ValueError('Unbalanced nginx server block')
        block = clean[start:index-1]
        if re.search(r'\blisten\s+(?:\[::\]:)?443\s+ssl\b', block) and re.search(r'\bserver_name\s+' + re.escape(hostname) + r'\s*;', block):
            if re.search(r'\blocation\s+[^\n{]*dashboard', block):
                raise ValueError('Unowned Dashboard route exists; inspect before editing')
            candidates.append(index-1)
    if len(candidates) != 1: raise ValueError('Expected exactly one matching TLS server')
    at = candidates[0]
    return clean[:at] + BEGIN + '\n' + ROUTES + '\n' + END + '\n' + clean[at:]


def plan(directory=Path('/etc/nginx/sites-enabled')):
    result = {}
    for label in ('demo', 'team', 'review'):
        path = directory / ('evidenceguard-' + label)
        result[path] = with_dashboard(path.read_text(), label + '.47.131.21.137.sslip.io')
    return result


def install():
    changes = plan()
    backup = Path('/var/backups/evidenceguard-dashboard') / ('https-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    backup.mkdir(parents=True, mode=0o700)
    originals = {str(p):base64.b64encode(p.read_bytes()).decode() for p in changes}
    (backup/'nginx.json').write_text(json.dumps(originals)); (backup/'nginx.json').chmod(0o600)
    try:
        for path, value in changes.items(): path.write_text(value)
        subprocess.run(['nginx','-t'],check=True)
        subprocess.run(['systemctl','reload','nginx'],check=True)
    except BaseException:
        for name, raw in originals.items(): Path(name).write_bytes(base64.b64decode(raw))
        subprocess.run(['nginx','-t'],check=True)
        subprocess.run(['systemctl','reload','nginx'],check=True)
        raise
    print(json.dumps({'httpsDashboardRoutes':list(originals),'backup':str(backup)}))


if __name__ == '__main__': install()
