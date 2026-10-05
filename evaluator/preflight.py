"""Small image + JSON compatibility check, separate from benchmark scoring."""
import base64
import datetime
import secrets
import struct
import zlib
from .client import api_call, validate_config, JudgeConfigurationError

COLORS = {'red': (255, 0, 0), 'green': (0, 255, 0), 'blue': (0, 0, 255), 'yellow': (255, 255, 0)}


def color_image(rgb):
    def chunk(kind, payload):
        return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind + payload))
    pixels = (b'\x00' + bytes(rgb) * 64) * 64
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 64, 64, 8, 2, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress(pixels)) + chunk(b'IEND', b'')
    return 'data:image/png;base64,' + base64.b64encode(png).decode()


def check_judge(config):
    validate_config(config)
    names = secrets.SystemRandom().sample(list(COLORS), 2)
    content = [{'type': 'text', 'text': 'Identify the solid color of each attached image in order. Return only JSON: {"colors": ["color1", "color2"], "image_count": 2}. Use lowercase red, green, blue or yellow.'}]
    content += [{'type': 'image_url', 'image_url': {'url': color_image(COLORS[name])}} for name in names]
    parsed, raw = api_call([{'role': 'user', 'content': content}], config)
    if parsed.get('colors') != names or type(parsed.get('image_count')) is not int or parsed['image_count'] != 2:
        raise JudgeConfigurationError('Judge compatibility check failed: expected two correctly identified images and valid JSON.')
    return {'provider': config['provider'], 'requested_model': config['model'], 'response_model': raw.get('model'),
            'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'checks': {'image_data_urls': True, 'multiple_images': True, 'json_response': True},
            'note': 'Checks basic compatibility only, not grading quality or full-size request capacity.'}
