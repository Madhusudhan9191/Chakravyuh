"""CHAKRA — dead-simple JSON persistence. No database to break at 2am."""
import json, os, threading

_LOCK = threading.Lock()
_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
_PATH = os.path.join(_DIR, "state.json")

_DEFAULT = {"invoices": [], "alerts": [], "graph": {"nodes": [], "edges": [], "rings": 0},
            "stopwatch_seconds": 0.0}


def load():
    with _LOCK:
        if not os.path.exists(_PATH):
            return json.loads(json.dumps(_DEFAULT))
        with open(_PATH) as f:
            return json.load(f)


def save(state):
    with _LOCK:
        os.makedirs(_DIR, exist_ok=True)
        tmp = _PATH + ".tmp"
        with open(tmp, "w") as f:
            json.dump(state, f, indent=1)
        os.replace(tmp, _PATH)


def reset():
    save(json.loads(json.dumps(_DEFAULT)))
    return load()
