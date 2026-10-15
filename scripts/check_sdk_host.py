#!/usr/bin/env python3
"""Check the host plist required by the official SDK's Compose 1.7.1 UI.

Accepts either the source plist (CI) or a built app's Info.plist (local release).
Never dumps the plist: a built internal app can contain a demo access token.
"""
import argparse
from pathlib import Path
import plistlib


def validate_sdk_host(info: dict) -> None:
    # PlistSanityCheck.performIfNeeded in Compose 1.7.1 throws asynchronously
    # on first ComposeUIViewController load if this NSNumber is not true.
    # Require the canonical plist boolean, not a string such as "YES".
    if info.get('CADisableMinimumFrameDurationOnPhone') is not True:
        raise ValueError('Official SDK host requires CADisableMinimumFrameDurationOnPhone = <true/>; opening the Compose UI would abort.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plist', nargs='?', type=Path,
                        default=Path(__file__).resolve().parents[1] / 'EvidenceGuard/Info.plist')
    args = parser.parse_args()
    try:
        with args.plist.open('rb') as file:
            validate_sdk_host(plistlib.load(file))
    except (OSError, ValueError, plistlib.InvalidFileException) as error:
        parser.error(str(error))
    print('Official SDK host plist check passed.')
