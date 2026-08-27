"""
CHAKRA — Gemma client (OpenAI-compatible, LM Studio / any local server).

Gemma does exactly two jobs in CHAKRA and never decides anything:
  READ : extract structured fields from an invoice photo (vision)
  WRITE: draft compliance paperwork from deterministic evidence (text)

Battle-tested details from pre-event testing (disclosed prior work):
  - json_schema response_format kills thinking-mode derailment; falls back
    to free-form if the server rejects it (HTTP 400/422)
  - retries on non-JSON replies; strips <think> blocks and code fences
  - no max_tokens cap (caps truncate thinking models mid-reasoning)
"""
import base64, json, os, re, time, urllib.request, urllib.error

BASE_URL = os.environ.get("CHAKRA_LLM_URL", "http://localhost:1234/v1").rstrip("/")
MODEL = os.environ.get("CHAKRA_LLM_MODEL", "")  # empty = auto-detect first gemma
API_KEY = os.environ.get("CHAKRA_LLM_KEY", "")


def _post(path, body, timeout=600):
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    req = urllib.request.Request(BASE_URL + path, data=json.dumps(body).encode(),
                                 headers=headers)
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r), time.time() - t0


def _get(path, timeout=5):
    headers = {"Authorization": f"Bearer {API_KEY}"} if API_KEY else {}
    req = urllib.request.Request(BASE_URL + path, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def status():
    """Returns (connected: bool, model_name: str, latency_ms: int)."""
    t0 = time.time()
    try:
        data = _get("/models")
        ms = int((time.time() - t0) * 1000)
        names = [m.get("id", "") for m in data.get("data", [])]
        gemmas = [n for n in names if "gemma" in n.lower()]
        return True, (MODEL or (gemmas[0] if gemmas else (names[0] if names else "unknown"))), ms
    except Exception:
        return False, "offline", 0


def _model_name():
    if MODEL:
        return MODEL
    ok, name, _ = status()
    return name if ok else "local-model"


def _strip(content):
    content = re.sub(r"<think>.*?</think>", "", content or "", flags=re.S)
    s = content.strip()
    s = re.sub(r"^```(json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    if not s.startswith("{"):
        m = re.search(r"\{.*\}", s, re.S)
        if m:
            s = m.group(0)
    return s


def generate_json(prompt, image_path=None, schema=None, retries=2):
    """Vision or text call that must return a JSON object. Returns (dict, seconds)."""
    content = [{"type": "text", "text": prompt}]
    if image_path:
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        content.append({"type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
    use_schema = schema is not None
    last_err, last_raw, total = None, "", 0.0
    for attempt in range(retries + 1):
        body = {"model": _model_name(),
                "messages": [{"role": "user", "content": content}],
                "temperature": 0}
        if use_schema:
            body["response_format"] = {"type": "json_schema", "json_schema": {
                "name": "chakra", "strict": True, "schema": schema}}
        try:
            resp, dt = _post("/chat/completions", body)
        except urllib.error.HTTPError as e:
            if use_schema and e.code in (400, 422):
                use_schema = False
                continue
            raise
        total += dt
        msg = resp["choices"][0]["message"]
        raw = msg.get("content") or msg.get("reasoning_content") or ""
        try:
            return json.loads(_strip(raw)), total
        except json.JSONDecodeError as e:
            last_err, last_raw = e, raw
    raise RuntimeError(f"Gemma never returned valid JSON. Last reply: {last_raw[:300]!r} ({last_err})")


def generate_text(prompt, system=None):
    """Plain text generation (Action Engine drafts). Returns (text, seconds)."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    body = {"model": _model_name(), "messages": messages, "temperature": 0.2}
    resp, dt = _post("/chat/completions", body)
    msg = resp["choices"][0]["message"]
    text = msg.get("content") or ""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    return text, dt 
