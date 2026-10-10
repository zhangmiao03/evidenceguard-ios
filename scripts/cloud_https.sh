#!/usr/bin/env bash
# Run only after the account owner explicitly accepts the linked subscriber agreement.
set -euo pipefail
test "$(id -u)" = 0
public_ipv4="${1:?pass public IPv4}"
[[ "$public_ipv4" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]
test "${2:-}" = '--accept-subscriber-agreement' || { printf 'Owner approval for certificate agreement is required.\n'; exit 2; }
certbot=/opt/evidenceguard-certbot/bin/certbot
test -x "$certbot"
"$certbot" certonly --non-interactive --agree-tos --register-unsafely-without-email \
    --preferred-profile shortlived --webroot --webroot-path /var/www/letsencrypt \
    --ip-address "$public_ipv4" --cert-name "$public_ipv4" --deploy-hook 'systemctl reload nginx'
cp /etc/nginx/sites-available/evidenceguard /etc/nginx/sites-available/evidenceguard.before-https
cat > /etc/nginx/sites-available/evidenceguard <<NGINX
server {
    listen 80 default_server;
    server_name $public_ipv4;
    location /.well-known/acme-challenge/ { root /var/www/letsencrypt; }
    location / { return 308 https://$public_ipv4\$request_uri; }
}
server {
    listen 443 ssl default_server;
    server_name $public_ipv4;
    ssl_certificate /etc/letsencrypt/live/$public_ipv4/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$public_ipv4/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    client_max_body_size 153m;
    location / {
        proxy_pass http://127.0.0.1:8790;
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-For \$remote_addr;
        proxy_read_timeout 180s;
        proxy_request_buffering off;
    }
}
NGINX
if ! nginx -t; then
    cp /etc/nginx/sites-available/evidenceguard.before-https /etc/nginx/sites-available/evidenceguard
    exit 1
fi
systemctl reload nginx
cat > /etc/systemd/system/evidenceguard-cert-renew.service <<'UNIT'
[Unit]
Description=Renew EvidenceGuard IP certificate and reload Nginx
[Service]
Type=oneshot
ExecStart=/opt/evidenceguard-certbot/bin/certbot renew --quiet --deploy-hook "systemctl reload nginx"
UNIT
cat > /etc/systemd/system/evidenceguard-cert-renew.timer <<'UNIT'
[Unit]
Description=Check short-lived certificate renewal every six hours
[Timer]
OnCalendar=*-*-* 00,06,12,18:00:00
RandomizedDelaySec=600
Persistent=true
[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
systemctl enable --now evidenceguard-cert-renew.timer
"$certbot" renew --dry-run
printf 'HTTPS configured; verify certificate trust and authenticated API from a separate client.\n'
