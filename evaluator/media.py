"""Portable FFmpeg extraction, with ffprobe or FFmpeg metadata probing."""
import base64
import hashlib
import json
import math
import re
import shutil
import subprocess
from array import array
from pathlib import Path
import sys

FFMPEG = None
FFPROBE = None


def run_cmd(args):
    try:
        return subprocess.run(args, check=True, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=120).stdout
    except subprocess.CalledProcessError as exc:
        raise ValueError('Media decoding failed: ' + exc.stderr.decode(errors='replace')[-1200:]) from None


def works(binary):
    if not binary:
        return False
    try:
        return subprocess.run([binary, '-version'], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def configure(ffmpeg=None, ffprobe=None):
    global FFMPEG, FFPROBE
    candidates = [ffmpeg] if ffmpeg else [shutil.which('ffmpeg')]
    if not ffmpeg:
        try:
            import imageio_ffmpeg
            candidates.append(imageio_ffmpeg.get_ffmpeg_exe())
        except ImportError:
            pass
    FFMPEG = next((x for x in candidates if works(x)), None)
    if FFMPEG is None:
        raise ValueError('No working FFmpeg. Install requirements/eval.txt or pass --ffmpeg PATH.')
    candidate = ffprobe or shutil.which('ffprobe')
    FFPROBE = candidate if works(candidate) else None
    if ffprobe and FFPROBE is None:
        raise ValueError('The explicitly selected ffprobe cannot run.')
    return {'ffmpeg': FFMPEG, 'ffprobe': FFPROBE,
            'probe_backend': 'ffprobe' if FFPROBE else 'ffmpeg_metadata',
            'ffmpeg_version': run_cmd([FFMPEG, '-version']).decode().splitlines()[0]}


def probe(path):
    if FFPROBE:
        data = json.loads(run_cmd([FFPROBE, '-v', 'error', '-show_streams',
                                   '-show_format', '-of', 'json', str(path)]))
        duration = float(data.get('format', {}).get('duration', 0))
        streams = data.get('streams', [])
    else:
        # FFmpeg emits demuxed stream metadata even when no output is requested.
        result = subprocess.run([FFMPEG, '-hide_banner', '-i', str(path)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
        text = result.stderr.decode(errors='replace')
        match = re.search(r'Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)', text)
        duration = (int(match[1]) * 3600 + int(match[2]) * 60 + float(match[3])) if match else 0
        streams = []
        for line in text.splitlines():
            if 'Stream #' not in line:
                continue
            if 'Video:' in line:
                geometry = re.search(r'\b(\d{2,5})x(\d{2,5})\b', line)
                if geometry:
                    streams.append({'codec_type': 'video', 'width': int(geometry[1]), 'height': int(geometry[2])})
            elif 'Audio:' in line:
                streams.append({'codec_type': 'audio'})
    if not streams or not math.isfinite(duration) or duration < 0:
        raise ValueError('Cannot read media metadata: ' + str(path))
    return {'duration_s': duration, 'video_streams': [s for s in streams if s['codec_type'] == 'video'],
            'audio_streams': [s for s in streams if s['codec_type'] == 'audio']}


def extract(path, prefix, count, side, folder, start=0, end=None, image=False):
    folder.mkdir(parents=True, exist_ok=True)
    if image:
        times = [None]
    else:
        duration = probe(path)['duration_s']
        stop = duration if end is None else end
        if not (math.isfinite(stop) and 0 <= start < stop <= duration + 0.05):
            raise ValueError('Invalid evaluation interval')
        last = max(start, stop - min(0.1, (stop - start) / 2))
        times = [start + (last - start) * i / (count - 1) for i in range(count)]
    blocks, rows = [], []
    for i, timestamp in enumerate(times):
        command = [FFMPEG, '-v', 'error']
        if timestamp is not None:
            command += ['-ss', str(timestamp)]
        command += ['-i', str(path), '-frames:v', '1', '-vf',
                    "scale='min(%d,iw)':'min(%d,ih)':force_original_aspect_ratio=decrease" % (side, side),
                    '-f', 'image2pipe', '-vcodec', 'mjpeg', 'pipe:1']
        data = run_cmd(command)
        if not data:
            raise ValueError('Empty decoded frame')
        saved = folder / f'{prefix}_{i:03d}.jpg'
        saved.write_bytes(data)
        row = {'id': f'{prefix}:{i}', 'time_s': timestamp,
               'frame_sha256': hashlib.sha256(data).hexdigest(), 'saved_file': str(saved.resolve())}
        rows.append(row)
        blocks.extend([{'type': 'text', 'text': json.dumps({k: v for k, v in row.items() if k != 'saved_file'})},
                       {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' +
                        base64.b64encode(data).decode(), 'detail': 'high'}}])
    return blocks, rows


def decode_pcm(path, sample_rate=8000):
    data = run_cmd([FFMPEG, '-v', 'error', '-i', str(path), '-vn', '-ac', '1',
                    '-ar', str(sample_rate), '-f', 's16le', 'pipe:1'])
    samples = array('h')
    samples.frombytes(data)
    if sys.byteorder != 'little':
        samples.byteswap()
    return samples
