#!/usr/bin/env bash
# Run as root on the existing Ubuntu cloud host. No new EC2 resource is created.
# A separate origin, process, Unix user, database and token isolate Apple review.
# This does not share the review token with Apple or invite any tester.
set -euo pipefail
test "$(id -u)" = 0
review_hostname="${1:?pass the review HTTPS hostname}"
[[ "$review_hostname" =~ ^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$ ]]
[[ "$review_hostname" == *.* && "$review_hostname" != *..* ]]
test -f /etc/evidenceguard/cloud.env
test -x /opt/evidenceguard/venv/bin/python
test -x /opt/evidenceguard-certbot/bin/certbot
id evidenceguard-review >/dev/null 2>&1 || useradd --system --home /var/lib/evidenceguard-review --shell /usr/sbin/nologin evidenceguard-review
install -d -m 0750 -o root -g evidenceguard-review /etc/evidenceguard-review
install -d -m 0700 -o evidenceguard-review -g evidenceguard-review /var/lib/evidenceguard-review

# Copy only model-provider settings; never copy team data or its access token.
/opt/evidenceguard/venv/bin/python - "$review_hostname" <<'PY'
import json, os, secrets, sys
from pathlib import Path
from dotenv import dotenv_values
source = dotenv_values('/etc/evidenceguard/cloud.env')
target = Path('/etc/evidenceguard-review/cloud.env')
existing = dotenv_values(target) if target.exists() else {}
names = ['EG_MODEL_BASE_URL', 'EG_MODEL_ID', 'EG_MODEL_API_KEY',
         'EG_VIDEO_BASE_URL', 'EG_VIDEO_MODEL_ID', 'EG_VIDEO_API_KEY',
         'EG_EMBED_BASE_URL', 'EG_EMBED_MODEL_ID', 'EG_EMBED_API_KEY']
values = {name: source[name] for name in names if source.get(name)}
values.update(EG_REQUIRE_AUTH='1', EG_ACCESS_TOKEN=existing.get('EG_ACCESS_TOKEN') or secrets.token_urlsafe(48),
              EG_DATABASE='/var/lib/evidenceguard-review/evidenceguard.sqlite3',
              EG_VIDEO_ROOT='/var/lib/evidenceguard-review/recordings',
              EVIDENCEGUARD_FIXTURE_URL='http://127.0.0.1:18788')
target.write_text(''.join(f'{key}={json.dumps(value)}\n' for key,value in values.items()))
os.chmod(target, 0o640)
access = Path('/etc/evidenceguard-review/access.txt')
access.write_text(f'HTTPS service: https://{sys.argv[1]}\nReview access token: {values["EG_ACCESS_TOKEN"]}\n'
                  'For isolated Apple review only. No camera credentials or team recordings.\n')
os.chmod(access, 0o600)
PY
chown root:evidenceguard-review /etc/evidenceguard-review/cloud.env

cat > /etc/systemd/system/evidenceguard-review.service <<'UNIT'
[Unit]
Description=EvidenceGuard isolated Apple review cloud
After=network-online.target
Wants=network-online.target
[Service]
User=evidenceguard-review
Group=evidenceguard-review
WorkingDirectory=/opt/evidenceguard/Cloud
Environment=EG_ENV_FILE=/etc/evidenceguard-review/cloud.env
ExecStart=/opt/evidenceguard/venv/bin/uvicorn evidenceguard.app:app --app-dir /opt/evidenceguard/Cloud/server --host 127.0.0.1 --port 8791 --proxy-headers --forwarded-allow-ips 127.0.0.1 --no-access-log
Restart=on-failure
RestartSec=5
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/var/lib/evidenceguard-review
MemoryMax=800M
CPUQuota=100%
UMask=0077
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable evidenceguard-review
systemctl restart evidenceguard-review

cat > /etc/nginx/sites-available/evidenceguard-review <<NGINX
server {
    listen 80;
    server_name $review_hostname;
    location /.well-known/acme-challenge/ { root /var/www/letsencrypt; }
    location / { return 426 "Review HTTPS configuration pending\n"; }
}
NGINX
ln -sfn /etc/nginx/sites-available/evidenceguard-review /etc/nginx/sites-enabled/evidenceguard-review
nginx -t
systemctl reload nginx

# Reuse the owner's already registered ACME account. Do not accept new terms.
/opt/evidenceguard-certbot/bin/certbot certonly --non-interactive --webroot \
  -w /var/www/letsencrypt --cert-name evidenceguard-review -d "$review_hostname" \
  --preferred-profile shortlived --keep-until-expiring --renew-hook 'systemctl reload nginx'

cat > /etc/nginx/sites-available/evidenceguard-review <<NGINX
server {
    listen 80;
    server_name $review_hostname;
    location /.well-known/acme-challenge/ { root /var/www/letsencrypt; }
    location / { return 308 https://$review_hostname\$request_uri; }
}
server {
    listen 443 ssl;
    server_name $review_hostname;
    ssl_certificate /etc/letsencrypt/live/evidenceguard-review/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/evidenceguard-review/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    client_max_body_size 153m;
    location / {
        proxy_pass http://127.0.0.1:8791;
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
printf 'Isolated review service: https://%s\nAccess details remain in /etc/evidenceguard-review/access.txt (root only).\n' "$review_hostname"
