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

Messages: a single user message (IFEval), or a system message then a user
message (the RAG pipeline, software/rag/rag.py). A system message is applied
with rkllm_set_chat_template in Qwen's ChatML layout, the layout Ollama's
qwen3.5 template renders (with the empty think block when thinking is off); a
request without one uses the model's built-in template (the model is reloaded
if a system template was set before). The .rkllm tokenizer counts a few percent
more tokens than Qwen's Hugging Face tokenizer on long RAG prompts, so
prompt_eval_count can be slightly above a client's own preflight count.

OpenAI-compatible endpoint (/v1/chat/completions, /v1/models) for clients such as
Qwen-Agent (software/knowledge_base), with --chat-template pointing at the model's
Hugging Face chat_template.jinja. Messages (system/user/assistant/tool, with tool
calls) and `tools` are rendered by that template, as transformers would, and run with
an empty RKLLM chat template so RKLLM adds nothing. Tool calls the model writes in its
XML format (<tool_call><function=...><parameter=...>) come back as OpenAI tool_calls
(finish_reason "tool_calls"), as Ollama returns them. Thinking follows Ollama's /v1
behaviour: on unless the request sends reasoning_effort "none". stream=true sends each
token as it is generated (server-sent events), holding back only text that may be the
start of a tool call, so a client's time-to-first-token is the real load + prefill
time; stream_options.include_usage adds a final usage chunk that also carries RKLLM's
perf counters (x_rkllm_perf).

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
import re
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


TOOL_OPEN = '<tool_call>'
TOOL_CALL_RE = re.compile(r'<tool_call>\s*<function=([^>\n]+)>(.*?)</function>\s*</tool_call>', re.S)
PARAM_RE = re.compile(r'<parameter=([^>\n]+)>\n?(.*?)\n?</parameter>', re.S)


class ChatTemplate:
    """The model's own Hugging Face chat template (chat_template.jinja), rendered the way
    transformers' apply_chat_template does, for /v1 requests (messages, tools, thinking)."""

    def __init__(self, path):
        import jinja2.ext
        from jinja2.sandbox import ImmutableSandboxedEnvironment

        def raise_exception(msg):
            raise ValueError(msg)

        def tojson(x, ensure_ascii=False, indent=None, separators=None, sort_keys=False):
            return json.dumps(x, ensure_ascii=ensure_ascii, indent=indent,
                              separators=separators, sort_keys=sort_keys)

        env = ImmutableSandboxedEnvironment(trim_blocks=True, lstrip_blocks=True,
                                            extensions=[jinja2.ext.loopcontrols])
        env.filters['tojson'] = tojson
        env.globals['raise_exception'] = raise_exception
        self.template = env.from_string(Path(path).read_text())

    def render(self, messages, tools, think):
        msgs = []
        for m in messages:
            m = dict(m)
            if m.get('role') == 'function':  # Legacy OpenAI name for a tool result.
                m['role'] = 'tool'
            calls = []
            for tc in m.get('tool_calls') or []:  # OpenAI sends arguments as a JSON string.
                fn = dict(tc.get('function') or {})
                if isinstance(fn.get('arguments'), str):
                    fn['arguments'] = json.loads(fn['arguments'] or '{}')
                calls.append({**tc, 'function': fn})
            if calls:
                m['tool_calls'] = calls
            msgs.append(m)
        return self.template.render(messages=msgs, tools=tools or None,
                                    add_generation_prompt=True, enable_thinking=think)


def parse_tool_calls(text, tools):
    """Qwen3.5's XML tool calls -> (content before the first call, OpenAI tool_calls)."""
    types = {t['function']['name']: (t['function'].get('parameters') or {}).get('properties', {})
             for t in tools or [] if t.get('type') == 'function'}
    calls = []
    for i, (name, body) in enumerate(TOOL_CALL_RE.findall(text)):
        name, args = name.strip(), {}
        for pname, value in PARAM_RE.findall(body):
            pname = pname.strip()
            if types.get(name, {}).get(pname, {}).get('type', 'string') != 'string':
                try:
                    value = json.loads(value)
                except ValueError:
                    pass
            args[pname] = value
        calls.append({'id': f'call_{time.time_ns()}_{i}', 'type': 'function',
                      'function': {'name': name, 'arguments': json.dumps(args, ensure_ascii=False)}})
    content = text.split(TOOL_OPEN)[0].strip() if calls else text
    return content, calls


def held_back(text):
    """Length of the tail of `text` that could be the start of '<tool_call>' (not sent yet)."""
    for n in range(min(len(TOOL_OPEN) - 1, len(text)), 0, -1):
        if TOOL_OPEN.startswith(text[-n:]):
            return n
    return 0


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
        self.lib.rkllm_set_chat_template.argtypes = [C.c_void_p, C.c_char_p, C.c_char_p,
                                                     C.c_char_p]
        self.handle = None
        self.template = None  # None = the model's built-in chat template.
        self.loaded_at = None
        self.lock = threading.Lock()
        self.cb = CALLBACK(self._on_result)  # Keep a reference; C holds the pointer.
        self.callbacks = RKLLMCallback(result_callback=self.cb)
        self.out = None

    def _on_result(self, result, userdata, state):
        r = result.contents if result else None
        if state == RKLLM_RUN_NORMAL and r is not None and r.text:
            piece = r.text.decode('utf-8', errors='replace')
            self.out['pieces'].append(piece)
            self.out['callbacks'] += 1
            sink = self.out.get('sink')
            if sink is not None:
                try:
                    sink(piece)  # Streaming client: send the token now.
                except OSError:
                    self.out['sink'] = None  # Client went away; finish the run quietly.
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
        self.template = None
        return time.perf_counter() - start

    def _destroy(self):
        if self.handle is not None:
            self.lib.rkllm_destroy(self.handle)
            self.handle = None

    def unload(self):
        with self.lock:
            self._destroy()

    def _use_system(self, system, think):
        """Apply a system prompt (ChatML), or go back to the built-in template.

        A custom template turns off RKLLM's own enable_thinking handling, so with
        thinking off the postfix carries the empty think block that the built-in
        template (and Ollama's qwen3.5 renderer) would add.
        """
        if system is None:
            if self.template is not None:
                self._destroy()  # The built-in template can only be restored by reloading.
            return
        want = (f'<|im_start|>system\n{system}<|im_end|>\n', '<|im_start|>user\n',
                '<|im_end|>\n<|im_start|>assistant\n' + ('' if think else '<think>\n\n</think>\n\n'))
        if want != self.template:
            ret = self.lib.rkllm_set_chat_template(self.handle, *(w.encode() for w in want))
            if ret != 0:
                raise RuntimeError(f'rkllm_set_chat_template failed ({ret})')
            self.template = want

    def _use_raw(self):
        """Empty template: the prompt is already fully rendered ChatML (/v1 requests)."""
        want = ('', '', '')
        if want != self.template:
            ret = self.lib.rkllm_set_chat_template(self.handle, b'', b'', b'')
            if ret != 0:
                raise RuntimeError(f'rkllm_set_chat_template failed ({ret})')
            self.template = want

    def chat(self, prompt, max_new, think, presence_penalty, system=None, raw=False, sink=None):
        """raw=True: `prompt` is a complete ChatML prompt (system/think ignored).
        sink: called with each generated piece as it arrives (streaming)."""
        with self.lock:
            t0 = time.perf_counter()
            if not raw and system is None and self.template is not None:
                self._use_system(None, think)
            load_s = self.load()
            if raw:
                self._use_raw()
            elif system is not None:
                self._use_system(system, think)
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
            self.out = {'pieces': [], 'callbacks': 0, 'perf': None, 'error': None, 'sink': sink}
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
    ap.add_argument('--chat-template', type=Path, default=None,
                    help="The model's Hugging Face chat_template.jinja; needed for /v1 requests.")
    args = ap.parse_args()
    args.model = args.model.expanduser().resolve()
    args.lib = args.lib.expanduser().resolve()

    print(f'Hashing {args.model.name} ...', flush=True)
    digest = file_sha256(args.model)
    lib_digest = file_sha256(args.lib)
    size = args.model.stat().st_size
    rt = Runtime(args)
    template = ChatTemplate(args.chat_template.expanduser()) if args.chat_template else None
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
            elif self.path == '/v1/models':
                self.send({'object': 'list', 'data': [{'id': args.name, 'object': 'model',
                                                       'owned_by': 'rkllm'}]})
            else:
                self.send({'error': 'not found'}, 404)

        def openai_chat(self, req):
            """POST /v1/chat/completions (OpenAI format), streamed or not."""
            if req.get('model') != args.name:
                return self.send({'error': {'message': f"model '{req.get('model')}' not found"}},
                                 404)
            if float(req.get('temperature') or 0.0) != 0.0:
                return self.send({'error': {'message': 'only greedy (temperature 0) is supported'}},
                                 400)
            if template is None:
                return self.send({'error': {'message': 'start the server with --chat-template '
                                            'for /v1 requests'}}, 400)
            think = req.get('reasoning_effort', 'medium') != 'none'
            tools = req.get('tools') or None
            try:
                prompt = template.render(req.get('messages') or [], tools, think)
            except (ValueError, TypeError) as exc:
                return self.send({'error': {'message': f'bad messages: {exc}'}}, 400)
            max_new = int(req.get('max_tokens') or req.get('max_completion_tokens')
                          or args.max_new_tokens)
            if max_new > args.max_new_tokens:
                return self.send({'error': {'message': 'max_tokens > server --max-new-tokens'}},
                                 400)
            cid, created = f'chatcmpl-{time.time_ns()}', int(time.time())
            stream = bool(req.get('stream'))
            sink = None
            if stream:
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Cache-Control', 'no-cache')
                self.end_headers()  # HTTP/1.0: the stream ends when the connection closes.

                def event(obj):
                    self.wfile.write(b'data: ' + json.dumps(obj).encode() + b'\n\n')
                    self.wfile.flush()

                def chunk(delta, finish=None):
                    return {'id': cid, 'object': 'chat.completion.chunk', 'created': created,
                            'model': args.name,
                            'choices': [{'index': 0, 'delta': delta, 'finish_reason': finish}]}

                # Stream text as it is generated, but (with tools) hold back anything that
                # may be the start of a tool call; once '<tool_call>' appears, stop
                # streaming text and return the parsed calls at the end, as Ollama does.
                st = {'acc': '', 'sent': 0, 'role': False, 'tool': False}

                def emit(text):
                    if text:
                        delta = {'content': text}
                        if not st['role']:
                            delta['role'], st['role'] = 'assistant', True
                        event(chunk(delta))

                def sink(piece):
                    st['acc'] += piece
                    if st['tool']:
                        return
                    if tools and TOOL_OPEN in st['acc']:
                        st['tool'] = True
                        emit(st['acc'][st['sent']:st['acc'].index(TOOL_OPEN)].rstrip())
                        return
                    end = len(st['acc']) - (held_back(st['acc']) if tools else 0)
                    emit(st['acc'][st['sent']:end])
                    st['sent'] = max(st['sent'], end)
            try:
                answer, out, load_s, total_s = rt.chat(
                    prompt, max_new, think, float(req.get('presence_penalty')
                                                  or args.presence_penalty),
                    raw=True, sink=sink)
            except Exception as exc:  # Report, never hide, a failed run.
                if stream:
                    event({'error': {'message': str(exc)}})
                    return
                return self.send({'error': {'message': str(exc)}}, 500)
            perf = out['perf'] or {}
            gen = perf.get('generate_tokens', out['callbacks'])
            finish = 'length' if gen >= max_new - 1 else 'stop'
            content, calls = parse_tool_calls(answer, tools) if tools else (answer, [])
            if calls:
                finish = 'tool_calls'
            usage = {'prompt_tokens': perf.get('prefill_tokens', 0), 'completion_tokens': gen,
                     'total_tokens': perf.get('prefill_tokens', 0) + gen,
                     'x_rkllm_perf': perf, 'x_load_s': round(load_s, 3),
                     'x_total_s': round(total_s, 3)}
            if stream:
                if not st['tool']:
                    emit(st['acc'][st['sent']:])  # Flush any held-back tail.
                if calls:
                    event(chunk({**({} if st['role'] else {'role': 'assistant'}),
                                 'tool_calls': [{'index': i, **c} for i, c in enumerate(calls)]}))
                elif st['tool']:
                    emit(st['acc'][st['acc'].index(TOOL_OPEN):])  # Unparseable: pass it on.
                event(chunk({}, finish))
                if (req.get('stream_options') or {}).get('include_usage'):
                    event({'id': cid, 'object': 'chat.completion.chunk', 'created': created,
                           'model': args.name, 'choices': [], 'usage': usage})
                self.wfile.write(b'data: [DONE]\n\n')
                self.wfile.flush()
                return
            self.send({'id': cid, 'object': 'chat.completion', 'created': created,
                       'model': args.name,
                       'choices': [{'index': 0, 'finish_reason': finish,
                                    'message': {'role': 'assistant', 'content': content,
                                                **({'tool_calls': calls} if calls else {})}}],
                       'usage': usage})

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
            if self.path == '/v1/chat/completions':
                return self.openai_chat(req)
            if self.path == '/api/generate' and req.get('keep_alive') in (0, '0', '0s'):
                rt.unload()
                return self.send({'model': args.name, 'created_at': utc_now(),
                                  'response': '', 'done': True, 'done_reason': 'unload'})
            if self.path != '/api/chat':
                return self.send({'error': 'not found'}, 404)
            if req.get('model') != args.name:
                return self.send({'error': f"model '{req.get('model')}' not found"}, 404)
            msgs = req.get('messages') or []
            roles = [m.get('role') for m in msgs]
            if roles not in (['user'], ['system', 'user']):
                return self.send({'error': 'only [user] or [system, user] messages are supported'},
                                 400)
            system = msgs[0]['content'] if roles[0] == 'system' else None
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
                    msgs[-1]['content'], max_new, bool(req.get('think', False)),
                    float(opts.get('presence_penalty', args.presence_penalty)), system)
            except Exception as exc:  # Report, never hide, a failed run.
                return self.send({'error': str(exc)}, 500)
            perf = out['perf'] or {}
            gen = perf.get('generate_tokens', out['callbacks'])
            self.send({
                'model': args.name, 'created_at': utc_now(),
                'message': {'role': 'assistant', 'content': answer},
                # RKLLM's generate_tokens stops one short of max_new_tokens when the cap
                # is hit (seen as 511 of 512 in the RAG runs), so treat max_new - 1 as the cap.
                'done': True, 'done_reason': 'length' if gen >= max_new - 1 else 'stop',
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
