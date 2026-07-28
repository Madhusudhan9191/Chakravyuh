"""
CHAKRA — server. Run:  python server.py   → http://localhost:8000

Design notes:
  - The frontend uploads files one-by-one with its own concurrency (default 4),
    matching LM Studio's parallel slots — so the browser IS the progress bar.
  - /api/demo?mode=instant loads pre-extracted results (the rehearsal hotkey);
    mode=live pushes the bundled demo photos through the real pipeline.
  - Single self-contained ui/index.html. No build step. Works in aeroplane mode.
"""
import os, threading, time, uuid

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, JSONResponse

import actions, extraction, gemma, rules, store

BASE = os.path.dirname(os.path.abspath(__file__))
UPLOADS = os.path.join(BASE, "uploads")
DEMO = os.path.join(BASE, "demo")
UI = os.path.join(BASE, "ui", "index.html")
os.makedirs(UPLOADS, exist_ok=True)

app = FastAPI(title="CHAKRA")
_EVAL_LOCK = threading.Lock()

# manual-review time a CA spends per document + per critical finding (stated
# assumptions for the hero numbers; adjust after the CA call)
MIN_PER_INVOICE = 12
HRS_PER_CRITICAL = 2.5


def _stats(state):
    n = len(state["invoices"])
    crit = sum(1 for a in state["alerts"] if a["severity"] == "CRITICAL" and a["status"] != "DISMISSED")
    protected = sum(a["impact"] for a in state["alerts"] if a["status"] != "DISMISSED")
    clean = len({inv["fields"].get("buyer_gstin") for inv in state["invoices"]}) - \
        len({e["gstin"] for a in state["alerts"] for e in a.get("entities", [])})
    return {
        "invoices": n,
        "alerts_open": sum(1 for a in state["alerts"] if a["status"] == "OPEN"),
        "critical": crit,
        "rupees_protected": round(protected, 2),
        "hours_saved": round((n * MIN_PER_INVOICE) / 60 + crit * HRS_PER_CRITICAL, 1),
        "stopwatch_seconds": round(state.get("stopwatch_seconds", 0.0), 1),
        "clean_parties": max(clean, 0),
    }


@app.get("/")
def index():
    return FileResponse(UI)


@app.get("/api/status")
def status():
    ok, model, ms = gemma.status()
    return {"gemma_connected": ok, "model": model, "latency_ms": ms,
            "provider": "LM Studio (local)" if ok else "offline"}


@app.get("/api/verify-gstin/{gstin}")
def verify_gstin(gstin: str):
    """Verify GSTIN structure and Modulo-36 checksum."""
    raw = gstin.strip().upper()
    fixed = extraction.gstin_structural_fix(raw)
    valid = extraction.gstin_valid(fixed)
    return {
        "raw_gstin": raw,
        "fixed_gstin": fixed,
        "is_valid": valid,
        "state_code": fixed[:2] if len(fixed) >= 2 else None,
        "pan": fixed[2:12] if len(fixed) >= 12 else None
    }


@app.get("/api/state")
def get_state():
    state = store.load()
    return {"stats": _stats(state), "alerts": state["alerts"],
            "graph": state["graph"], "invoices": [
                {"id": i["id"], "file": i["file"],
                 "seller": i["fields"].get("seller_name"),
                 "buyer": i["fields"].get("buyer_name"),
                 "total": i["fields"].get("total"),
                 "review": i.get("review", []),
                 "receipts": i.get("receipts", []),
                 "timings": i.get("timings", {})}
                for i in state["invoices"]]}


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    """One document in → extraction + trust layer → stored. Frontend fans out."""
    inv_id = "inv_" + uuid.uuid4().hex[:8]
    ext = os.path.splitext(file.filename or "doc.jpg")[1].lower() or ".jpg"
    path = os.path.join(UPLOADS, inv_id + ext)
    with open(path, "wb") as f:
        f.write(await file.read())
    t0 = time.time()
    try:
        result = extraction.extract(path)
    except Exception as e:
        raise HTTPException(502, f"Gemma extraction failed: {e}")
    elapsed = time.time() - t0
    inv = {"id": inv_id, "file": file.filename, "path": path, **result}
    state = store.load()
    state["invoices"].append(inv)
    state["stopwatch_seconds"] = state.get("stopwatch_seconds", 0.0) + elapsed
    store.save(state)
    return {"id": inv_id, "fields": result["fields"], "receipts": result["receipts"],
            "review": result["review"], "seconds": round(elapsed, 1)}


@app.post("/api/evaluate")
def evaluate():
    """Run the deterministic decision layer over everything ingested."""
    with _EVAL_LOCK:
        state = store.load()
        keep = {a["id"]: a for a in state["alerts"]}
        alerts, graph = rules.evaluate(state["invoices"])
        # preserve statuses/drafts across re-evaluations (match on rule+entity)
        old_by_key = {(a["rule"], a["entity"]): a for a in keep.values()}
        for a in alerts:
            old = old_by_key.get((a["rule"], a["entity"]))
            if old:
                a["status"] = old["status"]
                if "drafts" in old:
                    a["drafts"] = old["drafts"]
        state["alerts"], state["graph"] = alerts, graph
        store.save(state)
    return {"stats": _stats(state), "alerts": alerts, "graph": graph}


@app.post("/api/alerts/{alert_id}/drafts")
def make_drafts(alert_id: str):
    state = store.load()
    alert = next((a for a in state["alerts"] if a["id"] == alert_id), None)
    if not alert:
        raise HTTPException(404, "alert not found")
    alert["drafts"] = actions.draft_all(alert)
    alert["status"] = "DRAFTED"
    store.save(state)
    return {"drafts": alert["drafts"]}


@app.post("/api/alerts/{alert_id}/status/{new_status}")
def set_status(alert_id: str, new_status: str):
    if new_status not in ("OPEN", "DRAFTED", "APPROVED", "DISMISSED"):
        raise HTTPException(400, "bad status")
    state = store.load()
    alert = next((a for a in state["alerts"] if a["id"] == alert_id), None)
    if not alert:
        raise HTTPException(404, "alert not found")
    alert["status"] = new_status
    store.save(state)
    return {"ok": True, "stats": _stats(state)}


@app.get("/api/invoice/{inv_id}/image")
def invoice_image(inv_id: str):
    state = store.load()
    inv = next((i for i in state["invoices"] if i["id"] == inv_id), None)
    if not inv or not os.path.exists(inv.get("path", "")):
        raise HTTPException(404, "image not found")
    return FileResponse(inv["path"])


@app.post("/api/reset")
def reset():
    store.reset()
    return {"ok": True}


# ── DECISION INTELLIGENCE ───────────────────────────────────────────────────
# Both features exist ONLY because the decision layer is a pure deterministic
# function — you can re-run math on a changed world; you can't re-run an opinion.

@app.post("/api/simulate/{gstin}")
def simulate(gstin: str):
    """Counterfactual: what if this supplier were removed from the network today?"""
    state = store.load()
    before_alerts, _ = rules.evaluate(state["invoices"])
    kept = [i for i in state["invoices"]
            if i["fields"].get("seller_gstin") != gstin
            and i["fields"].get("buyer_gstin") != gstin]
    after_alerts, after_graph = rules.evaluate(kept)
    before_exp = sum(a["impact"] for a in before_alerts)
    after_exp = sum(a["impact"] for a in after_alerts)
    resolved = [a["title"] for a in before_alerts
                if a["title"] not in {b["title"] for b in after_alerts}]
    return {
        "removed": gstin,
        "before": {"exposure": round(before_exp, 2), "alerts": len(before_alerts)},
        "after": {"exposure": round(after_exp, 2), "alerts": len(after_alerts)},
        "saved": round(before_exp - after_exp, 2),
        "resolved_findings": resolved,
        "graph_after": after_graph,
    }


@app.get("/api/timeline")
def timeline():
    """Time machine: replay the network invoice-by-invoice; when did risk begin?"""
    state = store.load()
    dated = [i for i in state["invoices"] if i["fields"].get("invoice_date")]
    dated.sort(key=lambda i: i["fields"]["invoice_date"])
    steps, prev_titles = [], set()
    seen = []
    for inv in dated:
        seen.append(inv)
        d = inv["fields"]["invoice_date"]
        if steps and steps[-1]["date"] == d and inv is not dated[-1]:
            continue  # collapse same-day, evaluate once per date
        subset = [i for i in dated if i["fields"]["invoice_date"] <= d]
        alerts, _ = rules.evaluate(subset)
        titles = {a["title"] for a in alerts}
        steps.append({
            "date": d,
            "invoices": len(subset),
            "exposure": round(sum(a["impact"] for a in alerts), 2),
            "alerts": len(alerts),
            "new_findings": sorted(titles - prev_titles),
            "trigger_file": inv["file"],
        })
        prev_titles = titles
    return {"steps": steps}


@app.post("/api/demo/{mode}")
def demo(mode: str):
    """mode=instant → load pre-extracted results (rehearsal hotkey).
    mode=live → run the bundled demo photos through the real pipeline."""
    import json as _json
    if mode == "instant":
        snap = os.path.join(DEMO, "snapshot.json")
        if not os.path.exists(snap):
            raise HTTPException(404, "demo/snapshot.json missing — run demo_build.py first")
        with open(snap) as f:
            state = _json.load(f)
        # re-point image paths at the demo folder
        for inv in state["invoices"]:
            inv["path"] = os.path.join(DEMO, os.path.basename(inv.get("path", "")))
        store.save(state)
        return {"ok": True, "mode": "instant", "stats": _stats(state)}
    elif mode == "live":
        imgs = sorted(f for f in os.listdir(DEMO) if f.lower().endswith((".jpg", ".png")))
        if not imgs:
            raise HTTPException(404, "no demo images — run demo_build.py first")
        store.reset()
        state = store.load()
        t0 = time.time()
        for fname in imgs:
            path = os.path.join(DEMO, fname)
            result = extraction.extract(path)
            state["invoices"].append({"id": "inv_" + uuid.uuid4().hex[:8],
                                      "file": fname, "path": path, **result})
        state["stopwatch_seconds"] = time.time() - t0
        alerts, graph = rules.evaluate(state["invoices"])
        for i, a in enumerate(alerts):
            a["id"] = f"alert_{i+1}"
        state["alerts"], state["graph"] = alerts, graph
        store.save(state)
        return {"ok": True, "mode": "live", "stats": _stats(state)}
    raise HTTPException(400, "mode must be instant|live")


if __name__ == "__main__":
    import uvicorn
    print("\n  CHAKRA — what should the accountant do next?")
    print("  UI:  http://localhost:8000\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)
