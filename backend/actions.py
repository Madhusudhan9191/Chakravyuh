"""
CHAKRA — THE ACTION ENGINE. Every alert terminates in ready-to-send paperwork.

Gemma WRITES from a deterministic context block. It never decides.
If Gemma is unreachable, deterministic templates keep the demo alive
(clearly labelled as fallback).
"""
import gemma

SYSTEM = ("You are drafting on behalf of a Chartered Accountant's audit desk in India. "
          "Write the complete, ready-to-send document in plain professional English. "
          "Use ONLY the facts in the CONTEXT block — never invent amounts, dates, names "
          "or GSTINs. No markdown, no headers with #, no placeholders like [Name] unless "
          "the context lacks that fact. Start directly with the document.")

DOC_SPECS = {
    "vendor_email": {
        "label": "Vendor clarification email",
        "task": ("Draft a firm but professional email to the supplier named in ENTITY. "
                 "State that transactions are under compliance review, cite the finding, "
                 "and request within 7 days: signed transport receipts (lorry/e-way bill), "
                 "delivery challans, and stock ledger extracts proving goods movement.")},
    "client_advisory": {
        "label": "Client advisory",
        "task": ("Draft a plain-language advisory letter to the CA's client explaining: "
                 "what was found, exactly how many rupees of input tax credit are at risk "
                 "and under which CGST section, and a numbered list of the 3-4 immediate "
                 "steps the client must take. Reassure that their own books are clean if "
                 "the finding is exposure-through-suppliers.")},
    "payment_hold": {
        "label": "Payment hold recommendation",
        "task": ("Draft a short internal treasury memo recommending an immediate hold on "
                 "payments to the flagged supplier, stating the evidence and the exact "
                 "conditions for releasing the hold.")},
    "file_note": {
        "label": "Audit file note",
        "task": ("Draft a concise internal audit file note for the CA's own records: the "
                 "deterministic rule triggered, evidence summary, exposure computed, and "
                 "actions taken. This is the CA's legal cover under CGST §132(1)(l).")},
}

# which documents make sense per rule
DOCS_FOR_RULE = {
    "CIRCULAR_TRADING": ["client_advisory", "payment_hold", "file_note"],
    "RING_EXPOSURE": ["vendor_email", "client_advisory", "payment_hold", "file_note"],
    "DUPLICATE_INVOICE": ["vendor_email", "file_note"],
    "MANUAL_REVIEW": ["file_note"],
}


def _context_block(alert):
    ents = ", ".join(f"{e['name']} ({e['gstin']})" for e in alert.get("entities", [])) or alert.get("entity", "")
    path = " → ".join(p["name"] for p in alert.get("path", []))
    return (f"CONTEXT:\n"
            f"Finding        : {alert['title']}\n"
            f"Rule           : {alert['rule']} (deterministic graph/ledger analysis, not AI opinion)\n"
            f"Legal basis    : {alert.get('section', '')}\n"
            f"Exposure       : INR {alert['impact']:,.2f} ({alert.get('impact_label', '')})\n"
            f"Entities       : {ents}\n"
            + (f"Evidence path  : {path}\n" if path else "")
            + f"Why flagged    : {alert.get('why', '')}\n")


def draft(alert, doc_type):
    spec = DOC_SPECS[doc_type]
    prompt = _context_block(alert) + "\nTASK:\n" + spec["task"]
    try:
        text, dt = gemma.generate_text(prompt, system=SYSTEM)
        if not text.strip():
            raise RuntimeError("empty draft")
        return {"type": doc_type, "label": spec["label"], "text": text,
                "model": "gemma (local)", "seconds": round(dt, 1), "status": "DRAFT"}
    except Exception as e:
        return {"type": doc_type, "label": spec["label"],
                "text": _fallback(alert, doc_type),
                "model": f"offline template ({e})", "seconds": 0, "status": "DRAFT"}


def draft_all(alert):
    return [draft(alert, t) for t in DOCS_FOR_RULE.get(alert["rule"], ["file_note"])]


def _fallback(alert, doc_type):
    ents = ", ".join(e["name"] for e in alert.get("entities", [])) or alert.get("entity", "")
    base = (f"Re: {alert['title']}\n\n"
            f"A deterministic compliance review has flagged the following:\n"
            f"- Finding: {alert['title']}\n"
            f"- Exposure: INR {alert['impact']:,.2f} ({alert.get('impact_label','')})\n"
            f"- Legal basis: {alert.get('section','')}\n"
            f"- Entities: {ents}\n\n{alert.get('why','')}\n\n")
    tails = {
        "vendor_email": ("Please provide within 7 days: signed transport receipts, "
                         "e-way bills, delivery challans and stock ledger extracts "
                         "evidencing actual movement of goods.\n\nRegards,\nAudit Desk"),
        "client_advisory": ("Recommended immediate steps:\n1. Suspend further payments to the "
                            "flagged supplier.\n2. Do not claim ITC on the affected invoices in "
                            "the next GSTR-3B.\n3. Collect goods-movement evidence from the "
                            "supplier.\n4. Await our verification before resuming.\n\n"
                            "Your own records are in order; this exposure arises through your "
                            "supply chain.\n\nRegards,\nYour Chartered Accountant"),
        "payment_hold": ("Recommendation: place an immediate hold on payments to the above "
                         "entities until goods-movement evidence is produced and verified.\n\n"
                         "— Treasury advisory (auto-generated, review before action)"),
        "file_note": ("File note recorded for audit trail purposes under CGST §132(1)(l). "
                      "Evidence, rule trace and exposure computation preserved."),
    }
    return base + tails.get(doc_type, "")
