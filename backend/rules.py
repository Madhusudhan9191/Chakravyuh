"""
CHAKRA — deterministic decision layer. No LLM anywhere in this file.

Rules:
  R1 CIRCULAR_TRADING    — cycle in the vendor payment graph (networkx simple_cycles)
  R2 RING_EXPOSURE       — THE signature finding: a CLEAN buyer whose supplier
                           chain reaches a fraud ring within 2 hops. ITC at risk.
  R3 DUPLICATE_INVOICE   — same seller GSTIN + invoice number (+ amount)
  R4 INVALID_GSTIN       — extraction routed a GSTIN to manual review

Impact model (stated, defensible):
  - Ring members: full GST amount routed through the ring flagged.
  - Exposed buyer: ITC at risk = CGST+SGST on that buyer's purchases from the
    exposed supplier (per CGST §16(2) the credit is deniable), + 18% interest.
Every alert carries the evidence path so the UI can animate "Why am I connected?".
"""
import networkx as nx
from collections import defaultdict

INTEREST = 0.18


def _fmt_path(path, names):
    return [{"gstin": g, "name": names.get(g, g)} for g in path]


def evaluate(invoices):
    """invoices: list of dicts with fields from extraction (plus id, file).
    Returns (alerts, graph_payload)."""
    G = nx.DiGraph()
    names, edge_data = {}, {}

    for inv in invoices:
        f = inv["fields"]
        s, b = f.get("seller_gstin") or f"?{f.get('seller_name','')}", \
               f.get("buyer_gstin") or f"?{f.get('buyer_name','')}"
        names[s] = f.get("seller_name") or s
        names[b] = f.get("buyer_name") or b
        if s == b:
            continue
        G.add_edge(s, b)
        d = edge_data.setdefault((s, b), {"amount": 0.0, "gst": 0.0, "invoices": []})
        d["amount"] += f.get("total") or 0.0
        d["gst"] += (f.get("cgst") or 0.0) + (f.get("sgst") or 0.0)
        d["invoices"].append(inv["id"])

    alerts = []

    # ── R1: circular trading rings ──────────────────────────────────────────
    cycles = [c for c in nx.simple_cycles(G) if len(c) >= 2]
    ring_nodes = set()
    for idx, cyc in enumerate(cycles):
        ring_nodes.update(cyc)
        ring_edges = [(cyc[i], cyc[(i + 1) % len(cyc)]) for i in range(len(cyc))]
        amount = sum(edge_data.get(e, {}).get("amount", 0.0) for e in ring_edges)
        gst = sum(edge_data.get(e, {}).get("gst", 0.0) for e in ring_edges)
        inv_ids = [i for e in ring_edges for i in edge_data.get(e, {}).get("invoices", [])]
        alerts.append({
            "rule": "CIRCULAR_TRADING", "severity": "CRITICAL",
            "title": f"{len(cyc)}-company circular trading ring",
            "entity": names.get(cyc[0], cyc[0]),
            "entities": [{"gstin": g, "name": names.get(g, g)} for g in cyc],
            "impact": round(gst, 2),
            "impact_label": "GST routed through ring",
            "invoice_ids": inv_ids,
            "path": _fmt_path(cyc + [cyc[0]], names),
            "why": (f"{len(cyc)} companies invoice each other in a closed loop "
                    f"(₹{amount:,.0f} circulated). Circular invoicing without goods "
                    f"movement is the classic fake-ITC pattern (CGST §132)."),
            "section": "CGST §132(1)(b)/(c)",
        })

    # ── R2: ring exposure within 2 hops (the demo star) ─────────────────────
    # hop 1: buys directly FROM a ring member · hop 2: buys from a hop-1 buyer
    if ring_nodes:
        dist, parent = {}, {}
        frontier = list(ring_nodes)
        for n in frontier:
            dist[n] = 0
        for hop in (1, 2):
            nxt = []
            for u in frontier:
                for v in G.successors(u):
                    if v not in dist:
                        dist[v] = hop
                        parent[v] = u
                        nxt.append(v)
            frontier = nxt
        for node, hop in dist.items():
            if hop == 0 or node in ring_nodes:
                continue
            # ITC at risk = GST on this buyer's purchases from its exposed supplier
            sup = parent[node]
            gst = sum(d["gst"] for (s, b), d in edge_data.items() if b == node and s == sup)
            if gst <= 0:
                continue
            # reconstruct path back into the ring
            path, cur = [node], node
            while cur in parent:
                cur = parent[cur]
                path.append(cur)
            path = list(reversed(path))
            exposure = round(gst * (1 + INTEREST), 2)
            alerts.append({
                "rule": "RING_EXPOSURE", "severity": "CRITICAL" if hop == 2 else "HIGH",
                "title": f"Clean company {hop} hop{'s' if hop > 1 else ''} from a fraud ring",
                "entity": names.get(node, node),
                "entities": [{"gstin": node, "name": names.get(node, node)}],
                "impact": exposure,
                "impact_label": "ITC reversal + 18% interest at risk",
                "invoice_ids": [i for (s, b), d in edge_data.items() if b == node and s == sup
                                for i in d["invoices"]],
                "path": _fmt_path(path, names),
                "why": (f"{names.get(node, node)} has clean books — but its supplier "
                        f"{'chain reaches' if hop == 2 else names.get(sup, sup) + ' is inside'} "
                        f"a circular trading ring. Under CGST §16(2) the input tax credit on "
                        f"those purchases (₹{gst:,.0f}) can be denied, plus 18% interest. "
                        f"They have never met these companies."),
                "section": "CGST §16(2), §50",
            })

    # ── R3: duplicate invoices ──────────────────────────────────────────────
    seen = defaultdict(list)
    for inv in invoices:
        f = inv["fields"]
        key = (f.get("seller_gstin"), (f.get("invoice_number") or "").strip().upper())
        if key[0] and key[1]:
            seen[key].append(inv)
    for (gstin, number), grp in seen.items():
        if len(grp) > 1:
            amt = grp[0]["fields"].get("total") or 0.0
            gst = sum((i["fields"].get("cgst") or 0) + (i["fields"].get("sgst") or 0)
                      for i in grp[1:])
            alerts.append({
                "rule": "DUPLICATE_INVOICE", "severity": "HIGH",
                "title": f"Invoice {number} submitted {len(grp)}×",
                "entity": names.get(gstin, gstin),
                "entities": [{"gstin": gstin, "name": names.get(gstin, gstin)}],
                "impact": round(gst, 2),
                "impact_label": "double-claimed ITC",
                "invoice_ids": [i["id"] for i in grp],
                "path": [],
                "why": (f"The same seller GSTIN + invoice number appears {len(grp)} times "
                        f"(₹{amt:,.0f} each). ITC can be claimed only once per document."),
                "section": "CGST §16",
            })

    # ── R4: GSTINs the trust layer rejected ────────────────────────────────
    for inv in invoices:
        if inv.get("review"):
            fieldlist = ", ".join(inv["review"])
            gst = (inv["fields"].get("cgst") or 0) + (inv["fields"].get("sgst") or 0)
            alerts.append({
                "rule": "MANUAL_REVIEW", "severity": "MEDIUM",
                "title": f"Fields need human eyes: {fieldlist}",
                "entity": inv["fields"].get("seller_name") or inv["file"],
                "entities": [],
                "impact": round(gst, 2),
                "impact_label": "ITC blocked pending verification",
                "invoice_ids": [inv["id"]],
                "path": [],
                "why": ("The trust layer rejected these fields (checksum/consistency) "
                        "rather than accept a possibly-wrong value. ITC on this document "
                        "is blocked until verified."),
                "section": "internal governance",
            })

    # rank by rupees — never by confidence score
    alerts.sort(key=lambda a: -a["impact"])
    for i, a in enumerate(alerts):
        a["id"] = f"alert_{i+1}"
        a["status"] = "OPEN"

    # ── graph payload for the UI ────────────────────────────────────────────
    hop_of = {}
    if ring_nodes:
        for node in G.nodes:
            if node in ring_nodes:
                hop_of[node] = 0
        for a in alerts:
            if a["rule"] == "RING_EXPOSURE":
                hop_of[a["entities"][0]["gstin"]] = 1 if a["severity"] == "HIGH" else 2

    # Visibility Horizon: a node whose purchase side we hold no invoices for —
    # we cannot see who supplies THEM. Marked honestly instead of guessed at.
    nodes = [{"id": n, "name": names.get(n, n),
              "horizon": G.in_degree(n) == 0,
              "role": ("ring" if hop_of.get(n) == 0 else
                       "hop1" if hop_of.get(n) == 1 else
                       "hop2" if hop_of.get(n) == 2 else "clean")}
             for n in G.nodes]
    cycle_edge_set = {(c[i], c[(i + 1) % len(c)]) for c in cycles for i in range(len(c))}
    edges = [{"source": s, "target": b,
              "amount": round(d["amount"], 2), "gst": round(d["gst"], 2),
              "count": len(d["invoices"]), "in_ring": (s, b) in cycle_edge_set}
             for (s, b), d in edge_data.items()]

    return alerts, {"nodes": nodes, "edges": edges, "rings": len(cycles)}
