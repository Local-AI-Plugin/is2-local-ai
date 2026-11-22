#!/usr/bin/env python3
"""Ollama-compatible HTTP server that runs an .rkllm model on the RK3588 NPU.

It lets the CPU-only test scripts (evaluate_ollama.py, monitor_resources.py,
analyze_run.py) run unchanged against the NPU: it answers the Ollama calls
they use (/api/version, /api/tags, /api/show, /api/ps, /api/chat, and
/api/generate with keep_alive 0 to unload) and fills in Ollama's timing
fields from RKLLM's own performance counters:

  prompt_eval_count / prompt_eval_duration  <- perf.prefill_tokens / prefill_time_ms
  eval_count / eval_duration                <- perf.generate_tokens / generate_time_ms
  load_duration                             <- time spent in rkllm_init (cold load)

Like Ollama, the model is loaded on the first request and unloaded on
keep_alive 0, so the monitor sees memory rise from an unloaded start.

Sampling: Ollama sends temperature 0 (greedy). RKLLM has no temperature-0
mode, so greedy is top_k 1. Model-default penalties that Ollama applied to the
CPU run (presence_penalty 1.5 from the qwen3.5 Modelfile) are passed through
--presence-penalty. Stop strings are not enforced here (IFEval sends none); the
evaluator also cuts answers at stop strings itself.

  python models/rkllm_server.py --model ~/rkllm/models/qwen3.5-4b_w8a8_rk3588.rkllm \
      --lib ~/rkllm/librkllmrt.so --name qwen3.5:4b-w8a8-npu --port 11436

Needs the RKLLM runtime (librkllmrt.so, v1.3.x, aarch64) and the rknpu driver.
Loopback only. One request at a time (the NPU runs one inference at a time).
"""
import argparse
import ctypes as C
import hashlib
import json
import os
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# ---- rkllm.h (v1.3.1) -------------------------------------------------------
RKLLM_RUN_NORMAL, RKLLM_RUN_WAITING, RKLLM_RUN_FINISH, RKLLM_RUN_ERROR = 0, 1, 2, 3
RKLLM_INPUT_PROMPT = 0
RKLLM_INFER_GENERATE = 0


class RKLLMExtendParam(C.Structure):
    _fields_ = [('base_domain_id', C.c_int32), ('embed_flash', C.c_int8),
                ('enabled_cpus_num', C.c_int8), ('enabled_cpus_mask', C.c_uint32),
                ('n_batch', C.c_uint8), ('use_cross_attn', C.c_int8),
                ('reserved', C.c_uint8 * 104)]


class RKLLMParam(C.Structure):
    _fields_ = [('model_path', C.c_char_p), ('max_context_len', C.c_int32),
                ('max_new_tokens', C.c_int32), ('top_k', C.c_int32), ('n_keep', C.c_int32),
                ('top_p', C.c_float), ('temperature', C.c_float),
                ('repeat_penalty', C.c_float), ('frequency_penalty', C.c_float),
                ('presence_penalty', C.c_float), ('mirostat', C.c_int32),
                ('mirostat_tau', C.c_float), ('mirostat_eta', C.c_float),
                ('skip_special_token', C.c_bool), ('ignore_eos_token', C.c_bool),
                ('is_async', C.c_bool), ('extend_param', RKLLMExtendParam)]


class RKLLMEmbedInput(C.Structure):
    _fields_ = [('embed', C.POINTER(C.c_float)), ('n_tokens', C.c_size_t)]


class RKLLMTokenInput(C.Structure):
    _fields_ = [('input_ids', C.POINTER(C.c_int32)), ('n_tokens', C.c_size_t)]


class _Image(C.Structure):
    _fields_ = [('image_embed', C.POINTER(C.c_float)), ('n_image_tokens', C.c_size_t),
                ('n_image', C.c_size_t), ('image_start', C.c_char_p),
                ('image_end', C.c_char_p), ('image_content', C.c_char_p),
                ('image_width', C.c_size_t), ('image_height', C.c_size_t)]


class _Video(C.Structure):
    _fields_ = [('video_embed', C.POINTER(C.c_float)), ('n_frame_tokens', C.c_size_t),
                ('n_frame_per_video', C.c_size_t), ('n_video', C.c_size_t),
                ('video_start', C.c_char_p), ('video_end', C.c_char_p),
                ('video_content', C.c_char_p), ('frame_width', C.c_size_t),
                ('frame_height', C.c_size_t)]


class _Audio(C.Structure):
    _fields_ = [('audio_embed', C.POINTER(C.c_float)), ('n_audio_tokens', C.c_size_t),
                ('n_audio', C.c_size_t), ('audio_start', C.c_char_p),
                ('audio_end', C.c_char_p), ('audio_content', C.c_char_p)]


class RKLLMMultiModalInput(C.Structure):
    _fields_ = [('prompt', C.c_char_p), ('image', _Image), ('video', _Video), ('audio', _Audio)]


class _InputUnion(C.Union):
    _fields_ = [('prompt_input', C.c_char_p), ('embed_input', RKLLMEmbedInput),
                ('token_input', RKLLMTokenInput), ('multimodal_input', RKLLMMultiModalInput)]


class RKLLMInput(C.Structure):
    _anonymous_ = ('u',)
    _fields_ = [('role', C.c_char_p), ('enable_thinking', C.c_bool),
                ('input_type', C.c_int), ('u', _InputUnion)]


class RKLLMSamplingParam(C.Structure):
    _fields_ = [('top_k', C.c_int32), ('top_p', C.c_float), ('temperature', C.c_float),
                ('repeat_penalty', C.c_float), ('frequency_penalty', C.c_float),
                ('presence_penalty', C.c_float), ('mirostat', C.c_int32),
                ('mirostat_tau', C.c_float), ('mirostat_eta', C.c_float)]


class RKLLMInferParam(C.Structure):
    _fields_ = [('mode', C.c_int), ('lora_params', C.c_void_p),
                ('prompt_cache_params', C.c_void_p),
                ('sampling_params', C.POINTER(RKLLMSamplingParam)),
                ('keep_history', C.c_int), ('max_new_tokens', C.c_int32)]


class _Hidden(C.Structure):
    _fields_ = [('hidden_states', C.POINTER(C.c_float)), ('embd_size', C.c_int),
                ('num_tokens', C.c_int)]


class _Logits(C.Structure):
    _fields_ = [('logits', C.POINTER(C.c_float)), ('vocab_size', C.c_int),
                ('num_tokens', C.c_int)]


class RKLLMPerfStat(C.Structure):
    _fields_ = [('prefill_time_ms', C.c_float), ('prefill_tokens', C.c_int),
                ('generate_time_ms', C.c_float), ('generate_tokens', C.c_int),
                ('memory_usage_mb', C.c_float)]


class RKLLMResult(C.Structure):
    _fields_ = [('text', C.c_char_p), ('token_id', C.c_int32),
                ('last_hidden_layer', _Hidden), ('logits', _Logits), ('perf', RKLLMPerfStat)]


CALLBACK = C.CFUNCTYPE(C.c_int, C.POINTER(RKLLMResult), C.c_void_p, C.c_int)


class RKLLMCallback(C.Structure):
    _fields_ = [('result_callback', CALLBACK), ('result_userdata', C.c_void_p),
                ('tokenizer_callback', C.c_void_p), ('tokenizer_userdata', C.c_void_p),
                ('embed_callback', C.c_void_p), ('embed_userdata', C.c_void_p)]
# -----------------------------------------------------------------------------

BIG_CORES = 0xF0  # RK3588: CPU4-7 are the Cortex-A76 cores.


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def file_sha256(path):
    """SHA-256 of the model file, cached next to it (hashing 5 GB takes a while)."""
    st = path.stat()
    cache = path.with_name(path.name + '.sha256.json')
    try:
        c = json.loads(cache.read_text())
        if c['size'] == st.st_size and c['mtime'] == st.st_mtime:
            return c['sha256']
    except (OSError, ValueError, KeyError):
        pass
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1 << 24), b''):
            h.update(block)
    try:
        cache.write_text(json.dumps({'size': st.st_size, 'mtime': st.st_mtime,
                                     'sha256': h.hexdigest()}))
    except OSError:
        pass
    return h.hexdigest()


class Runtime:
    def __init__(self, args):
        self.args = args
        self.lib = C.CDLL(str(args.lib))
        self.lib.rkllm_createDefaultParam.restype = RKLLMParam
        self.lib.rkllm_init.argtypes = [C.POINTER(C.c_void_p), C.POINTER(RKLLMParam),
                                        C.POINTER(RKLLMCallback)]
        self.lib.rkllm_run.argtypes = [C.c_void_p, C.POINTER(RKLLMInput),
                                       C.POINTER(RKLLMInferParam), C.c_void_p]
        self.lib.rkllm_destroy.argtypes = [C.c_void_p]
        self.handle = None
        self.loaded_at = None
        self.lock = threading.Lock()
        self.cb = CALLBACK(self._on_result)  # Keep a reference; C holds the pointer.
        self.callbacks = RKLLMCallback(result_callback=self.cb)
        self.out = None

    def _on_result(self, result, userdata, state):
        r = result.contents if result else None
        if state == RKLLM_RUN_NORMAL and r is not None and r.text:
            self.out['pieces'].append(r.text.decode('utf-8', errors='replace'))
            self.out['callbacks'] += 1
        elif state == RKLLM_RUN_FINISH and r is not None:
            p = r.perf
            self.out['perf'] = {'prefill_time_ms': p.prefill_time_ms,
                                'prefill_tokens': p.prefill_tokens,
                                'generate_time_ms': p.generate_time_ms,
                                'generate_tokens': p.generate_tokens,
                                'memory_usage_mb': p.memory_usage_mb}
        elif state == RKLLM_RUN_ERROR:
            self.out['error'] = 'RKLLM_RUN_ERROR'
        return 0

    def load(self):
        """-> load seconds (0 if already loaded)."""
        if self.handle is not None:
            return 0.0
        a = self.args
        p = self.lib.rkllm_createDefaultParam()
        p.model_path = str(a.model).encode()
        p.max_context_len = a.context
        p.max_new_tokens = a.max_new_tokens
        p.top_k, p.top_p, p.temperature = 1, 1.0, 1.0
        p.repeat_penalty = a.repeat_penalty
        p.frequency_penalty = 0.0
        p.presence_penalty = a.presence_penalty
        p.n_keep = -1
        p.skip_special_token = True
        p.is_async = False
        p.extend_param.base_domain_id = 0
        p.extend_param.embed_flash = 1
        p.extend_param.enabled_cpus_num = bin(a.cpu_mask).count('1')
        p.extend_param.enabled_cpus_mask = a.cpu_mask
        p.extend_param.n_batch = 1
        handle = C.c_void_p()
        start = time.perf_counter()
        ret = self.lib.rkllm_init(C.byref(handle), C.byref(p), C.byref(self.callbacks))
        if ret != 0:
            raise RuntimeError(f'rkllm_init failed ({ret})')
        self.handle, self.loaded_at = handle, utc_now()
        return time.perf_counter() - start

    def unload(self):
        with self.lock:
            if self.handle is not None:
                self.lib.rkllm_destroy(self.handle)
                self.handle = None

    def chat(self, prompt, max_new, think, presence_penalty):
        with self.lock:
            t0 = time.perf_counter()
            load_s = self.load()
            sp = RKLLMSamplingParam(top_k=1, top_p=1.0, temperature=1.0,
                                    repeat_penalty=self.args.repeat_penalty,
                                    frequency_penalty=0.0,
                                    presence_penalty=presence_penalty, mirostat=0,
                                    mirostat_tau=5.0, mirostat_eta=0.1)
            ip = RKLLMInferParam(mode=RKLLM_INFER_GENERATE, keep_history=0,
                                 max_new_tokens=max_new, sampling_params=C.pointer(sp))
            text = C.c_char_p(prompt.encode('utf-8'))
            inp = RKLLMInput(role=b'user', enable_thinking=think,
                             input_type=RKLLM_INPUT_PROMPT)
            inp.prompt_input = text
            self.out = {'pieces': [], 'callbacks': 0, 'perf': None, 'error': None}
            ret = self.lib.rkllm_run(self.handle, C.byref(inp), C.byref(ip), None)
            total_s = time.perf_counter() - t0
            out = self.out
        if ret != 0 or out['error']:
            raise RuntimeError(f'rkllm_run failed (ret={ret}, {out["error"]})')
        return ''.join(out['pieces']), out, load_s, total_s


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--model', type=Path, required=True, help='.rkllm file')
    ap.add_argument('--lib', type=Path, required=True, help='librkllmrt.so')
    ap.add_argument('--name', default='qwen3.5:4b-w8a8-npu', help='Tag the evaluator uses.')
    ap.add_argument('--port', type=int, default=11436)
    ap.add_argument('--context', type=int, default=16384, help='max_context_len')
    ap.add_argument('--max-new-tokens', type=int, default=4096,
                    help='Init-time cap; each request sets its own (num_predict).')
    ap.add_argument('--presence-penalty', type=float, default=1.5,
                    help='Default when a request does not set one (qwen3.5 Modelfile value).')
    ap.add_argument('--repeat-penalty', type=float, default=1.0)
    ap.add_argument('--cpu-mask', type=lambda s: int(s, 0), default=BIG_CORES)
    ap.add_argument('--source', default='', help='Where the .rkllm came from (recorded in /api/show).')
    args = ap.parse_args()
    args.model = args.model.expanduser().resolve()
    args.lib = args.lib.expanduser().resolve()

    print(f'Hashing {args.model.name} ...', flush=True)
    digest = file_sha256(args.model)
    lib_digest = file_sha256(args.lib)
    size = args.model.stat().st_size
    rt = Runtime(args)
    details = {'format': 'rkllm', 'family': 'qwen35', 'parameter_size': '4B',
               'quantization_level': 'w8a8', 'runner': 'rkllm-npu',
               'context_length': args.context}
    tag = {'name': args.name, 'model': args.name, 'size': size, 'digest': digest,
           'modified_at': datetime.fromtimestamp(args.model.stat().st_mtime,
                                                 timezone.utc).isoformat(),
           'details': details}
    version = {'version': 'rkllm-1.3.1', 'runtime': 'rkllm', 'librkllmrt_sha256': lib_digest,
               'rknpu_driver': Path('/sys/module/rknpu/version').read_text().strip()
               if Path('/sys/module/rknpu/version').exists() else None}

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

        def body(self):
            n = int(self.headers.get('Content-Length') or 0)
            return json.loads(self.rfile.read(n) or b'{}')

        def do_GET(self):
            if self.path == '/api/version':
                self.send(version)
            elif self.path == '/api/tags':
                self.send({'models': [tag]})
            elif self.path == '/api/ps':
                self.send({'models': [{**tag, 'size_vram': 0, 'loaded_at': rt.loaded_at}]
                           if rt.handle is not None else []})
            else:
                self.send({'error': 'not found'}, 404)

        def do_POST(self):
            try:
                req = self.body()
            except ValueError:
                return self.send({'error': 'bad json'}, 400)
            if self.path == '/api/show':
                return self.send({'details': details, 'model_info': {
                    'model_path': str(args.model), 'sha256': digest, 'source': args.source,
                    'librkllmrt': str(args.lib), **version},
                    'parameters': (f'top_k 1 (greedy)\npresence_penalty {args.presence_penalty}'
                                   f'\nrepeat_penalty {args.repeat_penalty}'
                                   f'\nmax_context_len {args.context}'
                                   f'\ncpu_mask {hex(args.cpu_mask)}')})
            if self.path == '/api/generate' and req.get('keep_alive') in (0, '0', '0s'):
                rt.unload()
                return self.send({'model': args.name, 'created_at': utc_now(),
                                  'response': '', 'done': True, 'done_reason': 'unload'})
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
            if float(opts.get('temperature', 0.0)) != 0.0:
                return self.send({'error': 'only greedy (temperature 0) is supported'}, 400)
            max_new = int(opts.get('num_predict', args.max_new_tokens))
            if max_new > args.max_new_tokens:
                return self.send({'error': f'num_predict > server --max-new-tokens'}, 400)
            try:
                answer, out, load_s, total_s = rt.chat(
                    msgs[0]['content'], max_new, bool(req.get('think', False)),
                    float(opts.get('presence_penalty', args.presence_penalty)))
            except Exception as exc:  # Report, never hide, a failed run.
                return self.send({'error': str(exc)}, 500)
            perf = out['perf'] or {}
            gen = perf.get('generate_tokens', out['callbacks'])
            self.send({
                'model': args.name, 'created_at': utc_now(),
                'message': {'role': 'assistant', 'content': answer},
                'done': True, 'done_reason': 'length' if gen >= max_new else 'stop',
                'total_duration': int(total_s * 1e9), 'load_duration': int(load_s * 1e9),
                'prompt_eval_count': perf.get('prefill_tokens', 0),
                'prompt_eval_duration': int(perf.get('prefill_time_ms', 0) * 1e6),
                'eval_count': gen,
                'eval_duration': int(perf.get('generate_time_ms', 0) * 1e6),
                'rkllm_perf': perf, 'rkllm_text_callbacks': out['callbacks'],
            })

    if args.port <= 0:
        raise SystemExit('bad port')
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'Serving {args.name} on http://127.0.0.1:{args.port} (sha256 {digest[:12]}...)',
          flush=True)
    try:
        server.serve_forever()
    finally:
        rt.unload()


if __name__ == '__main__':
    os.environ.setdefault('RKLLM_LOG_LEVEL', '1')  # Runtime prints version/perf lines.
    main()
