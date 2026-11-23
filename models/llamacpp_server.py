#!/usr/bin/env python3
"""Ollama-compatible HTTP server that runs a GGUF model on the Rock 5T's Mali GPU.

It lets the CPU-only test scripts (evaluate_ollama.py, monitor_resources.py,
analyze_run.py) run unchanged against the GPU, like rkllm_server.py does for
the NPU. The model runs in llama.cpp's llama-server (Vulkan build) inside the
is2-gpu-vulkan Docker image (models/gpu-vulkan.Dockerfile), which carries a
Mesa new enough for the GPU.

Like Ollama, the model is loaded on the first request: this server starts the
container then, and stops it on keep_alive 0, so load time and memory are
measured the same way. Ollama's timing fields are filled from llama-server's
own timings:

  prompt_eval_count / prompt_eval_duration  <- timings.prompt_n / prompt_ms
  eval_count / eval_duration                <- timings.predicted_n / predicted_ms
  load_duration                             <- container start until /health is OK

It uses the same GGUF file as the CPU run (Ollama's blob), so the weights are
identical. Sampling copies what Ollama applied: the request's temperature (0)
and seed, plus the qwen3.5 Modelfile defaults (top_k 20, top_p 0.95,
presence_penalty 1.5). Prompt caching is off so every answer starts fresh.

  python models/llamacpp_server.py --ollama-model qwen3.5:4b --name qwen3.5:4b-gpu \
      --port 11437 --ngl 99

Needs Docker access (the docker group). Loopback only. One request at a time.
"""
import argparse
import hashlib
import json
import subprocess
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import requests

CONTAINER = 'is2-gpu-llama'


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def ollama_model(models_dir, tag):
    """-> (GGUF blob path, Ollama manifest digest) for an Ollama tag like qwen3.5:4b."""
    name, _, version = tag.partition(':')
    manifest = models_dir / 'manifests/registry.ollama.ai/library' / name / (version or 'latest')
    data = json.loads(manifest.read_text())
    layer = next(l for l in data['layers'] if l['mediaType'] == 'application/vnd.ollama.image.model')
    blob = models_dir / 'blobs' / layer['digest'].replace(':', '-')
    # Ollama's model ID (what `ollama list` and /api/tags show). This Ollama
    # version stores it as a manifest-type entry in the layer list; older ones
    # use the hash of the manifest file itself.
    nested = [l['digest'] for l in data['layers']
              if l['mediaType'] == 'application/vnd.docker.distribution.manifest.v2+json']
    digest = (nested[0].split(':', 1)[1] if nested
              else hashlib.sha256(manifest.read_bytes()).hexdigest())
    return blob, layer['digest'].split(':', 1)[1], digest


def file_sha256(path):
    """SHA-256 of a file, cached next to this script's state (hashing GBs takes a while)."""
    st = path.stat()
    cache = Path.home() / '.cache' / 'is2-llamacpp-sha256.json'
    try:
        c = json.loads(cache.read_text()).get(str(path))
        if c and c['size'] == st.st_size and c['mtime'] == st.st_mtime:
            return c['sha256']
    except (OSError, ValueError):
        pass
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1 << 24), b''):
            h.update(block)
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        old = json.loads(cache.read_text()) if cache.exists() else {}
        old[str(path)] = {'size': st.st_size, 'mtime': st.st_mtime, 'sha256': h.hexdigest()}
        cache.write_text(json.dumps(old))
    except (OSError, ValueError):
        pass
    return h.hexdigest()


class Runner:
    def __init__(self, args, blob):
        self.args, self.blob = args, blob
        self.url = f'http://127.0.0.1:{args.backend_port}'
        self.lock = threading.Lock()
        self.loaded_at = None
        self.session = requests.Session()

    def running(self):
        return self.loaded_at is not None

    def start(self):
        """-> load seconds (0 if already running)."""
        if self.loaded_at is not None:
            return 0.0
        a = self.args
        subprocess.run(['docker', 'rm', '-f', CONTAINER], capture_output=True)
        cmd = ['docker', 'run', '-d', '--rm', '--name', CONTAINER, '--network', 'host',
               '--device', '/dev/dri', '--user', f'{a.uid}:{a.uid}',
               '--group-add', str(a.render_gid), '--group-add', str(a.video_gid),
               *(['-e', 'GGML_VK_VISIBLE_DEVICES=none'] if a.hide_gpu else []),
               '-v', f'{self.blob.parent}:/models:ro', a.image,
               '-m', f'/models/{self.blob.name}', '--host', '127.0.0.1',
               '--port', str(a.backend_port), '-ngl', str(a.ngl), '-c', str(a.context),
               '-t', str(a.threads), '--parallel', '1', '--no-webui', '--jinja',
               *(['--no-kv-offload'] if a.kv_on_cpu else [])]
        start = time.perf_counter()
        subprocess.run(cmd, check=True, capture_output=True)
        while True:
            try:
                if self.session.get(self.url + '/health', timeout=2).status_code == 200:
                    break
            except requests.RequestException:
                pass
            state = subprocess.run(['docker', 'inspect', '-f', '{{.State.Running}}', CONTAINER],
                                   capture_output=True, text=True).stdout.strip()
            if state != 'true':
                raise RuntimeError('llama-server container exited during load')
            if time.perf_counter() - start > 600:
                raise RuntimeError('llama-server did not become ready in 600 s')
            time.sleep(0.5)
        self.loaded_at = utc_now()
        return time.perf_counter() - start

    def stop(self):
        with self.lock:
            if self.loaded_at is not None:
                if self.args.log:
                    logs = subprocess.run(['docker', 'logs', CONTAINER], capture_output=True, text=True)
                    with open(self.args.log, 'a', encoding='utf-8') as f:
                        f.write(logs.stdout + logs.stderr)
                subprocess.run(['docker', 'stop', '-t', '10', CONTAINER], capture_output=True)
                self.loaded_at = None

    def chat(self, prompt, max_new, think, opts):
        a = self.args
        with self.lock:
            t0 = time.perf_counter()
            load_s = self.start()
            body = {
                'messages': [{'role': 'user', 'content': prompt}],
                'max_tokens': max_new, 'stream': False, 'cache_prompt': False,
                'temperature': float(opts.get('temperature', 0.0)),
                'seed': int(opts.get('seed', 42)),
                'top_k': int(opts.get('top_k', a.top_k)), 'top_p': float(opts.get('top_p', a.top_p)),
                'min_p': float(opts.get('min_p', 0.0)),
                'presence_penalty': float(opts.get('presence_penalty', a.presence_penalty)),
                'frequency_penalty': float(opts.get('frequency_penalty', 0.0)),
                'repeat_penalty': float(opts.get('repeat_penalty', a.repeat_penalty)),
                'repeat_last_n': int(opts.get('repeat_last_n', 64)),
                'stop': opts.get('stop') or [],
                'chat_template_kwargs': {'enable_thinking': bool(think)},
            }
            r = self.session.post(self.url + '/v1/chat/completions', json=body,
                                  timeout=(10, max(1800, 600 + max_new)))
            total_s = time.perf_counter() - t0
        r.raise_for_status()
        return r.json(), body, load_s, total_s


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--ollama-model', default='qwen3.5:4b', help='Ollama tag whose GGUF to use.')
    ap.add_argument('--ollama-models-dir', type=Path, default=Path.home() / '.ollama/models')
    ap.add_argument('--name', default='qwen3.5:4b-gpu', help='Tag the evaluator uses.')
    ap.add_argument('--port', type=int, default=11437)
    ap.add_argument('--backend-port', type=int, default=8090, help='llama-server port (loopback).')
    ap.add_argument('--image', default='is2-gpu-vulkan:b12633')
    ap.add_argument('--ngl', type=int, default=99, help='Layers on the GPU (99 = all).')
    ap.add_argument('--context', type=int, default=16384)
    ap.add_argument('--threads', type=int, default=4, help='CPU threads for any CPU-side work.')
    ap.add_argument('--top-k', type=int, default=20)
    ap.add_argument('--top-p', type=float, default=0.95)
    ap.add_argument('--presence-penalty', type=float, default=1.5)
    ap.add_argument('--repeat-penalty', type=float, default=1.0)
    ap.add_argument('--uid', type=int, default=1000)
    ap.add_argument('--render-gid', type=int, default=105)
    ap.add_argument('--video-gid', type=int, default=44)
    ap.add_argument('--kv-on-cpu', action='store_true',
                    help='Keep the KV cache (and attention) in system RAM (llama.cpp -nkvo). '
                         'Needed on the Rock 5T: with the KV cache on the GPU, llama-server '
                         'fails with ErrorOutOfDeviceMemory at any context size tried (2k-16k).')
    ap.add_argument('--hide-gpu', action='store_true',
                    help='Run llama.cpp on the CPU only (settings check against the Ollama CPU run).')
    ap.add_argument('--log', help='Append llama-server container logs here on unload.')
    args = ap.parse_args()

    blob, blob_digest, manifest_digest = ollama_model(args.ollama_models_dir, args.ollama_model)
    print(f'Checking {blob.name} ...', flush=True)
    actual = file_sha256(blob)
    if actual != blob_digest:
        raise SystemExit(f'GGUF hash mismatch: {actual} != {blob_digest}')
    image_id = subprocess.run(['docker', 'image', 'inspect', '-f', '{{.Id}}', args.image],
                              capture_output=True, text=True, check=True).stdout.strip()
    runner = Runner(args, blob)
    details = {'format': 'gguf', 'family': 'qwen35', 'parameter_size': '4.2B',
               'quantization_level': 'Q4_K_M', 'runner': 'llama.cpp-vulkan-gpu',
               'context_length': args.context}
    tag = {'name': args.name, 'model': args.name, 'size': blob.stat().st_size,
           'digest': manifest_digest, 'model_blob_sha256': actual, 'details': details}
    version = {'version': 'llama.cpp-b12633-vulkan', 'image': args.image, 'image_id': image_id,
               'mesa': '26.2.7~kisak1~r', 'ngl': args.ngl, 'kv_on_cpu': args.kv_on_cpu}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *a):
            if not self.path.startswith('/api/ps'):
                print(f'{self.address_string()} {fmt % a}', flush=True)

        def send(self, obj, code=200):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == '/api/version':
                self.send(version)
            elif self.path == '/api/tags':
                self.send({'models': [tag]})
            elif self.path == '/api/ps':
                self.send({'models': [{**tag, 'loaded_at': runner.loaded_at}]
                           if runner.running() else []})
            else:
                self.send({'error': 'not found'}, 404)

        def do_POST(self):
            try:
                n = int(self.headers.get('Content-Length') or 0)
                req = json.loads(self.rfile.read(n) or b'{}')
            except ValueError:
                return self.send({'error': 'bad json'}, 400)
            if self.path == '/api/show':
                return self.send({'details': details, 'model_info': {
                    'gguf': str(blob), 'sha256': actual, 'ollama_model': args.ollama_model,
                    **version},
                    'parameters': (f'top_k {args.top_k}\ntop_p {args.top_p}\n'
                                   f'presence_penalty {args.presence_penalty}\n'
                                   f'repeat_penalty {args.repeat_penalty}\nngl {args.ngl}')})
            if self.path == '/api/generate' and req.get('keep_alive') in (0, '0', '0s'):
                runner.stop()
                return self.send({'model': args.name, 'created_at': utc_now(), 'response': '',
                                  'done': True, 'done_reason': 'unload'})
            if self.path != '/api/chat':
                return self.send({'error': 'not found'}, 404)
            if req.get('model') != args.name:
                return self.send({'error': f"model '{req.get('model')}' not found"}, 404)
            msgs = req.get('messages') or []
            if len(msgs) != 1 or msgs[0].get('role') != 'user':
                return self.send({'error': 'only a single user message is supported'}, 400)
            opts = req.get('options') or {}
            if opts.get('num_ctx', args.context) != args.context:
                return self.send({'error': f'num_ctx must equal server --context {args.context}'}, 400)
            max_new = int(opts.get('num_predict', 2048))
            try:
                data, body, load_s, total_s = runner.chat(
                    msgs[0]['content'], max_new, bool(req.get('think', False)), opts)
            except Exception as exc:  # Report, never hide, a failed run.
                return self.send({'error': str(exc)}, 500)
            choice = data['choices'][0]
            msg = choice['message']
            t = data.get('timings', {})
            out = {'role': 'assistant', 'content': msg.get('content') or ''}
            if msg.get('reasoning_content'):
                out['thinking'] = msg['reasoning_content']  # Evaluator rejects this when think is off.
            self.send({
                'model': args.name, 'created_at': utc_now(), 'message': out, 'done': True,
                'done_reason': 'length' if choice.get('finish_reason') == 'length' else 'stop',
                'total_duration': int(total_s * 1e9), 'load_duration': int(load_s * 1e9),
                'prompt_eval_count': t.get('prompt_n', 0),
                'prompt_eval_duration': int(t.get('prompt_ms', 0) * 1e6),
                'eval_count': t.get('predicted_n', 0),
                'eval_duration': int(t.get('predicted_ms', 0) * 1e6),
                'llamacpp_timings': t, 'llamacpp_request': {k: v for k, v in body.items()
                                                            if k != 'messages'},
            })

    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'Serving {args.name} on http://127.0.0.1:{args.port} (GGUF sha256 {actual[:12]}..., '
          f'ngl {args.ngl})', flush=True)
    try:
        server.serve_forever()
    finally:
        runner.stop()


if __name__ == '__main__':
    main()
