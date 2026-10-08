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
parser.add_argument('--execute', action='store_true', help='Archive locally; never uploads or submits review')
args = parser.parse_args()
url = urlsplit(args.api_url)
if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in {'', '/'} or url.hostname in {'localhost','127.0.0.1','unconfigured.invalid'}:
    parser.error('--api-url must be a reachable HTTPS origin without credentials, query or fragment')
if not re.fullmatch(r'[A-Z0-9]{10}', args.team) or not re.fullmatch(r'[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+', args.bundle_id) or not re.fullmatch(r'\d+(\.\d+){1,2}', args.version) or args.build < 1:
    parser.error('Invalid Team ID, Bundle ID, version or build number')
command = ['xcodebuild', '-workspace', 'EvidenceGuard.xcworkspace', '-scheme', 'EvidenceGuardSDK', '-configuration', 'Release', '-destination', 'generic/platform=iOS', '-archivePath', str(root/'Release/EvidenceGuard.xcarchive'), f'DEVELOPMENT_TEAM={args.team}', f'PRODUCT_BUNDLE_IDENTIFIER={args.bundle_id}', f'EG_SERVICE_BASE_URL={args.api_url.rstrip("/")}', f'MARKETING_VERSION={args.version}', f'CURRENT_PROJECT_VERSION={args.build}', '-allowProvisioningUpdates', 'archive']
if not args.execute:
    print('Dry run: '+shlex.join(command))
    print('This prepares an archive only. Upload and Beta App Review are separate steps.')
elif not (root/'EvidenceGuard.xcworkspace').exists() or not (root/'Pods/Manifest.lock').exists():
    parser.error('Restore the official SDK and complete python3 SDK/prepare.py before archiving')
else:
    subprocess.run(command, cwd=root, check=True)
