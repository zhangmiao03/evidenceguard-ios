"""Bounded, secret-filtered text capture for the explicitly public debug view.

Capture is opt-in. Binary media and private model reasoning are never captured.
The collector repeats structural filtering; credentials are removed in-process,
before SQLite, using both key patterns and the actual process secret values.
"""
from __future__ import annotations
import json
import math
import os
import re
from urllib.parse import quote

VERSION = 1
MAX_TEXT = 512_000
MAX_STRING = 256_000
MAX_ITEMS = 2000
REDACTED = '[redacted]'
TRUNCATED = '[truncated: capture limit]'
SECRET = re.compile(r'authorization|cookie|api.?key|secret|password|passwd|credential|(?:access|refresh|session|security|id)[_-]?token|^token$|private.?key|tokenhash|^sn$|devicesn|serialnumber|accountid|clientid|importedby', re.I)
ENV_SECRET = re.compile(r'api.?key|secret|password|credential|(?:access|refresh|session|security|id)[_-]?token|private.?key', re.I)
PRIVATE_REASONING = {'reasoning_content', 'reasoning', 'thinking', 'chain_of_thought'}
MEDIA = {'imagebase64', 'image_base64', 'image_url', 'input_audio', 'audio_base64'}


def enabled():
    return os.getenv('EG_DASHBOARD_CAPTURE_CONTENT') == '1'


def secret_values():
    values = set()
    for key, value in os.environ.items():
        if ENV_SECRET.search(key) and len(value) >= 8:
            values.update((value, quote(value, safe=''), json.dumps(value, ensure_ascii=False)[1:-1]))
    return sorted(values, key=len, reverse=True)


def clean(value, *, budget=MAX_TEXT, known_secrets=None):
    stats = {'version': VERSION, 'mode': 'full_redacted', 'redactions': 0, 'truncated': False,
             'maxTextCharacters': budget, 'maxStringCharacters': MAX_STRING}
    remaining = budget
    secrets = secret_values() if known_secrets is None else known_secrets

    def omitted(marker=REDACTED):
        stats['redactions'] += 1
        return marker

    def cut():
        stats['truncated'] = True
        stats['mode'] = 'truncated'
        return TRUNCATED

    def text(raw):
        nonlocal remaining
        for secret in secrets:
            if secret and secret in raw:
                stats['redactions'] += raw.count(secret)
                raw = raw.replace(secret, REDACTED)
        def replace(match):
            stats['redactions'] += 1
            return REDACTED
        raw = re.sub(r'-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----', replace, raw, flags=re.S)
        raw = re.sub(r'(?i)\b(?:Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+', replace, raw)
        raw = re.sub(r'\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|(?:AKIA|ASIA)[A-Z0-9]{16}|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)\b', replace, raw)
        raw = re.sub(r'''(?i)(?:api[_-]?key|password|passwd|secret|(?:access|refresh|session)[_-]?token)["']?\s*[=:]\s*(?:"[^"\r\n]*"|'[^'\r\n]*'|[^\s,;}]+)''', replace, raw)
        raw = re.sub(r'(?:密钥|密码|口令|授权码)\s*(?:[：:=]|是|为)\s*[^\s，。；;]+', replace, raw)
        raw = re.sub(r'data:[^\s"<>]*;base64,[A-Za-z0-9+/=\s]+', lambda m: omitted('[binary media omitted]'), raw)
        # URLs can contain signed media credentials or embedded user/passwords.
        raw = re.sub(r'https?://[^\s"<>]+', lambda m: omitted('[remote URL omitted]'), raw)
        limit = min(MAX_STRING, remaining)
        if len(raw) > limit:
            raw = raw[:limit] + '\n' + cut()
        remaining = max(0, remaining - len(raw))
        return raw

    def walk(item, depth=0):
        if depth > 32 or remaining <= 0:
            return cut()
        if isinstance(item, dict):
            result = {}
            for index, (key, val) in enumerate(item.items()):
                if index >= MAX_ITEMS:
                    result['_captureLimit'] = cut(); break
                key = str(key)
                safe_key = text(key)
                if SECRET.search(key):
                    result[safe_key] = omitted()
                elif key.lower() in PRIVATE_REASONING:
                    result[safe_key] = omitted('[private reasoning omitted]')
                elif key.lower() in MEDIA:
                    result[safe_key] = omitted('[binary media omitted]')
                else:
                    result[safe_key] = walk(val, depth + 1)
            return result
        if isinstance(item, (tuple, list)):
            result = [walk(v, depth + 1) for v in item[:MAX_ITEMS]]
            if len(item) > MAX_ITEMS: result.append(cut())
            return result
        if isinstance(item, str):
            # Tool arguments and tool-message bodies are often JSON strings.
            stripped = item.strip()
            if stripped[:1] in {'{', '['} and len(stripped) <= MAX_TEXT:
                try:
                    nested = json.loads(stripped)
                except (ValueError, RecursionError):
                    pass
                else:
                    if isinstance(nested, (dict, list)):
                        return json.dumps(walk(nested, depth + 1), ensure_ascii=False)
            return text(item)
        if isinstance(item, float): return item if math.isfinite(item) else None
        if item is None or isinstance(item, (bool, int)): return item
        return '[unsupported value]'

    result = walk(value)
    return result, stats


def details(**values):
    if not enabled(): return {}
    try:
        content, capture = clean(values)
        return {'content': content, 'capture': capture}
    except Exception:
        # Observability must never cause a tool or a model request to fail.
        return {'capture': {'version': VERSION, 'mode': 'unavailable', 'truncated': False}}


def safe_record(value, depth=0):
    """Recorder hook: retain ordinary full text instead of silently cutting at 16k."""
    result, stats = clean(value, budget=MAX_TEXT * 2)
    if isinstance(result, dict) and stats['truncated'] and isinstance(result.get('capture'), dict):
        result['capture'].update(mode='truncated', truncated=True)
    return result
