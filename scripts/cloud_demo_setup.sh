#!/usr/bin/env bash
# Run as root on the existing Ubuntu cloud host. No new EC2 resource is created.
# A separate origin, process, Unix user, database and token isolate mobile demo.
# Uses a demo-only access token; never copies team or Apple review credentials.
set -euo pipefail
test "$(id -u)" = 0
demo_hostname="${1:?pass the review HTTPS hostname}"
[[ "$demo_hostname" =~ ^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$ ]]
[[ "$demo_hostname" == *.* && "$demo_hostname" != *..* ]]
test -f /etc/evidenceguard/cloud.env
test -x /opt/evidenceguard/venv/bin/python
test -x /opt/evidenceguard-certbot/bin/certbot
id evidenceguard-demo >/dev/null 2>&1 || useradd --system --home /var/lib/evidenceguard-demo --shell /usr/sbin/nologin evidenceguard-demo
install -d -m 0750 -o root -g evidenceguard-demo /etc/evidenceguard-demo
install -d -m 0700 -o evidenceguard-demo -g evidenceguard-demo /var/lib/evidenceguard-demo

# Copy only model-provider settings; never copy team data or its access token.
/opt/evidenceguard/venv/bin/python - "$demo_hostname" <<'PY'
import json, os, secrets, sys
from pathlib import Path
from dotenv import dotenv_values
source = dotenv_values('/etc/evidenceguard/cloud.env')
target = Path('/etc/evidenceguard-demo/cloud.env')
existing = dotenv_values(target) if target.exists() else {}
names = ['EG_MODEL_VISION', 'EG_MODEL_BASE_URL', 'EG_MODEL_ID', 'EG_MODEL_API_KEY',
         'EG_VIDEO_BASE_URL', 'EG_VIDEO_MODEL_ID', 'EG_VIDEO_API_KEY',
         'EG_EMBED_BASE_URL', 'EG_EMBED_MODEL_ID', 'EG_EMBED_API_KEY']
values = {name: source[name] for name in names if source.get(name)}
values.update(EG_REQUIRE_AUTH='1', EG_ACCESS_TOKEN=existing.get('EG_ACCESS_TOKEN') or secrets.token_urlsafe(48),
              EG_DATABASE='/var/lib/evidenceguard-demo/evidenceguard.sqlite3',
              EG_VIDEO_ROOT='/var/lib/evidenceguard-demo/recordings', EG_ENABLE_SYNTHETIC_DEMO='1',
              EVIDENCEGUARD_FIXTURE_URL='http://127.0.0.1:18789')
target.write_text(''.join(f'{key}={json.dumps(value)}\n' for key,value in values.items()))
os.chmod(target, 0o640)
access = Path('/etc/evidenceguard-demo/access.txt')
access.write_text(f'HTTPS service: https://{sys.argv[1]}\nDemo access token: {values["EG_ACCESS_TOKEN"]}\n'
                  'For isolated mobile demo only. No camera credentials or team recordings.\n')
os.chmod(access, 0o600)
PY
chown root:evidenceguard-demo /etc/evidenceguard-demo/cloud.env

cat > /etc/systemd/system/evidenceguard-demo.service <<'UNIT'
[Unit]
Description=EvidenceGuard internal mobile demo cloud
After=network-online.target
Wants=network-online.target
[Service]
User=evidenceguard-demo
Group=evidenceguard-demo
WorkingDirectory=/opt/evidenceguard-demo/Cloud
Environment=EG_ENV_FILE=/etc/evidenceguard-demo/cloud.env
ExecStart=/opt/evidenceguard/venv/bin/uvicorn evidenceguard.app:app --app-dir /opt/evidenceguard-demo/Cloud/server --host 127.0.0.1 --port 8792 --proxy-headers --forwarded-allow-ips 127.0.0.1 --no-access-log
Restart=on-failure
RestartSec=5
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/var/lib/evidenceguard-demo
MemoryMax=800M
CPUQuota=100%
UMask=0077
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable evidenceguard-demo
systemctl restart evidenceguard-demo

cat > /etc/nginx/sites-available/evidenceguard-demo <<NGINX
server {
    listen 80;
    server_name $demo_hostname;
    location /.well-known/acme-challenge/ { root /var/www/letsencrypt; }
    location / { return 426 "Demo HTTPS configuration pending\n"; }
}
NGINX
ln -sfn /etc/nginx/sites-available/evidenceguard-demo /etc/nginx/sites-enabled/evidenceguard-demo
nginx -t
systemctl reload nginx

# Reuse the owner's already registered ACME account. Do not accept new terms.
/opt/evidenceguard-certbot/bin/certbot certonly --non-interactive --webroot \
  -w /var/www/letsencrypt --cert-name evidenceguard-demo -d "$demo_hostname" \
  --preferred-profile shortlived --keep-until-expiring --renew-hook 'systemctl reload nginx'

cat > /etc/nginx/sites-available/evidenceguard-demo <<NGINX
server {
    listen 80;
    server_name $demo_hostname;
    location /.well-known/acme-challenge/ { root /var/www/letsencrypt; }
    location / { return 308 https://$demo_hostname\$request_uri; }
}
server {
    listen 443 ssl;
    server_name $demo_hostname;
    ssl_certificate /etc/letsencrypt/live/evidenceguard-demo/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/evidenceguard-demo/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    client_max_body_size 153m;
    location / {
        proxy_pass http://127.0.0.1:8792;
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-For \$remote_addr;
        proxy_read_timeout 180s;
        proxy_request_buffering off;
    }
}
NGINX
nginx -t
systemctl reload nginx
printf 'Internal demo service: https://%s\nAccess details remain in /etc/evidenceguard-demo/access.txt (root only).\n' "$demo_hostname"
