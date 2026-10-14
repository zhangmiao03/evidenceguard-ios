#!/usr/bin/env python3
"""Restore the organizer's complete Web Demo UI, without importing .env or keys.

Original sources and built output stay ignored. Only the host, reproducible
adaptations and source hashes are maintained by EvidenceGuard.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def restore(source: Path, destination: Path) -> dict:
    source = source.resolve()
    required = ('src/App.tsx', 'src/config.ts', 'src/components/LivePanel.tsx',
                'src/components/AIRawFramePanel.tsx', 'src/utils/load-sdk.ts')
    for name in required:
        if not (source / name).is_file():
            raise ValueError(f'Missing official Demo source: {name}')
    config = (source / 'src/config.ts').read_text(encoding='utf-8')
    marker = "const STORAGE_KEY = 'eufy-web-sdk-demo-auth-config';"
    if config.count(marker) != 1:
        raise ValueError('Unknown official config revision; review storage adaptation before importing.')
    # Never expose locally modified DEFAULT_AUTH_CONFIG values in a public build.
    import re
    default = re.search(r'export const DEFAULT_AUTH_CONFIG: AuthConfig = \{(.*?)\};', config, re.S)
    if not default:
        raise ValueError('Unknown DEFAULT_AUTH_CONFIG layout')
    for key in ('appName', 'clientId', 'clientSecret', 'presetKey', 'stationSn', 'eufyUserId', 'accountUuid'):
        if not re.search(rf"\b{key}:\s*(['\"])\1\s*,", default.group(1)):
            raise ValueError(f'Official source must contain empty defaults: {key}')
    files = {}
    for file in sorted((source / 'src').rglob('*')):
        if not file.is_file() or file.suffix not in {'.ts', '.tsx', '.css'}:
            continue
        relative = file.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(file, target)
        files[relative.as_posix()] = hashlib.sha256(file.read_bytes()).hexdigest()
    # The official forms/components stay byte-for-byte intact. Replace only
    # credential persistence; the isolated host supplies optional unsubmitted
    # defaults through a same-origin handshake, never through a URL.
    config = config.split(marker)[0] + '''// EvidenceGuard host adaptation: credentials live only in this iframe.
let memoryConfig: AuthConfig = { ...DEFAULT_AUTH_CONFIG };
export function loadAuthConfig(): AuthConfig { return { ...memoryConfig }; }
export function saveAuthConfig(config: AuthConfig): void { memoryConfig = { ...config }; }
export function seedAuthConfig(config: Partial<AuthConfig>): void {
  memoryConfig = { ...DEFAULT_AUTH_CONFIG, ...config, env: 'us', region: 'US' };
}
'''
    (destination / 'src/config.ts').write_text(config, encoding='utf-8')
    manifest = {'schema': 1, 'source': 'Organizer WebSDKDemo', 'files': files,
                'adaptations': ['config.ts: memory-only credential storage',
                                'host: same-origin API proxy and explicit lifecycle handshake'],
                'ui': 'Original App, AuthForm, LivePanel and AIRawFramePanel'}
    (destination / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='Organizer WebSDKDemo directory (not public/sdk)')
    args = parser.parse_args()
    destination = ROOT / 'Web/.official-demo'
    result = restore(args.source, destination)
    print(f'Restored {len(result["files"])} source files. No SDK login was performed.')
    print('Run: cd Web && npm run build:official (after import_web_sdk.py and npm ci)')
