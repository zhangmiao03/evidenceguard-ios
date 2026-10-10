#!/usr/bin/env bash
# Run as root on Ubuntu 24.04 after copying the Cloud source and cloud.env.
set -euo pipefail
test "$(id -u)" = 0
public_ipv4="${1:?pass the EC2 public IPv4 address}"
[[ "$public_ipv4" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]
id evidenceguard >/dev/null 2>&1 || useradd --system --home /var/lib/evidenceguard --shell /usr/sbin/nologin evidenceguard
install -d -m 0755 /opt/evidenceguard /etc/evidenceguard /var/www/letsencrypt
install -d -o evidenceguard -g evidenceguard -m 0700 /var/lib/evidenceguard
install -m 0640 -o root -g evidenceguard /tmp/evidenceguard-cloud.env /etc/evidenceguard/cloud.env
tar -xzf /tmp/evidenceguard-cloud.tar.gz -C /opt/evidenceguard
python3 -m venv /opt/evidenceguard/venv
/opt/evidenceguard/venv/bin/pip install --quiet -r /opt/evidenceguard/Cloud/server/requirements.txt
cat > /etc/systemd/system/evidenceguard.service <<'UNIT'
[Unit]
Description=EvidenceGuard single-team cloud agent
After=network-online.target
Wants=network-online.target
[Service]
User=evidenceguard
Group=evidenceguard
WorkingDirectory=/opt/evidenceguard/Cloud
Environment=EG_ENV_FILE=/etc/evidenceguard/cloud.env
ExecStart=/opt/evidenceguard/venv/bin/uvicorn evidenceguard.app:app --app-dir /opt/evidenceguard/Cloud/server --host 127.0.0.1 --port 8790 --proxy-headers --forwarded-allow-ips 127.0.0.1 --no-access-log
Restart=on-failure
RestartSec=5
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/var/lib/evidenceguard
UMask=0077
[Install]
WantedBy=multi-user.target
UNIT
cat > /etc/nginx/sites-available/evidenceguard <<NGINX
server {
    listen 80 default_server;
    server_name $public_ipv4;
    location /.well-known/acme-challenge/ { root /var/www/letsencrypt; }
    location = /api/health { proxy_pass http://127.0.0.1:8790; }
    location / { return 426 "HTTPS configuration pending\n"; }
}
NGINX
if test -L /etc/nginx/sites-enabled/default; then unlink /etc/nginx/sites-enabled/default; fi
ln -sfn /etc/nginx/sites-available/evidenceguard /etc/nginx/sites-enabled/evidenceguard
nginx -t
systemctl daemon-reload
systemctl enable --now evidenceguard
systemctl reload nginx
rm -f /tmp/evidenceguard-cloud.env
printf 'Cloud service installed; API remains behind HTTPS gate.\n'
