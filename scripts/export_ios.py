#!/usr/bin/env python3
"""Validate, export or upload an existing signed SDK archive using Xcode.

Dry run by default. Upload sends the binary to App Store Connect; it does not
submit Beta App Review, accept agreements, or invite testers.
"""
import argparse
from pathlib import Path
import plistlib
import re
import shlex
import subprocess
from urllib.parse import urlsplit

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--team', required=True)
parser.add_argument('--bundle-id', required=True)
parser.add_argument('--archive', type=Path, default=root / 'Release/EvidenceGuard.xcarchive')
parser.add_argument('--action', choices=['validate', 'export', 'upload'], default='validate')
parser.add_argument('--execute', action='store_true')
args = parser.parse_args()
if not re.fullmatch(r'[A-Z0-9]{10}', args.team) or not re.fullmatch(r'[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+', args.bundle_id):
    parser.error('Invalid Team ID or Bundle ID')
archive = args.archive.resolve()
output = root / 'Release' / args.action
options_path = output / 'ExportOptions.plist'
options = {'method': 'validation' if args.action == 'validate' else 'app-store-connect',
           'destination': 'export' if args.action == 'export' else 'upload',
           'teamID': args.team, 'signingStyle': 'automatic',
           'manageAppVersionAndBuildNumber': False, 'uploadSymbols': True,
           'testFlightInternalTestingOnly': False}
command = ['xcodebuild', '-exportArchive', '-archivePath', str(archive),
           '-exportOptionsPlist', str(options_path), '-exportPath', str(output),
           '-allowProvisioningUpdates']
if not args.execute:
    print('Dry run: ' + shlex.join(command))
    print('Export options: ' + str(options))
    print('No upload or Beta App Review submission was performed.')
    raise SystemExit(0)
apps = list((archive / 'Products/Applications').glob('*.app'))
if len(apps) != 1:
    parser.error('Expected one app in an existing SDK archive. Run archive_ios.py first.')
app = apps[0]
with (app / 'Info.plist').open('rb') as file:
    info = plistlib.load(file)
if info.get('CFBundleIdentifier') != args.bundle_id:
    parser.error('Bundle ID differs from the archived app; refuse to upload the wrong app.')
url = urlsplit(info.get('EGServiceBaseURL', ''))
if url.scheme != 'https' or not url.hostname or url.hostname in {'localhost', '127.0.0.1', 'unconfigured.invalid'}:
    parser.error('Archive has no configured HTTPS service. Prepare the release configuration first.')
if not (app / 'Frameworks/SampleCore.framework/SampleCore').is_file():
    parser.error('Archive does not include the official SDK framework; do not substitute a simulator build.')
subprocess.run(['codesign', '--verify', '--strict', str(app)], check=True)
output.mkdir(parents=True, exist_ok=True)
options_path.write_bytes(plistlib.dumps(options))
subprocess.run(command, cwd=root, check=True)
print('Xcode completed ' + args.action + '. Beta App Review is a separate App Store Connect step.')
