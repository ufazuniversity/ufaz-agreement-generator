"""
The Form — fill in Device Issuance Agreements one at a time on screen.

Opened by running  generate  without a CSV file.  It starts with the Issuer details
from the settings, the next agreement number and today's date.  After each
agreement the receiver, device and return fields are cleared for the next one;
the Issuer details and dates stay.
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.validation import Function
from textual.widgets import Button, Checkbox, Footer, Header, Input, Label, RadioButton, RadioSet, Static

from .agreement import COLUMN_ALIASES, fill_pdf, format_agreement_no, parse_date, pdf_filename, row_to_fields

HMAP = {key: key for key in COLUMN_ALIASES}   # the Form's rows are keyed by internal key, not by CSV header
STATUSES = ["Staff", "Teacher", "Student"]
DEVICE_TYPES = ["Laptop", "Desktop PC", "Monitor", "Other"]
ACCESSORIES = ["Charger", "Bag", "Mouse", "Keyboard"]
CONDITIONS = ["New", "Good", "Used"]
DATE_FIELDS = {"agreement_date": "Date", "issue_date": "Issue date", "return_date": "Return date"}
KEPT_FIELDS = ["agreement_date", "issue_date", "issuer_name", "issuer_position", "issuer_contact"]


def open_file(path: Path) -> None:
    """Open a file in the system's default viewer."""
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606 — only exists on Windows
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def section(title: str) -> Vertical:
    box = Vertical(classes="section")
    box.border_title = title
    return box


class ConfirmReplace(ModalScreen[bool]):
    """Asks before an existing PDF is overwritten."""

    BINDINGS = [Binding("escape", "dismiss(False)", "Cancel")]

    def __init__(self, path: Path) -> None:
        super().__init__()
        self.path = path

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(f"{self.path.name} already exists.\nReplace it?")
            with Horizontal(id="choices"):
                yield Button("Replace", variant="error", id="replace")
                yield Button("Cancel", id="cancel")

    @on(Button.Pressed)
    def choose(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "replace")


class AgreementForm(App):
    """One agreement at a time: fill in, generate, and the form is ready for the next receiver."""

    TITLE = "UFAZ Device Issuance Agreement"
    # F-keys, because terminal multiplexers (zellij, tmux) take most Ctrl keys before the app sees them.
    BINDINGS = [
        Binding("f2", "generate", "Generate", priority=True),
        Binding("f3", "open_pdf", "Open last PDF", priority=True),
        Binding("f10", "quit", "Quit", priority=True),
    ]
    ENABLE_COMMAND_PALETTE = False   # its Ctrl+P is taken by zellij too, and the Form has no use for it
    CSS = """
    #form { padding: 0 1; }
    .section { height: auto; border: round $primary; border-title-style: bold; padding: 0 1; margin-bottom: 1; }
    .field { height: auto; margin-bottom: 1; }
    .field:last-child { margin-bottom: 0; }
    .field > Label { width: 24; color: $text-muted; }
    .field > Input { width: 1fr; }
    .field > Input.-invalid { background-tint: $error 40%; }
    .field > RadioSet { layout: horizontal; }
    .field > RadioSet:blur > RadioButton.-selected > .toggle--label { background: transparent; }  /* nothing looks picked until it is */
    .field > RadioSet > RadioButton, .choices > Checkbox { width: auto; margin-right: 3; }
    .choices { width: 1fr; height: auto; }
    #bar { height: auto; padding: 0 1; }
    #blocking { color: $text-error; }
    #warnings { color: $text-warning; }
    #buttons { height: auto; }
    #saved { width: 1fr; padding-top: 1; }
    #buttons > Button { margin-left: 1; }
    ConfirmReplace { align: center middle; }
    #dialog { width: 60; height: auto; border: thick $error; background: $surface; padding: 1 2; }
    #choices { height: auto; margin-top: 1; align-horizontal: right; }
    #choices > Button { margin-left: 1; }
    """

    def __init__(self, cfg: dict, template: Path, output: Path, lock: bool, clock=datetime.now) -> None:
        super().__init__()
        self.cfg, self.template, self.output, self.lock, self.clock = cfg, template, output, lock, clock
        self.sub_title = f"PDFs go to {output}"
        today = clock().strftime("%d/%m/%Y")
        self.start = {"agreement_date": today, "issue_date": today,
                      **{key: cfg.get(key, "") for key in ("issuer_name", "issuer_position", "issuer_contact")}}
        self.issued = 0            # agreements written this session; drives {seq}
        self.numbered_at = None    # time behind the last auto number used, so the next one never repeats it
        self.last_pdf: Path | None = None
        self.next_number()

    # --- layout ---------------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="form"):
            with section("Agreement"):
                yield self.text("agreement_no", "Agreement No.", value=self.auto_no)
                yield self.text("agreement_date", "Date", "DD/MM/YYYY")
            with section("Issuer"):
                yield self.text("issuer_name", "Representative")
                yield self.text("issuer_position", "Position")
                yield self.text("issuer_contact", "Phone / e-mail")
            with section("Receiver"):
                yield self.text("receiver_name", "Full name *")
                yield self.choice("receiver_status", "Status", STATUSES)
                yield self.text("receiver_id", "Employee / Student ID")
                yield self.text("receiver_faculty", "Faculty / Department")
                yield self.text("receiver_contact", "Phone / e-mail")
            with section("Device"):
                yield self.choice("device_type", "Device type", DEVICE_TYPES)
                yield self.text("device_type_other", "Other device type")
                yield self.text("device_model", "Brand & model")
                yield self.text("device_serial", "Serial / Inventory No.")
                yield Horizontal(Label("Accessories"),
                                 Horizontal(*(Checkbox(a, id=f"acc_{a.lower()}", compact=True) for a in ACCESSORIES),
                                            Checkbox("Other", id="acc_other", compact=True), classes="choices"),
                                 classes="field")
                yield self.text("acc_other_text", "Other accessory")
                yield self.choice("condition", "Condition", CONDITIONS)
                yield self.text("condition_notes", "Notes")
            with section("Return"):
                yield self.text("issue_date", "Issue date", "DD/MM/YYYY")
                yield self.text("return_date", "Return date", "DD/MM/YYYY")
                yield Horizontal(Label("or"),
                                 Vertical(Checkbox("Until the end of employment / studies", id="return_until_end", compact=True),
                                          Checkbox("Upon the Department's request", id="return_on_request", compact=True),
                                          classes="choices"),
                                 classes="field")
        with Vertical(id="bar"):
            yield Static(id="blocking", markup=False)
            yield Static(id="warnings", markup=False)
            with Horizontal(id="buttons"):
                yield Static(f"✓ Saved {self.last_pdf}" if self.last_pdf else "", id="saved", markup=False)
                if self.last_pdf:
                    yield Button("Open PDF", id="open")
                yield Button("Generate", variant="primary", id="generate")
        yield Footer()

    def text(self, key: str, label: str, placeholder: str = "", value: str | None = None) -> Horizontal:
        validators = [Function(lambda v: parse_date(v) is not None, "use DD/MM/YYYY")] if key in DATE_FIELDS else None
        return Horizontal(Label(label),
                          Input(self.start.get(key, "") if value is None else value, placeholder=placeholder, id=key,
                                validators=validators, valid_empty=True, compact=True),
                          classes="field")

    def choice(self, key: str, label: str, options: list[str]) -> Horizontal:
        return Horizontal(Label(label), RadioSet(*(RadioButton(o) for o in options), id=key, compact=True), classes="field")

    def on_mount(self) -> None:
        self.check()
        self.query_one("#receiver_name", Input).focus()

    # --- reading the form ------------------------------------------------------
    def value(self, key: str) -> str:
        return self.query_one(f"#{key}", Input).value.strip()

    def chosen(self, key: str, options: list[str]) -> str:
        index = self.query_one(f"#{key}", RadioSet).pressed_index
        return options[index] if index >= 0 else ""

    def ticked(self, key: str) -> bool:
        return self.query_one(f"#{key}", Checkbox).value

    def row(self) -> dict:
        """The form's values as a row for row_to_fields, written the way a CSV would have them."""
        row = {i.id: i.value for i in self.query(Input)}
        row["agreement_no"] = row["agreement_no"].strip() or self.auto_no
        row["receiver_status"] = self.chosen("receiver_status", STATUSES)
        row["device_type"] = self.chosen("device_type", DEVICE_TYPES)
        if row["device_type"] != "Other":
            row["device_type_other"] = ""
        row["accessories"] = ", ".join(a for a in ACCESSORIES if self.ticked(f"acc_{a.lower()}"))
        if not self.ticked("acc_other"):
            row["acc_other_text"] = ""
        row["condition"] = self.chosen("condition", CONDITIONS)
        row["return_until_end"] = "Yes" if self.ticked("return_until_end") else ""
        row["return_on_request"] = "Yes" if self.ticked("return_on_request") else ""
        return row

    def problems(self) -> tuple[list[str], list[str]]:
        """(blocking, warnings): what stops Generate, and what only deserves a second look."""
        blocking = [] if self.value("receiver_name") else ["Receiver full name is required"]
        blocking += [f"{label} is not a date — use DD/MM/YYYY" for key, label in DATE_FIELDS.items()
                     if self.value(key) and parse_date(self.value(key)) is None]
        row = self.row()
        warnings = []
        if row["device_type"] == "Other" and not row["device_type_other"].strip():
            warnings.append("describe the other device type")
        if self.ticked("acc_other") and not row["acc_other_text"].strip():
            warnings.append("describe the other accessory")
        warnings += [w for w in row_to_fields(row, HMAP, self.cfg, 1)[1] if w != "receiver name is empty"]
        return blocking, warnings

    @on(Input.Changed)
    @on(RadioSet.Changed)
    @on(Checkbox.Changed)
    def check(self) -> None:
        blocking, warnings = self.problems()
        self.query_one("#blocking", Static).update("\n".join(f"✗ {p}" for p in blocking))
        self.query_one("#warnings", Static).update("\n".join(f"! {w}" for w in warnings))
        self.query_one("#generate", Button).disabled = bool(blocking)

    @on(Input.Changed, "#device_type_other")
    def pick_other_device(self, event: Input.Changed) -> None:
        if event.value.strip():
            self.query_one("#device_type", RadioSet).query(RadioButton).last().value = True

    @on(Input.Changed, "#acc_other_text")
    def tick_other_accessory(self, event: Input.Changed) -> None:
        if event.value.strip():
            self.query_one("#acc_other", Checkbox).value = True

    # --- actions ----------------------------------------------------------------
    def check_action(self, action: str, parameters: tuple) -> bool | None:
        return not (action in ("generate", "open_pdf") and isinstance(self.screen, ModalScreen))

    def next_number(self) -> None:
        """Number the next agreement from the current time, a minute past the last auto number used if needed."""
        now = self.clock()
        if self.numbered_at is not None:
            now = max(now, self.numbered_at + timedelta(minutes=1))
        self.auto_at = now
        self.auto_no = format_agreement_no(self.cfg, now, self.cfg["_seq_start"] + self.issued)

    async def action_generate(self) -> None:
        blocking, _ = self.problems()
        if blocking:
            self.notify("\n".join(blocking), title="Not ready to generate", severity="error")
            return
        values, _ = row_to_fields(self.row(), HMAP, self.cfg, 1)
        out_path = self.output / pdf_filename(values, 1)
        kept = {key: self.value(key) for key in KEPT_FIELDS}

        async def replace(confirmed: bool | None) -> None:
            if confirmed:
                await self.write(values, out_path, kept)

        if out_path.exists():
            self.push_screen(ConfirmReplace(out_path), replace)
        else:
            await self.write(values, out_path, kept)

    async def write(self, values: dict, out_path: Path, kept: dict) -> None:
        try:
            fill_pdf(self.template, values, out_path, self.lock)
        except Exception as e:
            self.notify(str(e), title="Could not write the PDF", severity="error")
            return
        if values["agreement_no"] == self.auto_no:
            self.numbered_at = self.auto_at
        self.issued += 1
        self.last_pdf = out_path
        self.start = kept
        self.next_number()
        await self.recompose()   # a fresh form: receiver, device and return terms are cleared
        self.check()
        self.query_one("#receiver_name", Input).focus()

    # The buttons are handled here rather than with Button(action=...): an action runs inside the
    # button, and Generate rebuilds the form — removing that button while it waits on itself freezes the app.
    @on(Button.Pressed, "#generate")
    async def generate_pressed(self) -> None:
        await self.action_generate()

    @on(Button.Pressed, "#open")
    def open_pressed(self) -> None:
        self.action_open_pdf()

    def action_open_pdf(self) -> None:
        if self.last_pdf is None:
            self.notify("Generate an agreement first.", severity="warning")
            return
        try:
            open_file(self.last_pdf)
        except OSError as e:
            self.notify(str(e), title="Could not open the PDF", severity="error")
