"""
Turning one receiver's details into a filled Device Issuance Agreement PDF.

Shared by the Batch (a CSV of receivers, see cli.py) and the Form (one agreement
at a time on screen, see form.py), so both apply the same rules and defaults.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, NumberObject

# ---------------------------------------------------------------------------
# Column names -> internal keys.  Matching is case-insensitive and ignores
# spaces, punctuation and underscores, so "Receiver name", "receiver_name" and
# "RECEIVER NAME" are all accepted.  Add your own synonyms here if needed.
# ---------------------------------------------------------------------------
COLUMN_ALIASES = {
    "agreement_no":        ["agreement no", "agreement number", "agreement", "no", "number", "contract no"],
    "agreement_date":      ["date", "agreement date", "contract date"],
    "issuer_name":         ["issuer name", "issuer", "representative", "representative name", "issued by"],
    "issuer_position":     ["issuer position", "position"],
    "issuer_contact":      ["issuer contact", "issuer phone", "issuer email", "issuer phone email"],
    "receiver_name":       ["receiver name", "receiver", "full name", "name", "employee name", "student name"],
    "receiver_status":     ["status", "receiver status", "role", "type of receiver"],
    "receiver_id":         ["id", "id no", "receiver id", "employee id", "student id", "employee student id no", "id number"],
    "receiver_faculty":    ["faculty", "department", "faculty department", "receiver faculty", "receiver department"],
    "receiver_contact":    ["contact", "receiver contact", "phone", "email", "e-mail", "phone email", "phone e-mail", "receiver phone email"],
    "device_type":         ["device type", "device", "type"],
    "device_type_other":   ["other device", "device type other", "device other"],
    "device_model":        ["brand model", "brand & model", "brand and model", "model", "device model", "brand"],
    "device_serial":       ["serial", "serial no", "serial number", "inventory no", "inventory", "serial inventory no", "asset tag"],
    "accessories":         ["accessories", "accessories included", "accessory"],
    "acc_other_text":      ["other accessory", "other accessories", "accessories other"],
    "condition":           ["condition", "condition on issue", "device condition"],
    "condition_notes":     ["notes", "condition notes", "remarks", "comments"],
    "issue_date":          ["issue date", "issued on", "issued", "date issued"],
    "return_date":         ["return date", "return by", "due date"],
    "return_until_end":    ["until end", "until end of employment", "until end of employment studies", "return until end", "end of employment"],
    "return_on_request":   ["on request", "upon request", "return on request", "upon department request"],
}

STATUS_MAP = {
    "staff": "staff", "employee": "staff", "administrative": "staff", "admin": "staff",
    "teacher": "teacher", "lecturer": "teacher", "professor": "teacher", "instructor": "teacher", "faculty": "teacher",
    "student": "student", "phd": "student", "master": "student", "bachelor": "student",
}
DEVICE_MAP = {
    "laptop": "laptop", "notebook": "laptop", "macbook": "laptop",
    "desktop": "desktop", "desktop pc": "desktop", "pc": "desktop", "computer": "desktop", "workstation": "desktop",
    "monitor": "monitor", "display": "monitor", "screen": "monitor",
}
CONDITION_MAP = {"new": "new", "good": "good", "used": "used", "fair": "used", "worn": "used"}
ACCESSORY_MAP = {
    "charger": "acc_charger", "adapter": "acc_charger", "power adapter": "acc_charger", "power supply": "acc_charger",
    "bag": "acc_bag", "case": "acc_bag", "sleeve": "acc_bag",
    "mouse": "acc_mouse",
    "keyboard": "acc_keyboard",
}
YES_WORDS = {"yes", "y", "true", "1", "x", "✓", "✔", "on", "checked"}
DATE_FORMATS = ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def norm(s: str) -> str:
    """Normalise a header or value for matching: lower-case, letters/digits only."""
    return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()


def build_header_map(headers: list[str]) -> dict[str, str]:
    """Map internal key -> actual column header found in the file."""
    lookup = {}
    for key, aliases in COLUMN_ALIASES.items():
        for a in [key] + aliases:
            lookup.setdefault(norm(a), key)
    found = {}
    for h in headers:
        if h is None:
            continue
        key = lookup.get(norm(h))
        if key and key not in found:
            found[key] = h
    return found


def parse_date(v) -> date | None:
    """Return the date in recognised date text, or None."""
    s = clean(v)
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def fmt_date(v) -> str:
    """Return a DD/MM/YYYY string for recognised date text; pass anything else through."""
    if v is None or v == "":
        return ""
    d = parse_date(v)
    return d.strftime("%d/%m/%Y") if d else str(v).strip()


def is_yes(v) -> bool:
    return norm(v) in YES_WORDS if v not in (None, "") else False


def clean(v) -> str:
    if v is None:
        return ""
    return str(v).strip()


def safe_filename(s: str) -> str:
    s = re.sub(r"[^\w\-. ]+", "", s, flags=re.UNICODE).strip()
    return re.sub(r"\s+", "_", s) or "Agreement"


def pdf_filename(values: dict, fallback) -> str:
    """File name for an agreement's PDF; `fallback` stands in for missing number or name."""
    name = values.get("receiver_name", f"row{fallback}")
    return safe_filename(f"Agreement_{values.get('agreement_no', fallback)}_{name}") + ".pdf"


def format_agreement_no(cfg: dict, now: datetime, seq: int) -> str:
    """Agreement number from agreement_no_pattern for time `now` and sequence number `seq`."""
    pattern = cfg.get("agreement_no_pattern", "{now:%y%m%d%H%M}")
    return pattern.format(now=now, year=now.year, seq=seq, date=now.strftime("%Y%m%d"))


# ---------------------------------------------------------------------------
# Row -> PDF field values
# ---------------------------------------------------------------------------
def row_to_fields(row: dict, hmap: dict[str, str], cfg: dict, index: int) -> tuple[dict, list[str]]:
    """Return (field_values, warnings) for one input row."""
    g = lambda key: row.get(hmap[key]) if key in hmap else None   # noqa: E731
    warnings: list[str] = []
    f: dict[str, str] = {}

    # --- header -----------------------------------------------------------
    agreement_no = clean(g("agreement_no"))
    if not agreement_no:
        now = cfg["_now"] + timedelta(minutes=index - 1)   # one minute per row keeps a batch's numbers unique
        agreement_no = format_agreement_no(cfg, now, cfg.get("_seq_start", 1) + index - 1)
    f["agreement_no"] = agreement_no
    f["agreement_date"] = fmt_date(g("agreement_date")) or date.today().strftime("%d/%m/%Y")

    # --- issuer (falls back to config defaults) -----------------------------
    f["issuer_name"] = clean(g("issuer_name")) or cfg.get("issuer_name", "")
    f["issuer_position"] = clean(g("issuer_position")) or cfg.get("issuer_position", "")
    f["issuer_contact"] = clean(g("issuer_contact")) or cfg.get("issuer_contact", "")

    # --- receiver -----------------------------------------------------------
    f["receiver_name"] = clean(g("receiver_name"))
    if not f["receiver_name"]:
        warnings.append("receiver name is empty")
    f["receiver_id"] = clean(g("receiver_id"))
    f["receiver_faculty"] = clean(g("receiver_faculty"))
    f["receiver_contact"] = clean(g("receiver_contact"))
    status = STATUS_MAP.get(norm(g("receiver_status")))
    if status:
        f["receiver_status"] = "/" + status
    elif clean(g("receiver_status")):
        warnings.append(f"unknown status '{clean(g('receiver_status'))}' (use Staff / Teacher / Student)")

    # --- device -------------------------------------------------------------
    dtype_raw = clean(g("device_type"))
    dtype = DEVICE_MAP.get(norm(dtype_raw))
    if dtype:
        f["device_type"] = "/" + dtype
    elif dtype_raw:
        f["device_type"] = "/other"
        f["device_type_other"] = clean(g("device_type_other")) or dtype_raw
    if clean(g("device_type_other")) and "device_type_other" not in f:
        f["device_type_other"] = clean(g("device_type_other"))
    f["device_model"] = clean(g("device_model"))
    f["device_serial"] = clean(g("device_serial"))

    # accessories: "Charger, Bag, USB-C hub"  ->  checkboxes + Other text
    others = []
    for item in re.split(r"[,;/\n]+", clean(g("accessories"))):
        item = item.strip()
        if not item:
            continue
        key = ACCESSORY_MAP.get(norm(item))
        if key:
            f[key] = "/Yes"
        else:
            others.append(item)
    if clean(g("acc_other_text")):
        others.append(clean(g("acc_other_text")))
    if others:
        f["acc_other"] = "/Yes"
        f["acc_other_text"] = ", ".join(others)

    cond = CONDITION_MAP.get(norm(g("condition")))
    if cond:
        f["condition"] = "/" + cond
    elif clean(g("condition")):
        warnings.append(f"unknown condition '{clean(g('condition'))}' (use New / Good / Used)")
    f["condition_notes"] = clean(g("condition_notes"))

    f["issue_date"] = fmt_date(g("issue_date")) or f["agreement_date"]
    f["return_date"] = fmt_date(g("return_date"))
    if is_yes(g("return_until_end")):
        f["return_until_end"] = "/Yes"
    if is_yes(g("return_on_request")):
        f["return_on_request"] = "/Yes"
    if not f["return_date"] and "return_until_end" not in f and "return_on_request" not in f:
        warnings.append("no return date / return condition given")

    # --- signature blocks (names pre-filled, signatures stay handwritten) ---
    f["sig_issuer_name"] = ", ".join(x for x in (f["issuer_name"], f["issuer_position"]) if x)
    f["sig_receiver_name"] = f["receiver_name"]
    if cfg.get("prefill_signature_dates", True):
        f["sig_issuer_date"] = f["issue_date"]
        f["sig_receiver_date"] = f["issue_date"]

    return {k: v for k, v in f.items() if v not in ("", None)}, warnings


# ---------------------------------------------------------------------------
# PDF filling
# ---------------------------------------------------------------------------
def fill_pdf(template: Path, values: dict, out_path: Path, lock: bool) -> None:
    reader = PdfReader(str(template))
    writer = PdfWriter(clone_from=reader)
    for page in writer.pages:
        # pypdf writes the appearance streams itself; NeedAppearances is deliberately
        # left off so every viewer (Acrobat, Chrome, Preview, poppler) shows the same thing.
        writer.update_page_form_field_values(page, values, auto_regenerate=False)

    if lock:  # make every field read-only so the values can't be changed afterwards
        for page in writer.pages:
            for annot in page.get("/Annots", []):
                obj = annot.get_object()
                target = obj["/Parent"].get_object() if "/Parent" in obj and "/T" not in obj else obj
                flags = int(target.get("/Ff", 0))
                target[NameObject("/Ff")] = NumberObject(flags | 1)

    doc_info = {"/Title": f"Device Issuance Agreement {values.get('agreement_no', '')} — {values.get('receiver_name', '')}",
                "/Author": "UFAZ IT Department"}
    writer.add_metadata(doc_info)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as fh:
        writer.write(fh)
