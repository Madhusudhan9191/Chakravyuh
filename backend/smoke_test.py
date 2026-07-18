#!/usr/bin/env python3
"""30-second health check after every transfer. Run: python smoke_test.py [--with-gemma]"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ok = lambda m: print(f"  ✅ {m}")
bad = lambda m: (print(f"  🚨 {m}"), sys.exit(1))

print("CHAKRA smoke test")
try:
    import gemma, extraction, rules, actions, store, server  # noqa
    ok("all modules import")
except Exception as e:
    bad(f"import failed: {e}")

# trust layer regression (patterns from 7 live pre-event runs)
g = {"taxable_value": 267883.6, "cgst": 20431.8, "sgst": 20431.8, "total": 308747.2,
     "line_items": [{"hsn": "7306", "qty": 120, "rate": 1450.0, "amount": 174000},
                    {"hsn": "7307", "qty": 240, "rate": 185.5, "amount": 44520},
                    {"hsn": "9965", "qty": 1, "rate": 8500.0, "amount": 8500}]}
rec = []
g2 = extraction.repair_money(dict(g), rec)
(abs(g2["taxable_value"] - 227020.0) < 0.01 and abs(g2["total"] - 267883.6) < 0.01) or bad("money repair broken")
extraction.gstin_structural_fix("29AABC51429B1ZQ") == "29AABCS1429B1ZQ" or bad("structural fix broken")
extraction.gstin_valid("29AABCS1429B1ZQ") or bad("checksum broken")
ok("trust layer regression")

# rules + demo snapshot
snap = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo", "snapshot.json")
if os.path.exists(snap):
    import json
    state = json.load(open(snap))
    alerts, graph = rules.evaluate(state["invoices"])
    alerts and alerts[0]["rule"] == "RING_EXPOSURE" or bad("demo story broken")
    ok(f"rules on demo data: {len(alerts)} findings, #1 = {alerts[0]['entity']}")
else:
    print("  ⚠️  demo/snapshot.json missing — run demo_build.py")

# gemma connectivity
connected, model, ms = gemma.status()
if connected:
    ok(f"Gemma reachable: {model} ({ms} ms)")
    if "--with-gemma" in sys.argv:
        imgs = [f for f in os.listdir("demo") if f.endswith(".jpg")]
        if imgs:
            r = extraction.extract(os.path.join("demo", sorted(imgs)[0]))
            r["fields"].get("seller_gstin") or bad("live extraction returned nothing")
            ok(f"live extraction: {r['timings']['main']}s, "
               f"{len([x for x in r['receipts'] if x['kind']=='repair'])} repairs, "
               f"review={r['review'] or 'none'}")
else:
    print("  ⚠️  Gemma NOT reachable — start LM Studio server (drafts will use fallback templates)")

print("SMOKE TEST PASSED — run: python server.py → http://localhost:8000")
