import asyncio
import json
from datetime import datetime
from pathlib import Path

import pytest
from pypdf import PdfReader
from textual.widgets import Button, Checkbox, Input, RadioButton, RadioSet

from ufaz_agreement_generator import cli, form
from ufaz_agreement_generator.form import AgreementForm, ConfirmReplace

ROOT = Path(__file__).resolve().parents[1]
NOON = datetime(2026, 9, 17, 12, 0)


@pytest.fixture(autouse=True)
def no_local_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)   # keeps a ./config.json in the repo from changing the settings


def settings(**overrides) -> dict:
    cfg = json.loads(cli.DEFAULT_CONFIG.read_text(encoding="utf-8"))
    cfg.update({"_seq_start": 1, "_now": NOON, **overrides})
    return cfg


def fields(pdf: Path) -> dict:
    """The filled-in values of a generated PDF."""
    return {k: v.get("/V") for k, v in PdfReader(str(pdf)).get_fields().items() if v.get("/V") not in (None, "", "/Off")}


def run_form(output: Path, steps, cfg=None, clock=lambda: NOON) -> AgreementForm:
    app = AgreementForm(cfg or settings(), cli.DEFAULT_TEMPLATE, output, lock=False, clock=clock)

    async def drive():
        async with app.run_test(size=(100, 40)) as pilot:
            await steps(app, pilot)

    asyncio.run(drive())
    return app


async def fill(app, pilot, **values) -> None:
    for key, value in values.items():
        app.query_one(f"#{key}", Input).value = value
    await pilot.pause()


async def pick(app, pilot, key: str, index: int) -> None:
    app.query_one(f"#{key}", RadioSet).query(RadioButton)[index].value = True
    await pilot.pause()


async def generate(pilot) -> None:
    await pilot.press("f2")
    await pilot.pause()


# --- Batch --------------------------------------------------------------------
def test_batch_writes_one_agreement_per_row(tmp_path):
    assert cli.main([str(ROOT / "receivers_template.csv"), "-o", str(tmp_path)]) == 0
    pdfs = sorted(tmp_path.glob("*.pdf"))
    assert len(pdfs) == 2
    aysel = fields(next(p for p in pdfs if "Aysel" in p.name))
    assert aysel["receiver_status"] == "/student"
    assert aysel["issuer_contact"] == "it@ufaz.az"


def test_form_and_batch_make_the_same_pdf(tmp_path):
    csv = tmp_path / "receivers.csv"
    csv.write_text(
        "Agreement No.,Date,Receiver name,Status,ID No.,Faculty / Department,Phone / e-mail,Device type,Brand & model,"
        "Serial / Inventory No.,Accessories,Condition,Notes,Issue date,Return date,Until end of employment/studies,Upon request\n"
        '2609171200,17/09/2026,Aysel Mammadova,Student,S-1,Computer Science,a@ufaz.az,Tablet,iPad Air,SN1,'
        '"Charger, Bag, USB-C hub",Good,Scratch on lid,17/09/2026,30/06/2027,No,Yes\n', encoding="utf-8")
    assert cli.main([str(csv), "-o", str(tmp_path / "batch")]) == 0

    async def steps(app, pilot):
        await fill(app, pilot, receiver_name="Aysel Mammadova", receiver_id="S-1", receiver_faculty="Computer Science",
                   receiver_contact="a@ufaz.az", device_type_other="Tablet", device_model="iPad Air", device_serial="SN1",
                   acc_other_text="USB-C hub", condition_notes="Scratch on lid", return_date="30/06/2027")
        await pick(app, pilot, "receiver_status", 2)
        await pick(app, pilot, "condition", 1)
        for key in ("acc_charger", "acc_bag", "return_on_request"):
            app.query_one(f"#{key}", Checkbox).value = True
        await generate(pilot)

    run_form(tmp_path / "form", steps)
    [batch_pdf] = (tmp_path / "batch").glob("*.pdf")
    [form_pdf] = (tmp_path / "form").glob("*.pdf")
    assert form_pdf.name == batch_pdf.name
    assert fields(form_pdf) == fields(batch_pdf)


# --- Form ---------------------------------------------------------------------
def test_form_starts_from_the_settings(tmp_path):
    async def steps(app, pilot):
        assert app.query_one("#issuer_name", Input).value == "Aynur Aliyeva"
        assert app.query_one("#issuer_position", Input).value == "IT Specialist"
        assert app.query_one("#agreement_no", Input).value == "2609171200"
        assert app.query_one("#agreement_date", Input).value == "17/09/2026"
        assert app.query_one("#issue_date", Input).value == "17/09/2026"
        assert app.query_one("#return_date", Input).value == ""

    run_form(tmp_path, steps, cfg=settings(issuer_name="Aynur Aliyeva"))


def test_form_clears_receiver_device_and_return_but_keeps_issuer_and_dates(tmp_path):
    async def steps(app, pilot):
        await fill(app, pilot, receiver_name="Aysel Mammadova", device_model="iPad Air", return_date="30/06/2027",
                   issuer_name="Aynur Aliyeva", issue_date="16/09/2026")
        await pick(app, pilot, "receiver_status", 2)
        app.query_one("#return_until_end", Checkbox).value = True
        await generate(pilot)

        assert (tmp_path / "Agreement_2609171200_Aysel_Mammadova.pdf").exists()
        for key in ("receiver_name", "device_model", "return_date"):
            assert app.query_one(f"#{key}", Input).value == ""
        assert app.query_one("#receiver_status", RadioSet).pressed_index == -1
        assert not app.query_one("#return_until_end", Checkbox).value
        assert app.query_one("#issuer_name", Input).value == "Aynur Aliyeva"
        assert app.query_one("#issue_date", Input).value == "16/09/2026"
        # same minute on the clock, yet the next number moves on
        assert app.query_one("#agreement_no", Input).value == "2609171201"
        assert "Agreement_2609171200_Aysel_Mammadova.pdf" in str(app.query_one("#saved").render())

    run_form(tmp_path, steps)


def test_form_generate_button_writes_and_clears_the_form(tmp_path):
    async def steps(app, pilot):
        await fill(app, pilot, receiver_name="Aysel Mammadova")
        await pilot.click("#generate")
        await pilot.pause()
        assert (tmp_path / "Agreement_2609171200_Aysel_Mammadova.pdf").exists()
        assert app.query_one("#receiver_name", Input).value == ""

    run_form(tmp_path, steps)


def test_form_counts_seq_per_agreement(tmp_path):
    async def steps(app, pilot):
        assert app.query_one("#agreement_no", Input).value == "UFAZ-57"
        await fill(app, pilot, receiver_name="Aysel Mammadova")
        await generate(pilot)
        assert app.query_one("#agreement_no", Input).value == "UFAZ-58"

    run_form(tmp_path, steps, cfg=settings(agreement_no_pattern="UFAZ-{seq}", _seq_start=57))


def test_form_blocks_generate_without_a_name_or_with_a_bad_date(tmp_path):
    async def steps(app, pilot):
        button = app.query_one("#generate", Button)
        assert button.disabled
        await generate(pilot)

        await fill(app, pilot, receiver_name="Aysel Mammadova", return_date="31/02/2026")
        assert button.disabled
        assert app.query_one("#return_date", Input).has_class("-invalid")
        await generate(pilot)
        assert not list(tmp_path.glob("*.pdf"))

        await fill(app, pilot, return_date="28/02/2027")
        assert not button.disabled

    run_form(tmp_path, steps)


def test_form_shows_warnings_without_blocking(tmp_path):
    async def steps(app, pilot):
        await fill(app, pilot, receiver_name="Aysel Mammadova")
        assert "no return date" in str(app.query_one("#warnings").render())
        await generate(pilot)
        assert len(list(tmp_path.glob("*.pdf"))) == 1

    run_form(tmp_path, steps)


def test_form_asks_before_replacing_a_pdf(tmp_path):
    pdf = tmp_path / "Agreement_A-1_Aysel_Mammadova.pdf"

    async def steps(app, pilot):
        await fill(app, pilot, agreement_no="A-1", receiver_name="Aysel Mammadova", condition_notes="first")
        await generate(pilot)

        await fill(app, pilot, agreement_no="A-1", receiver_name="Aysel Mammadova", condition_notes="second")
        await generate(pilot)
        assert isinstance(app.screen, ConfirmReplace)
        await pilot.press("escape")
        await pilot.pause()
        assert fields(pdf)["condition_notes"] == "first"
        assert app.query_one("#condition_notes", Input).value == "second"   # nothing lost on cancel

        await pilot.click("#generate")
        await pilot.pause()
        await pilot.click("#replace")
        await pilot.pause()
        assert fields(pdf)["condition_notes"] == "second"
        assert app.query_one("#condition_notes", Input).value == ""

    run_form(tmp_path, steps)


def test_form_opens_the_last_pdf(tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr(form, "open_file", opened.append)

    async def steps(app, pilot):
        await fill(app, pilot, receiver_name="Aysel Mammadova")
        await generate(pilot)
        await pilot.click("#open")
        assert opened == [tmp_path / "Agreement_2609171200_Aysel_Mammadova.pdf"]

    run_form(tmp_path, steps)


# --- Command line -----------------------------------------------------------------
def test_no_csv_and_no_terminal_is_an_error():
    with pytest.raises(SystemExit, match="no terminal"):
        cli.main([])


def test_dry_run_needs_a_csv():
    with pytest.raises(SystemExit, match="--dry-run needs a CSV"):
        cli.main(["--dry-run"])
