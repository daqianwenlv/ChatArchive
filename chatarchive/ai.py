"""Optional, administrator-configured JSON model adapter. No browser-held credentials."""
from __future__ import annotations
import json
import os
from urllib.parse import urlsplit
import httpx


class ModelUnavailable(ValueError):
    pass


class Model:
    def __init__(self):
        self.base = os.environ.get('CHATARCHIVE_AI_BASE_URL', '').rstrip('/')
        self.name = os.environ.get('CHATARCHIVE_AI_MODEL', '')
        self.key = os.environ.get('CHATARCHIVE_AI_API_KEY', '')
        # Local CLI gateways (e.g. cligw -> gpt-5.5) need around a minute for a 40-group batch; the default keeps the previous limit.
        self.timeout = float(os.environ.get('CHATARCHIVE_AI_TIMEOUT', '50') or 50)

    def status(self):
        return {'ready': bool(self.base and self.name), 'model': self.name if self.base else '',
                'message': 'AI 已配置' if self.base and self.name else '尚未配置 AI，可先手动制定执行方案'}

    def complete(self, system, payload):
        if not self.status()['ready']:
            raise ModelUnavailable('尚未配置 AI。需求已保留，可稍后重试或手动制定方案。')
        url = urlsplit(self.base)
        if url.username or url.password or url.query or url.fragment or (url.scheme != 'https' and not (url.scheme == 'http' and url.hostname in ('localhost', '127.0.0.1', '::1'))):
            raise ModelUnavailable('模型服务地址无效，请管理员检查配置。')
        headers = {'Content-Type': 'application/json'}
        if self.key:
            headers['Authorization'] = 'Bearer ' + self.key
        try:
            with httpx.Client(timeout=httpx.Timeout(self.timeout, connect=10), follow_redirects=False) as client:
                with client.stream('POST', self.base + '/chat/completions', headers=headers, json={
                    'model': self.name, 'messages': [{'role': 'system', 'content': system},
                    {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}],
                    'response_format': {'type': 'json_object'}, 'max_tokens': 5000,
                }) as response:
                    response.raise_for_status()
                    data = bytearray()
                    for chunk in response.iter_bytes():
                        data.extend(chunk)
                        if len(data) > 1048576:
                            raise ValueError('Model response too large')
            envelope = json.loads(data)
            content = envelope['choices'][0]['message']['content']
            if not isinstance(content, str):
                raise ValueError('Missing model content')
            if content.strip().startswith('```'):
                content = content.strip().split('\n', 1)[1].rsplit('```', 1)[0]
            result = json.loads(content)
            if not isinstance(result, dict):
                raise ValueError('Expected object')
            return result
        except Exception:
            # Never return provider responses: they may contain requests or credentials.
            raise ModelUnavailable('AI 暂时未能生成有效结果。需求已保留，请重试或手动修改方案。') from None
