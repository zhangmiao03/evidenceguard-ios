import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eg_dashboard import content
from eg_dashboard.collector import public_record


class ContentTests(unittest.TestCase):
    def test_actual_credentials_and_nested_json_are_removed_before_storage(self):
        canary = 'provider-secret-value-928475'
        value = {
            'messages': [{'role': 'user', 'content': 'a normal question ' + canary},
                         {'role': 'tool', 'tool_call_id': 'call-1', 'content': json.dumps({'api_key': 'not-patterned', 'answer': 'normal result'})}],
            'headers': {'Cookie': 'session-content', 'Authorization': 'Bearer another-key'},
            'pem': ('-----BEGIN ' + 'PRIVATE KEY-----\nsensitive-lines\n-----END PRIVATE KEY-----'),
            'jwt': 'eyJhbGciOiJIUzI1NiJ9.payload.signature',
            'signed': 'https://media.invalid/a?token=secretvalue',
            'reasoning_content': 'private model deliberation',
            'encrypted_content': 'opaque-private-reasoning',
            'usage': {'total_tokens': 18, 'completion_tokens_details': {'reasoning_tokens': 2}},
        }
        with patch.dict(os.environ, {'EG_MODEL_API_KEY': canary}):
            cleaned, stats = content.clean(value)
        encoded = json.dumps(cleaned)
        for secret in (canary, 'not-patterned', 'session-content', 'another-key', 'sensitive-lines',
                       'eyJhbGciOiJIUzI1NiJ9', 'secretvalue', 'private model deliberation', 'opaque-private-reasoning'):
            self.assertNotIn(secret, encoded)
        self.assertIn('a normal question', encoded)
        self.assertIn('normal result', encoded)
        self.assertEqual(cleaned['messages'][1]['tool_call_id'], 'call-1')
        self.assertEqual(cleaned['usage']['total_tokens'], 18)
        self.assertEqual(cleaned['usage']['completion_tokens_details']['reasoning_tokens'], 2)
        self.assertGreater(stats['redactions'], 0)

    def test_full_text_survives_recorder_and_public_projection(self):
        long = '正文内容' * 8000 + 'THE-END'
        with patch.dict(os.environ, {'EG_DASHBOARD_CAPTURE_CONTENT': '1'}):
            data = content.safe_record(content.details(answer=long, arguments={}, result=[]))
        projected = public_record({'id': 'r', 'kind': 'event', 'data': data})
        self.assertEqual(projected['data']['content']['answer'], long)
        self.assertEqual(projected['data']['content']['result'], [])
        self.assertFalse(projected['data']['capture']['truncated'])

    def test_limits_are_explicit_and_capture_is_opt_in(self):
        value, capture = content.clean('x' * (content.MAX_STRING + 20))
        self.assertTrue(capture['truncated'])
        self.assertEqual(capture['mode'], 'truncated')
        self.assertTrue(value.endswith(content.TRUNCATED))
        with patch.dict(os.environ, {'EG_DASHBOARD_CAPTURE_CONTENT': '0'}):
            self.assertEqual(content.details(answer='not enabled'), {})

    def test_capture_failure_is_best_effort(self):
        with patch.dict(os.environ, {'EG_DASHBOARD_CAPTURE_CONTENT': '1'}), patch.object(content, 'clean', side_effect=ValueError):
            self.assertEqual(content.details(answer='a')['capture']['mode'], 'unavailable')


if __name__ == '__main__': unittest.main()
