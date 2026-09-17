"""
The Form in the browser — fill in Device Issuance Agreements one at a time and download each PDF.

Opened by running  generate --web,  or served by app.py on Vercel.  It starts with the Issuer
details from the settings (or from this browser's last agreement), the next agreement number
and today's date in Baku.  After each agreement the PDF downloads, and the receiver, device and
return fields are cleared for the next one; the Issuer details and dates stay.

The server remembers nothing between requests: each browser keeps its Issuer details and the
last agreement number it used in a cookie (see docs/adr/0001-no-shared-agreement-counter.md).
"""
from __future__ import annotations

import base64
import json
import threading
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote, unquote
from zoneinfo import ZoneInfo

import uvicorn
from fasthtml.common import (A, Button, Div, FastHTML, Fieldset, Form, Hidden, Input, Label, Legend, Link, P, Script,
                             Small, Style, Titled, cookie)

from .agreement import (ACCESSORIES, CONDITIONS, DEVICE_TYPES, FORM_KEYS, KEPT_FIELDS, STATUSES, TICK_BOXES,
                        form_problems, form_row, format_agreement_no, pdf_filename, render_pdf, row_to_fields)

BAKU = ZoneInfo("Asia/Baku")
MEMORY = "ufaz_form"          # the cookie with this browser's Issuer details and last agreement number
ISSUER_FIELDS = ["issuer_name", "issuer_position", "issuer_contact"]
PICO = Link(rel="stylesheet", href="https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css")
CSS = """
:root { --pico-font-size: 93.75%; --pico-spacing: 0.75rem;
        --pico-form-element-spacing-vertical: 0.3rem; --pico-form-element-spacing-horizontal: 0.6rem; }
main.container { padding-block: 1rem; }
h1 { font-size: 1.5rem; margin-bottom: 1rem; }
.section { border: 1px solid var(--pico-muted-border-color); border-radius: var(--pico-border-radius);
           padding: 0 1rem; margin-bottom: 0.75rem; }
.section > legend { font-weight: bold; padding: 0 0.4rem; }
label { font-size: 0.9em; }
.choices { display: flex; flex-wrap: wrap; gap: 0.3rem 1.25rem; margin-bottom: var(--pico-spacing); }
.choices label { margin: 0; }
.choices > legend { width: 100%; margin-bottom: 0.3rem; font-size: 0.9em; }
#bar small { display: block; margin-bottom: 0.4rem; }
#bar .blocking { color: var(--pico-del-color); }
#bar .warning { color: #c27c0e; }
#bar button { width: 100%; }
"""


def baku_now() -> datetime:
    """The time at UFAZ, whatever time zone the server runs in (Vercel runs in UTC)."""
    return datetime.now(BAKU).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------
def text(entries: dict, key: str, label: str, type: str = "text", **attrs) -> Label:
    return Label(label, Input(type=type, name=key, id=key, value=entries.get(key, ""), **attrs))


def choice(entries: dict, key: str, label: str, options: list[str]) -> Fieldset:
    return Fieldset(Legend(label),
                    *(Label(Input(type="radio", name=key, value=o, checked=entries.get(key) == o), o) for o in options),
                    cls="choices")


def tick(entries: dict, key: str, label: str) -> Label:
    return Label(Input(type="checkbox", name=key, id=key, checked=bool(entries.get(key))), label)


def section(title: str, *fields) -> Fieldset:
    return Fieldset(Legend(title), *fields, cls="section")


def bar(blocking: list[str], warnings: list[str]) -> Div:
    """The problems and the Generate button; checked again as you type."""
    return Div(*(Small(f"✗ {p}", cls="blocking") for p in blocking),
               *(Small(f"! {w}", cls="warning") for w in warnings),
               Button("Generate", type="submit", disabled=bool(blocking)),
               id="bar", hx_post="/check", hx_trigger="input delay:300ms from:#form", hx_swap="outerHTML")


def form_view(entries: dict, auto_no: str, auto_at: datetime, cfg: dict, saved: tuple[str, bytes] | None = None) -> Form:
    tick_other_device = "if (this.value.trim()) this.form.querySelector('[name=device_type][value=Other]').checked = true"
    tick_other_accessory = "if (this.value.trim()) this.form.acc_other.checked = true"
    return Form(
        section("Agreement",
                Div(text(entries, "agreement_no", "Agreement No.", placeholder=auto_no),
                    text(entries, "agreement_date", "Date", type="date"), cls="grid")),
        section("Issuer",
                Div(text(entries, "issuer_name", "Representative"),
                    text(entries, "issuer_position", "Position"),
                    text(entries, "issuer_contact", "Phone / e-mail"), cls="grid")),
        section("Receiver",
                Div(text(entries, "receiver_name", "Full name *", autofocus=True),
                    choice(entries, "receiver_status", "Status", STATUSES), cls="grid"),
                Div(text(entries, "receiver_id", "Employee / Student ID"),
                    text(entries, "receiver_faculty", "Faculty / Department"),
                    text(entries, "receiver_contact", "Phone / e-mail"), cls="grid")),
        section("Device",
                Div(choice(entries, "device_type", "Device type", DEVICE_TYPES),
                    text(entries, "device_type_other", "Other device type", oninput=tick_other_device), cls="grid"),
                Div(text(entries, "device_model", "Brand & model"),
                    text(entries, "device_serial", "Serial / Inventory No."), cls="grid"),
                Div(Fieldset(Legend("Accessories"), *(tick(entries, f"acc_{a.lower()}", a) for a in ACCESSORIES),
                             tick(entries, "acc_other", "Other"), cls="choices"),
                    text(entries, "acc_other_text", "Other accessory", oninput=tick_other_accessory), cls="grid"),
                Div(choice(entries, "condition", "Condition", CONDITIONS),
                    text(entries, "condition_notes", "Notes"), cls="grid")),
        section("Return",
                Div(text(entries, "issue_date", "Issue date", type="date"),
                    text(entries, "return_date", "Return date", type="date"),
                    Fieldset(Legend("or"), tick(entries, "return_until_end", "Until the end of employment / studies"),
                             tick(entries, "return_on_request", "Upon the Department's request"), cls="choices"),
                    cls="grid")),
        Fieldset(tick(entries, "lock", "Lock the fields, so the PDF can't be changed afterwards")),
        Hidden(auto_no, name="auto_no"), Hidden(auto_at.isoformat(), name="auto_at"),
        *(download(*saved) if saved else ()),
        bar(*form_problems(entries, cfg)),
        id="form", hx_post="/generate", hx_swap="outerHTML")


def download(name: str, pdf: bytes) -> tuple:
    """The finished PDF, downloaded straight away; the server keeps no copy to fetch later."""
    href = "data:application/pdf;base64," + base64.b64encode(pdf).decode()
    return (P("✓ Downloaded ", A(name, href=href, download=name, id="download"), id="saved"),
            Script("document.getElementById('download').click()"))


# ---------------------------------------------------------------------------
# This browser's memory
# ---------------------------------------------------------------------------
def remembered(req) -> dict:
    """This browser's Issuer details and last auto number; empty if it has none or the cookie can't be read."""
    try:
        memory = json.loads(unquote(req.cookies.get(MEMORY, "")))
        if memory.get("numbered_at"):
            datetime.fromisoformat(memory["numbered_at"])
        if not isinstance(memory.get("issued", 0), int):
            raise ValueError("issued is not a count")
    except (ValueError, TypeError, AttributeError):
        return {}
    return memory


def remember(memory: dict) -> object:
    return cookie(MEMORY, quote(json.dumps(memory)), max_age=365 * 24 * 3600)


def entries_from(form) -> dict:
    """What was filled in, from the submitted form: unticked boxes are simply missing from it."""
    entries = {key: value for key, value in form.items() if key not in TICK_BOXES}
    entries.update({key: key in form for key in TICK_BOXES})
    return entries


# ---------------------------------------------------------------------------
# The app
# ---------------------------------------------------------------------------
def create_app(cfg: dict, template: Path, lock: bool = False, clock=baku_now) -> FastHTML:
    # No sessions: without them FastHTML would write a .sesskey file, and Vercel's disk is read-only.
    app = FastHTML(hdrs=(PICO, Style(CSS)), surreal=False, sess_cls=None, secret_key="unused")

    def next_number(memory: dict) -> tuple[str, datetime]:
        """Number the next agreement from the current time, a minute past this browser's last auto number if needed."""
        now = clock()
        if memory.get("numbered_at"):
            now = max(now, datetime.fromisoformat(memory["numbered_at"]) + timedelta(minutes=1))
        return format_agreement_no(cfg, now, cfg["_seq_start"] + memory.get("issued", 0)), now

    @app.get("/")
    def index(req):
        memory = remembered(req)
        today = clock().date().isoformat()
        auto_no, auto_at = next_number(memory)
        entries = {"agreement_no": auto_no, "agreement_date": today, "issue_date": today, "lock": lock,
                   **{key: memory.get(key, cfg.get(key, "")) for key in ISSUER_FIELDS}}
        return Titled("UFAZ Device Issuance Agreement", form_view(entries, auto_no, auto_at, cfg))

    @app.post("/check")
    async def check(req):
        return bar(*form_problems(entries_from(await req.form()), cfg))

    @app.post("/generate")
    async def generate(req):
        form = await req.form()
        entries, memory = entries_from(form), remembered(req)
        try:
            auto_no, auto_at = form["auto_no"], datetime.fromisoformat(form["auto_at"])
        except (KeyError, ValueError):
            auto_no, auto_at = next_number(memory)
        if form_problems(entries, cfg)[0]:
            return form_view(entries, auto_no, auto_at, cfg)

        still_auto = entries.get("agreement_no", "").strip() in ("", auto_no)
        if still_auto and memory.get("numbered_at") and auto_at <= datetime.fromisoformat(memory["numbered_at"]):
            auto_no, auto_at = next_number(memory)   # this browser used that number since the page was shown
            entries["agreement_no"] = auto_no
        values, _ = row_to_fields(form_row(entries, auto_no), FORM_KEYS, cfg, 1)
        pdf = render_pdf(template, values, "lock" in form)

        if values["agreement_no"] == auto_no:
            memory["numbered_at"] = auto_at.isoformat()
        memory["issued"] = memory.get("issued", 0) + 1
        memory.update({key: entries.get(key, "") for key in ISSUER_FIELDS})
        kept = {key: entries.get(key, "") for key in KEPT_FIELDS}
        next_no, next_at = next_number(memory)
        fresh = {**kept, "agreement_no": next_no, "lock": "lock" in form}
        return form_view(fresh, next_no, next_at, cfg, saved=(pdf_filename(values, 1), pdf)), remember(memory)

    return app


def serve(cfg: dict, template: Path, lock: bool, host: str, port: int) -> None:
    """Run the Form on this computer and open it in the browser."""
    url = f"http://{'127.0.0.1' if host in ('0.0.0.0', '::') else host}:{port}"
    print(f"The Form is open at {url} — press Ctrl+C to stop.", flush=True)
    threading.Timer(1, webbrowser.open, [url]).start()
    uvicorn.run(create_app(cfg, template, lock), host=host, port=port, log_level="warning")
