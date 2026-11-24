"""How the LLM software tells the power manager what it is doing.

Each program that runs AI work (the NPU server, the RAG pipeline, ...) writes its own
small file into STATE_DIR, named after itself:

    /run/pms/ai_state.d/rkllm_server   ->  "generate 1764000000.12"
    /run/pms/ai_state.d/rag            ->  "retrieve 1764000000.05"

The power manager reads all of them and uses the busiest state:
    prefill  > generate > retrieve > idle
    (reading     (writing    (searching    (nothing
     the prompt)  tokens)     documents)    running)

A busy state older than MAX_AGE_S counts as idle, so a program that crashes mid-answer
cannot hold the board at full power forever.

Writers never fail: if the folder is missing (power manager not installed), set_state
silently does nothing, so the LLM keeps working without the PMS.

Writer:
    from firmware.communication import ai_state
    ai_state.set_state("rkllm_server", "prefill")
    ...
    with ai_state.busy("rag", "retrieve"):
        search()
"""
import contextlib
import os
import time

STATE_DIR = os.environ.get("PMS_STATE_DIR", "/run/pms/ai_state.d")
STATES = ("idle", "retrieve", "generate", "prefill")      # lowest to highest priority
MAX_AGE_S = 900.0


def set_state(source, state, state_dir=None, now=None):
    """Record `state` for `source`. Returns True if written, False if the PMS folder is absent."""
    if state not in STATES:
        raise ValueError(f"unknown AI state {state!r}; use one of {STATES}")
    d = state_dir or STATE_DIR
    path = os.path.join(d, source)
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w") as f:
            f.write(f"{state} {time.time() if now is None else now:.3f}\n")
        os.replace(tmp, path)            # atomic: the reader never sees half a file
        return True
    except OSError:
        with contextlib.suppress(OSError):
            os.remove(tmp)
        return False


@contextlib.contextmanager
def busy(source, state, state_dir=None):
    """Hold `state` for the duration of a with-block, then go back to idle."""
    set_state(source, state, state_dir)
    try:
        yield
    finally:
        set_state(source, "idle", state_dir)


def read_states(state_dir=None, now=None, max_age_s=MAX_AGE_S):
    """{source: state} for every writer, with stale busy states reported as idle."""
    d = state_dir or STATE_DIR
    now = time.time() if now is None else now
    out = {}
    try:
        names = os.listdir(d)
    except OSError:
        return out
    for name in names:
        if name.endswith(".tmp"):
            continue
        try:
            with open(os.path.join(d, name)) as f:
                parts = f.read().split()
            state, stamp = parts[0], float(parts[1])
        except (OSError, IndexError, ValueError):
            continue
        if state not in STATES or (state != "idle" and now - stamp > max_age_s):
            state = "idle"
        out[name] = state
    return out


def current_state(state_dir=None, now=None, max_age_s=MAX_AGE_S):
    """The busiest state across all writers ('idle' if there are none)."""
    states = read_states(state_dir, now, max_age_s).values()
    return max(states, key=STATES.index, default="idle")
