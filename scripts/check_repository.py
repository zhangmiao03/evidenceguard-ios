#!/usr/bin/env python3
"""Check tracked/staged files before sharing the team repository."""
from pathlib import Path
import re
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
names = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
secret_patterns = [
    re.compile(rb'\bsk-[A-Za-z0-9_-]{24,}\b'),
    re.compile(rb'\bgh[pousr]_[A-Za-z0-9]{30,}\b'),
    re.compile(rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
]
errors = []
for name in filter(None, names):
    path = Path(name)
    if name.startswith(('SDK/Vendor/', 'Web/public/sdk/', 'Web/public/official-demo/', 'Web/.official-demo/', 'Cloud/data/')) or path.name.startswith('.env') and path.name != '.env.example' or any(p in {'.venv','node_modules','Pods','DerivedData','xcuserdata'} or p.endswith('.xcarchive') for p in path.parts) or path.suffix in {'.sqlite3','.sqlite','.db','.ipa','.mp4','.mov','.p8','.pem','.key','.p12','.mobileprovision'} or name in {'Release/local.xcconfig','Release/internal-demo.xcconfig'}:
        errors.append(f'Local/private artifact tracked: {name}')
    result = subprocess.run(['git', 'show', ':'+name], cwd=root, capture_output=True)
    if result.returncode:
        errors.append(f'Cannot inspect staged file: {name}')
        continue
    if any(pattern.search(result.stdout) for pattern in secret_patterns):
        # Never print matching bytes or secret values.
        errors.append(f'Possible credential in staged file: {name}')
if errors:
    print('\n'.join(errors))
    sys.exit(1)
print(f'Checked {len(list(filter(None, names)))} files: no prohibited local artifacts or recognized credential patterns.')
