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
    if info.get('EGSDKManagedAccount') == 'YES':
        for key in ('EGSDKUserID', 'EGSDKAuthToken', 'EGSDKEnvironment'):
            value = info.get(key)
            if not isinstance(value, str) or not value.strip() or '$(' in value or '${' in value:
                raise ValueError('Managed SDK account is incomplete: ' + key)
        if info['EGSDKEnvironment'] not in {'PR', 'QA'}:
            raise ValueError('Managed SDK environment must be PR or QA.')


def validate_sdk_app(app: Path) -> None:
    with (app / 'Info.plist').open('rb') as file:
        validate_sdk_host(plistlib.load(file))
    for relative in ('Frameworks/SampleCore.framework/SampleCore',
                     'Frameworks/AnkerWebRTC.framework/AnkerWebRTC'):
        file = app / relative
        if not file.is_file() or file.stat().st_size == 0:
            raise ValueError('Official SDK framework missing: ' + relative)
    resources = app / 'compose-resources/composeResources/com.anker.esiotkit.demo.generated.resources'
    if not resources.is_dir() or not any(file.is_file() for file in resources.rglob('*')):
        raise ValueError('Official Compose UI resources are missing from the app.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plist', nargs='?', type=Path,
                        default=Path(__file__).resolve().parents[1] / 'EvidenceGuard/Info.plist')
    parser.add_argument('--app', type=Path, help='Validate a built device app and its packaged UI resources')
    args = parser.parse_args()
    try:
        if args.app:
            validate_sdk_app(args.app)
        else:
            with args.plist.open('rb') as file:
                validate_sdk_host(plistlib.load(file))
    except (OSError, ValueError, plistlib.InvalidFileException) as error:
        parser.error(str(error))
    print('Official SDK host plist check passed.')
