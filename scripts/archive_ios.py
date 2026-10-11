#!/usr/bin/env python3
"""Prepare a signed SDK archive for manual App Store Connect/TestFlight upload."""
import argparse
from pathlib import Path
import re
import shlex
import subprocess
from urllib.parse import urlsplit

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--team', required=True, help='Apple Developer Program Team ID')
parser.add_argument('--bundle-id', required=True, help='Bundle ID registered in this Team')
parser.add_argument('--api-url', required=True, help='Reachable Cloud HTTPS origin; no keys')
parser.add_argument('--version', default='1.0')
parser.add_argument('--build', type=int, required=True, help='Increment on every upload')
parser.add_argument('--demo-config', type=Path, help='Private xcconfig with demo-only credentials; never a model key')
parser.add_argument('--archive', type=Path, default=root/'Release/EvidenceGuard.xcarchive')
parser.add_argument('--execute', action='store_true', help='Archive locally; never uploads or submits review')
args = parser.parse_args()
url = urlsplit(args.api_url)
if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in {'', '/'} or url.hostname in {'localhost','127.0.0.1','unconfigured.invalid'}:
    parser.error('--api-url must be a reachable HTTPS origin without credentials, query or fragment')
if not re.fullmatch(r'[A-Z0-9]{10}', args.team) or not re.fullmatch(r'[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+', args.bundle_id) or not re.fullmatch(r'\d+(\.\d+){1,2}', args.version) or args.build < 1:
    parser.error('Invalid Team ID, Bundle ID, version or build number')
config = []
if args.demo_config:
    if not args.demo_config.is_file(): parser.error('Demo config file is missing')
    values = dict(line.split('=',1) for line in args.demo_config.read_text().splitlines() if '=' in line and not line.lstrip().startswith('//'))
    values = {k.strip():v.strip() for k,v in values.items()}
    if set(values) != {'EG_INTERNAL_DEMO','EG_SERVICE_BASE_URL','EG_DEMO_ACCESS_TOKEN'} or values['EG_INTERNAL_DEMO'] != 'YES' or not re.fullmatch(r'[A-Za-z0-9_-]{32,}',values['EG_DEMO_ACCESS_TOKEN']):
        parser.error('Demo config must contain only the internal flag, origin and a demo-scoped token')
    if values['EG_SERVICE_BASE_URL'].replace('/$()/','//').rstrip('/') != args.api_url.rstrip('/'):
        parser.error('Demo credential origin differs from the archive service URL')
    config = ['-xcconfig',str(args.demo_config.resolve())]
command = ['xcodebuild', '-workspace', 'EvidenceGuard.xcworkspace', '-scheme', 'EvidenceGuardSDK', '-configuration', 'Release', '-destination', 'generic/platform=iOS', '-archivePath', str(args.archive.resolve()), *config, f'DEVELOPMENT_TEAM={args.team}', f'EG_APP_BUNDLE_ID={args.bundle_id}', f'EG_SERVICE_BASE_URL={args.api_url.rstrip("/")}', f'MARKETING_VERSION={args.version}', f'CURRENT_PROJECT_VERSION={args.build}', '-allowProvisioningUpdates', 'archive']
if not args.execute:
    print('Dry run: '+shlex.join(command))
    print('This prepares an archive only. Upload and Beta App Review are separate steps.')
elif not (root/'EvidenceGuard.xcworkspace').exists() or not (root/'Pods/Manifest.lock').exists():
    parser.error('Restore the official SDK and complete python3 SDK/prepare.py before archiving')
else:
    subprocess.run(command, cwd=root, check=True)
