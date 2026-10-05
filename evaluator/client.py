"""Provider-aware, image-capable Chat Completions client. Never logs credentials."""
import json
import os
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request

PROVIDERS = {
    'compatible': {'base_url': '', 'model': '', 'api_key_env': 'JUDGE_API_KEY', 'token_field': 'max_tokens', 'request_options': {}},
    'deepseek': {'base_url': 'https://api.deepseek.com', 'model': 'deepseek-flash', 'api_key_env': 'DEEPSEEK_API_KEY', 'token_field': 'max_tokens', 'request_options': {'thinking': {'type': 'disabled'}}},
    'kimi': {'base_url': 'https://api.moonshot.ai/v1', 'model': 'kimi-k2.6', 'api_key_env': 'MOONSHOT_API_KEY', 'token_field': 'max_tokens', 'request_options': {'thinking': {'type': 'disabled'}}},
    'openai': {'base_url': 'https://api.openai.com/v1', 'model': 'gpt-4.1-2025-04-14', 'api_key_env': 'OPENAI_API_KEY', 'token_field': 'max_completion_tokens', 'request_options': {}},
}

class JudgeError(RuntimeError):
    """Judge service or response failure; never a model task failure."""

class JudgeConfigurationError(JudgeError):
    """Fatal credentials, model access or request configuration error."""


def resolve_config(supplied=None, overrides=None):
    supplied = {} if supplied is None else supplied
    if not isinstance(supplied, dict):
        raise ValueError('Judge configuration must be an object.')
    values = dict(supplied)
    values.update({k: v for k, v in (overrides or {}).items() if v is not None})
    provider = values.get('provider', 'compatible')
    if provider not in PROVIDERS:
        raise ValueError('Judge provider must be compatible, deepseek, kimi or openai.')
    config = {'provider': provider, 'timeout': 180, 'retries': 3, 'max_tokens': 8192, 'json_mode': True, **PROVIDERS[provider]}
    if set(values) - set(config):
        raise ValueError('Unknown judge configuration fields; keep credentials in environment variables.')
    config.update(values)
    if not isinstance(config['api_key_env'], str) or not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*', config['api_key_env']):
        raise ValueError('Invalid API credential environment variable name.')
    return config


def validate_config(config):
    url = urllib.parse.urlsplit(config.get('base_url', ''))
    if (url.scheme != 'https' or not url.netloc or url.username or url.password or url.query or url.fragment):
        raise ValueError('Judge base_url must be an HTTPS URL without credentials, query or fragment.')
    if not isinstance(config.get('model'), str) or not config['model'].strip():
        raise ValueError('Set an image-capable judge model.')
    if 'YOUR_' in config['model'] or 'YOUR_' in config['base_url']:
        raise ValueError('Replace the example judge host and model with your service settings.')
    if not isinstance(config.get('api_key_env'), str) or not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*', config['api_key_env']):
        raise ValueError('Invalid API credential environment variable name.')
    options = config.get('request_options', {})
    reserved = {'model', 'messages', 'api_key', 'stream', 'max_tokens', 'max_completion_tokens', 'response_format'}
    if not isinstance(options, dict) or set(options) & reserved:
        raise ValueError('request_options cannot override managed request fields or credentials.')
    if config.get('token_field', 'max_tokens') not in {'max_tokens', 'max_completion_tokens'}:
        raise ValueError('token_field must be max_tokens or max_completion_tokens.')
    for key in ('timeout', 'max_tokens'):
        if not isinstance(config[key], (int, float)) or isinstance(config[key], bool) or not math.isfinite(config[key]) or config[key] <= 0:
            raise ValueError('Invalid judge ' + key)
    if type(config['max_tokens']) is not int or not 1 <= config['max_tokens'] <= 393216:
        raise ValueError('Judge max_tokens must be a positive integer up to 393216.')
    if type(config.get('json_mode', True)) is not bool:
        raise ValueError('Judge json_mode must be true or false.')
    if type(config['retries']) is not int or not 0 <= config['retries'] <= 10:
        raise ValueError('Judge retries must be between 0 and 10.')
    if not os.environ.get(config['api_key_env']):
        raise ValueError('Set the judge credential environment variable: ' + config['api_key_env'])


def parse_response(raw):
    choice = raw['choices'][0]
    message = choice['message']
    if choice.get('finish_reason') != 'stop' or message.get('refusal'):
        raise ValueError('Judge response is incomplete or refused.')
    content = message.get('content')
    if isinstance(content, list):
        if any(not isinstance(b, dict) or b.get('type') != 'text' or not isinstance(b.get('text'), str) for b in content):
            raise ValueError('Unsupported judge content blocks.')
        content = ''.join(b['text'] for b in content)
    if not isinstance(content, str):
        raise ValueError('Judge final content must contain JSON.')
    content = content.strip()
    fenced = re.fullmatch(r'```(?:json)?\s*\n(.*?)\n```', content, re.DOTALL)
    if fenced:
        content = fenced.group(1)
    def unique_object(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError('Duplicate JSON field.')
            obj[key] = value
        return obj
    def invalid_constant(value):
        raise ValueError('Non-finite JSON value.')
    parsed = json.loads(content, object_pairs_hook=unique_object, parse_constant=invalid_constant)
    if not isinstance(parsed, dict):
        raise ValueError('Judge must return a JSON object.')
    return parsed


def api_call(messages, config):
    body = {'model': config['model'], 'messages': messages, config.get('token_field', 'max_tokens'): config['max_tokens']}
    if config.get('json_mode', True):
        body['response_format'] = {'type': 'json_object'}
    body.update(config.get('request_options', {}))
    encoded = json.dumps(body, allow_nan=False).encode()
    if len(encoded) > 47 * 1024 * 1024:
        raise ValueError('Judge request too large; reduce frame counts or max-side.')
    url = config['base_url'].rstrip('/')
    if not url.endswith('/chat/completions'):
        url += '/chat/completions'
    for attempt in range(config['retries'] + 1):
        request = urllib.request.Request(url, data=encoded, headers={
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + os.environ[config['api_key_env']]})
        try:
            with urllib.request.urlopen(request, timeout=config['timeout']) as response:
                raw = json.load(response)
            return parse_response(raw), raw
        except urllib.error.HTTPError as exc:
            if exc.code in {400, 401, 403, 404, 405, 422}:
                raise JudgeConfigurationError('Judge HTTP ' + str(exc.code) + ': check credentials, model access, endpoint and request options.') from None
            if exc.code not in {408, 429, 500, 502, 503, 504} or attempt == config['retries']:
                raise JudgeError('Judge HTTP ' + str(exc.code)) from None
        except (urllib.error.URLError, TimeoutError):
            if attempt == config['retries']:
                raise JudgeError('Judge network request failed.') from None
        except (ValueError, KeyError, IndexError, TypeError):
            if attempt == config['retries']:
                raise JudgeError('Judge returned an invalid, refused or incomplete JSON response.') from None
        time.sleep(min(2 ** attempt, 30))
