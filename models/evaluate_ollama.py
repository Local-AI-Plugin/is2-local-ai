#!/usr/bin/env python3
"""Public-benchmark runner for an existing local Ollama server.

Install (Python 3.11+ recommended):
  python -m pip install 'lm_eval[ifeval]' requests nltk
  python -m nltk.downloader punkt punkt_tab averaged_perceptron_tagger_eng
Smoke test:
  python models/evaluate_ollama.py --tasks ifeval --limit 5
Full IFEval: omit --limit. Limits apply PER TASK, not to the whole suite.
Uses lm-evaluation-harness prompts/scorers with Ollama chat wrapping. This
is a local chat-based evaluation configuration, not an exact reproduction
of model-card scores. No RAG, no tools, no answer-key feedback or retries.
Task defaults control few-shot examples, generation budget, and stop strings.
Thinking is disabled by default. Task-requested textual reasoning (e.g.
MMLU-Pro CoT) can still occur in the answer. --think enables thinking with
Qwen's recommended sampling (greedy decoding can loop while thinking) and adds
--think-budget tokens to each task's generation budget; only the final answer
is scored. Non-thinking-only models (instruct-2507) refuse --think.
Run from the host/WSL, outside Docker.
Initial dependency/dataset downloads need internet; inference stays local.
"""
import argparse
import importlib.metadata
import json
import platform
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from lm_eval import evaluator
from lm_eval.api.model import LM

MODELS = ['qwen3.5:4b', 'qwen3:4b-instruct-2507-q4_K_M', 'qwen3:8b']
# Qwen's recommended thinking-mode sampling. Seeded, so runs still repeat.
THINK_SAMPLING = {'temperature': 0.6, 'top_p': 0.95, 'top_k': 20, 'min_p': 0.0}

def save_json(path, data):
    path.write_text(json.dumps(data, indent=2, default=str), encoding='utf-8')

def can_think(model):
    # Ollama lists 'thinking' for instruct-2507 too, so its capabilities
    # field can't be trusted here; the 2507 instruct release never thinks.
    return 'instruct-2507' not in model

class OllamaLM(LM):
    def __init__(self, model, base_url, context, log_path, think=False, think_budget=0):
        super().__init__()
        self.model = model
        self.base_url = base_url.rstrip('/')
        self.context = context
        self.log_path = log_path
        self.think = think
        self.think_budget = think_budget
        self.session = requests.Session()

    def loglikelihood(self, requests):
        raise NotImplementedError('Use a generation-based task; this adapter has no logprobs.')

    def loglikelihood_rolling(self, requests):
        raise NotImplementedError('Perplexity is not supported by this adapter.')

    def generate_until(self, requests):
        outputs = []
        for request in requests:
            prompt, kwargs = request.args
            stops = kwargs.get('until') or []
            if isinstance(stops, str):
                stops = [stops]
            stops = [s for s in stops if s]
            budget = int(kwargs.get('max_gen_toks', 2048))
            if self.think:
                budget += self.think_budget  # Thinking tokens count against num_predict.
            if budget >= self.context:
                raise ValueError('Generation budget must be smaller than context.')
            options = {'num_ctx': self.context, 'num_predict': budget,
                       'temperature': float(kwargs.get('temperature', 0.0)),
                       'seed': 42, 'stop': stops}
            if self.think:
                options.update(THINK_SAMPLING)
            payload = {
                'model': self.model,
                'messages': [{'role': 'user', 'content': prompt}],
                'stream': False,
                'keep_alive': '10m',
                'options': options,
            }
            if can_think(self.model):
                payload['think'] = self.think
            start = time.perf_counter()
            try:
                # CPU inference can run ~1 token/s; scale the read timeout.
                response = self.session.post(self.base_url + '/api/chat', json=payload,
                                             timeout=(10, max(1800, 600 + budget)))
                response.raise_for_status()
                data = response.json()
                if data.get('error'):
                    raise RuntimeError(data['error'])
                answer = data['message']['content']
                if not isinstance(answer, str):
                    raise ValueError('Missing text answer')
            except Exception as exc:
                with self.log_path.open('a', encoding='utf-8') as f:
                    f.write(json.dumps({'request': payload, 'error': str(exc)}) + '\n')
                raise  # Never silently drop errors or turn them into wrong answers.
            record = {'task': getattr(request, 'task_name', None),
                      'doc_id': getattr(request, 'doc_id', None),
                      'request': payload, 'response': data,
                      'wall_seconds': time.perf_counter() - start}
            with self.log_path.open('a', encoding='utf-8') as f:
                f.write(json.dumps(record, default=str) + '\n')
            # Saturation is a warning sign; Ollama does not expose a complete
            # pre-truncation token count through this call. Inspect long inputs.
            if data.get('prompt_eval_count', 0) >= self.context - budget:
                raise RuntimeError('Context headroom exhausted. Increase --context '
                                   'and rerun all models using that setting.')
            # A server or template that ignores think=false, or thinking left
            # in the answer text, would be scored as part of the answer.
            if '<think>' in answer or (not self.think and data['message'].get('thinking')):
                raise RuntimeError('Thinking output found in a response; see the logged '
                                   'response. Check the model template and Ollama version.')
            if data.get('done_reason') == 'length':
                print('WARNING: output budget reached; inspect logged response.', flush=True)
            for stop in stops:
                answer = answer.split(stop, 1)[0]
            outputs.append(answer)
        return outputs

def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--models', nargs='+', default=MODELS)
    parser.add_argument('--tasks', nargs='+', default=['ifeval'])
    parser.add_argument('--limit', type=int, default=None,
                        help='First N examples PER task; screening only.')
    parser.add_argument('--context', type=int, default=16384)
    parser.add_argument('--base-url', default='http://127.0.0.1:11434')
    parser.add_argument('--out', default='benchmark_results')
    parser.add_argument('--think', action='store_true',
                        help='Enable thinking mode (hybrid models only).')
    parser.add_argument('--think-budget', type=int, default=4096,
                        help='Extra tokens per answer for thinking (with --think).')
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error('--limit must be positive')
    if args.context < 4096:
        parser.error('--context must be at least 4096')
    if urlparse(args.base_url).hostname not in ('localhost', '127.0.0.1', '::1'):
        parser.error('This starter permits only a loopback/local Ollama server.')
    if args.think and not all(can_think(m) for m in args.models):
        parser.error('--think given for a non-thinking model: '
                     + ', '.join(m for m in args.models if not can_think(m)))
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    root = Path(args.out) / (stamp + ('_think' if args.think else ''))
    root.mkdir(parents=True)
    def get(path):
        r = requests.get(args.base_url.rstrip('/') + path, timeout=15)
        r.raise_for_status()
        return r.json()
    tags = get('/api/tags')
    available = {m['name'] for m in tags['models']}
    missing = set(args.models) - available
    if missing:
        raise SystemExit('Download these exact tags first: ' + ', '.join(sorted(missing)))
    save_json(root / 'manifest.json', {
        'settings': vars(args), 'platform': platform.platform(),
        'python': platform.python_version(), 'ollama': get('/api/version'),
        'model_tags_and_digests': tags,
        'harness_version': importlib.metadata.version('lm_eval'),
        'protocol': 'Harness task prompts as one user message; Ollama template; '
                    + (f'thinking on (+{args.think_budget} tokens, {THINK_SAMPLING})'
                       if args.think else 'thinking off'),
        'note': 'Latency includes model loading when cold. Not TTFT or RAM measurement.'})
    freeze = subprocess.run([__import__('sys').executable, '-m', 'pip', 'freeze'],
                            capture_output=True, text=True, check=True)
    (root / 'requirements-frozen.txt').write_text(freeze.stdout, encoding='utf-8')
    for model in args.models:
        folder = root / re.sub(r'[^a-zA-Z0-9._-]', '_', model)
        folder.mkdir()
        r = requests.post(args.base_url.rstrip('/') + '/api/show',
                          json={'model': model}, timeout=30)
        r.raise_for_status()
        save_json(folder / 'model_details.json', r.json())
        print(f'Running {model}: {args.tasks}', flush=True)
        result = evaluator.simple_evaluate(
            model=OllamaLM(model, args.base_url, args.context, folder / 'requests.jsonl',
                           think=args.think, think_budget=args.think_budget),
            tasks=args.tasks, limit=args.limit, batch_size=1,
            log_samples=True, bootstrap_iters=0,
            random_seed=42, numpy_random_seed=42, torch_random_seed=42,
            fewshot_random_seed=42,
        )
        save_json(folder / 'results.json', result)
        print(json.dumps(result['results'], indent=2, default=str), flush=True)
        r = requests.post(args.base_url.rstrip('/') + '/api/generate',
                          json={'model': model, 'keep_alive': 0}, timeout=120)
        r.raise_for_status()
    print(f'Results saved to {root.resolve()}')

if __name__ == '__main__':
    main()
