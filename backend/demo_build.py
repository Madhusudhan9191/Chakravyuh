#!/usr/bin/env python3
"""
Builds the demo dataset into ./demo :
  - 9 invoice photos telling the v3 story:
      ring: Agni Traders → Bhairav Metals → Chakor Alloys → Agni
      hop1: Agni → Deepak Chemicals
      hop2: Deepak → SHARMA TRADERS   ← the star finding (clean but exposed)
      clean pairs + one duplicate invoice
  - snapshot.json — pre-verified state for the ⚡ instant demo (rehearsal hotkey).
    Live demo mode re-extracts the same photos through Gemma for real.

Run once on any machine with Pillow: python demo_build.py
"""
import json, math, os, random, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rules
from extraction import ALPHANUM

DEMO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo")
os.makedirs(DEMO, exist_ok=True)
rng = random.Random(42)


def check_digit(g14):
    t = 0
    for i, ch in enumerate(g14):
        v = ALPHANUM.index(ch) * (2 if i % 2 else 1)
        t += v // 36 + v % 36
    return ALPHANUM[(36 - t % 36) % 36]


def gstin(pan):
    base = "29" + pan + "1Z"
    return base + check_digit(base)


COMPANIES = {
    "AGNI": ("AGNI TRADERS PVT LTD", gstin("AABCA1111A")),
    "BHAIRAV": ("BHAIRAV METALS", gstin("AABCB2222B")),
    "CHAKOR": ("CHAKOR ALLOYS", gstin("AABCC3333C")),
    "DEEPAK": ("DEEPAK CHEMICALS", gstin("AABCD4444D")),
    "SHARMA": ("SHARMA TRADERS", gstin("AABCS5555S")),
    "KAVERI": ("KAVERI STEEL TRADERS", gstin("AABCK6666K")),
    "ANAND": ("ANAND FABRICATORS", gstin("AABCF7777F")),
    "LAKSHMI": ("LAKSHMI METAL WORKS", gstin("AABCL8888L")),
    "KPT": ("KARNATAKA PRECISION TOOLS", gstin("AABCP9999P")),
}

ITEMS = [("MS Steel Pipes 50mm", "7306"), ("GI Coupling 50mm", "7307"),
         ("HR Sheets 2mm", "7208"), ("Industrial Solvent Grade-A", "2902"),
         ("Copper Wire 4sqmm", "7408"), ("Welding Electrodes", "8311")]

# (seller, buyer, taxable, date, invoice_no or None)
SCRIPT = [
    ("AGNI", "BHAIRAV", 95000, "02/06/2026", None),
    ("BHAIRAV", "CHAKOR", 91000, "06/06/2026", None),
    ("CHAKOR", "AGNI", 93500, "13/06/2026", None),       # ring closes — 11 days
    ("AGNI", "DEEPAK", 210000, "18/06/2026", None),      # hop 1
    ("DEEPAK", "SHARMA", 330000, "24/06/2026", None),    # hop 2 — the star
    ("KAVERI", "ANAND", 145000, "05/06/2026", None),     # clean
    ("LAKSHMI", "KPT", 88000, "10/06/2026", "LMW/2026-27/0412"),
    ("LAKSHMI", "KPT", 88000, "21/06/2026", "LMW/2026-27/0412"),  # duplicate!
    ("KAVERI", "SHARMA", 76000, "09/06/2026", None),     # clean purchase by Sharma
]


def inr(x):
    s = f"{x:,.2f}"
    ip, dec = s.split(".")
    ip = ip.replace(",", "")
    if len(ip) > 3:
        head, tail = ip[:-3], ip[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:]); head = head[:-2]
        if head: groups.insert(0, head)
        ip = ",".join(groups) + "," + tail
    return ip + "." + dec


def render(idx, sname, sg, bname, bg, inv_no, date, line_items, taxable, cgst, sgst, total):
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    W, H = 1240, 1650
    img = Image.new("RGB", (W, H), (252, 250, 246))
    d = ImageDraw.Draw(img)
    F = "/usr/share/fonts/truetype/dejavu/"
    ft = ImageFont.truetype(F + "DejaVuSans-Bold.ttf", 34)
    fb = ImageFont.truetype(F + "DejaVuSans-Bold.ttf", 22)
    fr = ImageFont.truetype(F + "DejaVuSans.ttf", 21)
    fs = ImageFont.truetype(F + "DejaVuSans.ttf", 18)
    ink = (35, 32, 40)
    line = lambda y, x0=40, x1=W - 40: d.line([(x0, y), (x1, y)], fill=ink, width=2)
    d.text((W // 2, 50), "TAX INVOICE", font=fb, fill=ink, anchor="mm")
    d.text((W // 2, 105), sname, font=ft, fill=ink, anchor="mm")
    d.text((W // 2, 145), "Peenya Industrial Area, Bengaluru - 560058", font=fs, fill=ink, anchor="mm")
    d.text((W // 2, 172), f"GSTIN: {sg}    State: Karnataka (29)", font=fr, fill=ink, anchor="mm")
    line(200)
    d.text((60, 220), f"Invoice No: {inv_no}", font=fr, fill=ink)
    d.text((W - 60, 220), f"Date: {date}", font=fr, fill=ink, anchor="ra")
    line(260)
    d.text((60, 280), "Bill To:", font=fb, fill=ink)
    d.text((60, 312), bname, font=fr, fill=ink)
    d.text((60, 340), "Bommasandra Indl Estate, Bengaluru - 560099", font=fs, fill=ink)
    d.text((60, 368), f"GSTIN: {bg}", font=fr, fill=ink)
    line(410)
    cols = [60, 520, 640, 750, 1180]
    for x, t in zip(cols[:4], ["Description", "HSN", "Qty", "Rate"]):
        d.text((x, 430), t, font=fb, fill=ink)
    d.text((920, 430), "Amount (Rs.)", font=fb, fill=ink)
    line(465)
    y = 495
    for it in line_items:
        d.text((cols[0], y), it["description"], font=fr, fill=ink)
        d.text((cols[1], y), it["hsn"], font=fr, fill=ink)
        d.text((cols[2], y), str(it["qty"]), font=fr, fill=ink)
        d.text((cols[3], y), inr(it["rate"]), font=fr, fill=ink)
        d.text((cols[4], y), inr(it["amount"]), font=fr, fill=ink, anchor="ra")
        y += 48
    line(y + 10)
    ty = y + 40
    for lbl, val in [("Taxable Value", taxable), ("CGST @ 9%", cgst), ("SGST @ 9%", sgst)]:
        d.text((870, ty), lbl, font=fr, fill=ink)
        d.text((cols[4], ty), inr(val), font=fr, fill=ink, anchor="ra")
        ty += 42
    line(ty + 5, x0=850)
    d.text((870, ty + 25), "TOTAL", font=fb, fill=ink)
    d.text((cols[4], ty + 25), "Rs. " + inr(total), font=fb, fill=ink, anchor="ra")
    CLEAN = True  # flip to False for crumpled phone-photo mode
    if CLEAN:
        ph = img.resize((900, int(900 * H / W)))
        path = os.path.join(DEMO, f"invoice_{idx:02d}_{sname.split()[0].lower()}.png")
        ph.save(path)
        return path
    # phone-photo degradation
    ph = img.rotate(rng.uniform(-3, 3), expand=True, fillcolor=(80, 75, 70))
    from PIL import Image as I, ImageDraw as ID
    grad = I.new("L", ph.size, 0)
    gd = ID.Draw(grad)
    amp = rng.uniform(18, 40)
    for x in range(ph.width):
        gd.line([(x, 0), (x, ph.height)], fill=max(0, int(amp * x / ph.width + 8 * math.sin(x / 130))))
    ph = I.composite(I.new("RGB", ph.size, (60, 55, 50)), ph, grad)
    noise = I.effect_noise(ph.size, rng.uniform(9, 16)).convert("L")
    ph = I.blend(ph, I.merge("RGB", (noise, noise, noise)), 0.05)
    ph = ph.filter(ImageFilter.GaussianBlur(0.6))
    ph = ph.resize((900, int(900 * ph.height / ph.width)))
    path = os.path.join(DEMO, f"invoice_{idx:02d}_{sname.split()[0].lower()}.jpg")
    ph.save(path, quality=rng.randint(60, 74))
    return path


def main():
    invoices = []
    for idx, (s, b, taxable, date, forced_no) in enumerate(SCRIPT, 1):
        sname, sg = COMPANIES[s]
        bname, bg = COMPANIES[b]
        n = rng.randint(2, 3)
        chosen = rng.sample(ITEMS, n)
        remaining, items = taxable, []
        for j, (desc, hsn) in enumerate(chosen):
            amt = remaining if j == n - 1 else round(remaining * rng.uniform(0.3, 0.55), 2)
            remaining = round(remaining - amt, 2)
            qty = rng.choice([5, 10, 24, 50, 120])
            items.append({"description": desc, "hsn": hsn, "qty": qty,
                          "rate": round(amt / qty, 2), "amount": amt})
        cgst = round(taxable * 0.09, 2)
        sgst = round(taxable * 0.09, 2)
        total = round(taxable + cgst + sgst, 2)
        inv_no = forced_no or f"{''.join(w[0] for w in sname.split()[:3])}/2026-27/{rng.randint(100,999):04d}"
        path = render(idx, sname, sg, bname, bg, inv_no, date, items, taxable, cgst, sgst, total)
        dd, mm, yy = date.split("/")
        invoices.append({
            "id": f"inv_demo{idx:02d}", "file": os.path.basename(path), "path": path,
            "fields": {"seller_name": sname, "seller_gstin": sg,
                       "buyer_name": bname, "buyer_gstin": bg,
                       "invoice_number": inv_no, "invoice_date": f"{yy}-{mm}-{dd}",
                       "line_items": items, "taxable_value": taxable,
                       "cgst": cgst, "sgst": sgst, "total": total},
            "receipts": [], "review": [], "timings": {}})
    alerts, graph = rules.evaluate(invoices)
    state = {"invoices": invoices, "alerts": alerts, "graph": graph, "stopwatch_seconds": 0.0}
    with open(os.path.join(DEMO, "snapshot.json"), "w") as f:
        json.dump(state, f, indent=1)
    print(f"demo: {len(invoices)} photos rendered")
    for a in alerts:
        print(f"  {a['severity']:8} {a['entity']:28} {a['title']:45} ₹{a['impact']:,.0f}")
    top = alerts[0]
    assert top["rule"] == "RING_EXPOSURE" and "SHARMA" in top["entity"].upper(), \
        "the star finding must rank #1 by rupees"
    print("★ Sharma Traders is finding #1 — the demo story holds.")


if __name__ == "__main__":
    main()
