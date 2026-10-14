"""Keep event and live relays in the same real-device view, outside fixtures."""
import json
import os

REAL_SOURCES = frozenset({'official_sdk', 'official_live_ios', 'official_live_web', 'official_live_android'})


def fixture_mode():
    return os.getenv('EG_CAMERA_SOURCE') == 'fixture_lab' or os.getenv('EG_CAMERA_MODE') == 'fixture'


def official_mode(subject=None):
    mode = getattr(subject, '__dict__', {}).get('official_mode')
    if isinstance(mode, bool):
        return mode
    return not fixture_mode() and (os.getenv('EG_CAMERA_SOURCE') == 'official_sdk' or os.getenv('EG_CAMERA_MODE') == 'official')


def registered_device_ids(store):
    # Synchronous recipes read the same persisted identities as the registry.
    # Imported devices remain client-reported; this does not verify ownership.
    result = set()
    with store.lock:
        for table in ('sdk_devices', 'live_devices'):
            if store.db.execute('SELECT 1 FROM sqlite_master WHERE type=? AND name=?', ('table', table)).fetchone():
                result.update(json.loads(row[0])['id'] for row in store.db.execute(f'SELECT payload FROM {table}'))
    return result


def visible_recording(recording, device_ids):
    return recording['sourceType'] in REAL_SOURCES or (recording['sourceType'] == 'uploaded' and recording['cameraId'] in device_ids)
