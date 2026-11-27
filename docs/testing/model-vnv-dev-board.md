# Model V&V: Dev Board (qwen3.5:4b)

Verification and validation plan for running the candidate model on the dev board. It carries out step 1 of the [laptop results' next steps](model-evaluation-results.md#next-steps), using the method in [model-evaluation.md](model-evaluation.md). Results are in [RockLocalCPUOnly.md](RockLocalCPUOnly.md).

- **Verification** asks whether the evaluation was run correctly on the board: right software, right weights, no errors, complete logs, results repeatable.
- **Validation** asks whether the model is fit for the device: accuracy, speed, memory and thermal behaviour on hardware close to the target.

## Scope

| Item | In scope |
|---|---|
| Model | `qwen3.5:4b` (Q4_K_M, 4.2B parameters, Ollama ID `d8b0f5e9760c`), thinking off |
| Benchmark | IFEval, first 20 prompts (same prompts as the laptop battery screen) |
| Not in scope yet | `qwen3:4b-instruct-2507` and `qwen3:8b` on the board, the 100-prompt screen, thinking mode, energy |

## Test article and environment

| Item | Value |
|---|---|
| Board | Radxa ROCK 5T, Rockchip RK3588 (4× Cortex-A76 at 2.3 GHz + 4× Cortex-A55 at 1.8 GHz), 12 GB LPDDR, eMMC/SD root (57 GB) |
| OS | Debian 12, Linux 6.1 (Rockchip BSP), aarch64 |
| Cooling | Board heatsink with PWM fan (`pwmfan`), CPU governor `ondemand` |
| Inference | CPU only (the RK3588 NPU is not used by Ollama) |
| Ollama | 0.40.3 (same as the laptop), native arm64 build run as user `radxa` from `~/.local/ollama-0.40.3`, on `127.0.0.1:11435` |
| Python | 3.11 venv (`.venv`) with `lm_eval[ifeval]` 0.4.13, `requests`, `nltk`, `psutil` |
| Monitor | `monitor_resources.py --container ""` (native process RAM/CPU via psutil), plus SoC/CPU temperature and lowest CPU-cluster clock, sampled once a second |

Differences from the laptop setup, and why:

- **Port 11435, not 11434.** A separate root-owned Ollama 0.40.16 was already serving on 11434 before this work started. It was left running, idle, and not used. The tests use 0.40.3 to match the laptop.
- **No `setup_board.sh`.** It needs sudo to install the systemd service. The same release (0.40.3, `ollama-linux-arm64.tar.zst`) was unpacked into the user's home instead. The weight ID check from that script is done by hand (V-02).
- **No energy figures.** The board has no battery, and its USB-C power-delivery sensor (`tcpm-source-psy`) reads 0 V / 0 A. Energy needs an external USB-C meter (see the plan's open items).
- **Desktop session running.** The board is used through its KDE desktop and VS Code, so these stay open during the run. That costs some RAM and CPU and is recorded in the starting RAM figure.

## Verification

| ID | Check | Method | Pass criterion |
|---|---|---|---|
| V-01 | Ollama version matches the laptop | `GET /api/version` on the test server; `manifest.json` | `0.40.3` |
| V-02 | Same weights as the laptop | `ollama list` ID; digest in `manifest.json` | ID `d8b0f5e9760c` |
| V-03 | Same harness and settings | `manifest.json`, `requirements-frozen.txt` | lm_eval 0.4.13, greedy, seed 42, 16k context, thinking off, first 20 IFEval prompts |
| V-04 | Run completed without errors | Evaluator output | `Results saved to ...` printed; no failed request, context overflow or thinking output |
| V-05 | No truncated answers | `analysis.json` | `truncated_answers` = 0 |
| V-06 | Resource log complete | `resources_*.csv` | About 1 row per second over the window; no gaps over 5 s; no `unreachable` model entries |
| V-07 | Model was actually loaded | `analysis.json` | Peak Ollama memory well above starting memory (> 2 GB increase) |
| V-08 | Local only | Evaluator URL check; `HF_HUB_OFFLINE=1`, `HF_DATASETS_OFFLINE=1` during the run | Loopback server only; harness ran offline from the cached dataset |
| V-09 | Repeatable | Rerun the first 5 prompts on the board and compare answer text with the 20-prompt run | All 5 answers identical |

V-09 replaces the plan's laptop-versus-AC comparison: the laptop's raw `requests.jsonl` files are not on the board, so answers cannot be compared across machines yet. Copying those files over would allow a cross-machine check (same weights and seed, but a different CPU, so small differences are possible).

## Validation

There is no requirements document yet (`docs/requirements/` is empty), so the criteria below are **proposed working targets** for the team to confirm. They are based on the README's design goals and the laptop results.

| ID | Measure | Proposed target | Basis |
|---|---|---|---|
| VAL-01 | IFEval prompt-level strict, 20 prompts | Within noise of the laptop's 85% (≥ 70%, i.e. ≥ 14/20) | Same weights and settings should give similar accuracy. ±18 points is the 20-prompt noise in the plan |
| VAL-02 | Generation speed | ≥ 3 tokens/s; report against the laptop's 4.36 | Usable interactive speed for a 3B–7B plug-in |
| VAL-03 | Average seconds per answer | Report; compare with the laptop's 63.2 s | Responsiveness |
| VAL-04 | Peak Ollama process memory | ≤ 8 GB, leaving headroom on a 12 GB board | Memory is a main device constraint (README) |
| VAL-05 | Thermal | Peak SoC temperature < 85 °C, and no sustained clock drop on the A76 clusters | The plug-in must sustain inference without throttling (README thermal goals) |
| VAL-06 | Offline operation | Inference needs no network (V-08) | README "Offline operation" and "Privacy" goals |

## Procedure

Run from the repository root with the venv active (`source .venv/bin/activate`).

1. **Before the session:** close heavy apps; check that the model isn't loaded (`curl -s http://127.0.0.1:11435/api/ps`); let the board idle for a few minutes so the SoC is near its idle temperature.
2. **Offline mode:**
   ```bash
   export HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1
   ```
   (Download the IFEval dataset once beforehand with offline mode off.)
3. **Run 20 prompts:**
   ```bash
   python models/monitor_resources.py --container "" --base-url http://127.0.0.1:11435 -- \
     python models/evaluate_ollama.py --models qwen3.5:4b --limit 20 \
     --base-url http://127.0.0.1:11435 > benchmark_results/board_run.log 2>&1
   ```
4. **Analyze:** `python models/analyze_run.py benchmark_results/<run folder>`
5. **Repeatability (V-09):** repeat step 3 with `--limit 5` and compare the `message.content` of each answer with the matching answer from step 3.
6. **Record** the results against every V and VAL item in [RockLocalCPUOnly.md](RockLocalCPUOnly.md).

## Limitations

- **20 prompts** give only a rough accuracy check (about ±18 points). Model ranking needs the 100-prompt screen.
- **Native process memory** is the sum of the Ollama processes' RSS (`psutil`). That is not the same measure as the laptop's `docker stats` container memory, so compare the two with care.
- **The board is not the final device.** It is closer than the laptop (an ARM SoC with LPDDR and passive/fan cooling), but the final processing unit, memory and cooling are not chosen yet.
- **No NPU.** The RK3588's 6 TOPS NPU is not used by Ollama. An NPU runtime (e.g. RKLLM) could change speed and power a lot and is worth a separate test.
