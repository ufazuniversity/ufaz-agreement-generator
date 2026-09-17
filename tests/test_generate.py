import asyncio
import base64
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import pytest
from bs4 import BeautifulSoup
from fasthtml.common import Client
from pypdf import PdfReader
from textual.widgets import Button, Checkbox, Input, RadioButton, RadioSet

from ufaz_agreement_generator import cli, form, web
from ufaz_agreement_generator.form import AgreementForm, ConfirmReplace

ROOT = Path(__file__).resolve().parents[1]
NOON = datetime(2026, 9, 17, 12, 0)
AYSEL_CSV = (
    "Agreement No.,Date,Receiver name,Status,ID No.,Faculty / Department,Phone / e-mail,Device type,Brand & model,"
    "Serial / Inventory No.,Accessories,Condition,Notes,Issue date,Return date,Until end of employment/studies,Upon request\n"
    '2609171200,17/09/2026,Aysel Mammadova,Student,S-1,Computer Science,a@ufaz.az,Tablet,iPad Air,SN1,'
    '"Charger, Bag, USB-C hub",Good,Scratch on lid,17/09/2026,30/06/2027,No,Yes\n')


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
    assert aysel["issuer_contact"] == "+994125990074 ext:320 g.rustamli@ufaz.az"


def test_form_and_batch_make_the_same_pdf(tmp_path):
    csv = tmp_path / "receivers.csv"
    csv.write_text(AYSEL_CSV, encoding="utf-8")
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
        assert app.query_one("#issuer_position", Input).value == "IT Manager"
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


# --- Form in the browser ------------------------------------------------------
def browser(cfg=None, clock=lambda: NOON, lock=False) -> Client:
    return Client(web.create_app(cfg or settings(), cli.DEFAULT_TEMPLATE, lock, clock=clock))


def page(response) -> BeautifulSoup:
    assert response.status_code == 200
    return BeautifulSoup(response.text, "html.parser")


def shown(soup: BeautifulSoup) -> dict:
    """What the page's form holds, sent the way a browser sends it: only ticked boxes and the picked choice."""
    data = {}
    for i in soup.select("#form input"):
        if i.get("type") not in ("radio", "checkbox"):
            data[i["name"]] = i.get("value", "")
        elif i.has_attr("checked"):
            data[i["name"]] = i.get("value", "on")
    return data


def submit(client: Client, soup: BeautifulSoup, **changes) -> BeautifulSoup:
    return page(client.post("/generate", data={**shown(soup), **changes}))


def downloaded(soup: BeautifulSoup, folder: Path) -> Path:
    """The PDF the page handed to the browser, saved under its download name."""
    link = soup.select_one("#download")
    pdf = folder / link["download"]
    pdf.write_bytes(base64.b64decode(link["href"].split(",", 1)[1]))
    return pdf


def test_browser_form_starts_from_the_settings():
    values = shown(page(browser(settings(issuer_name="Aynur Aliyeva")).get("/")))
    assert values["issuer_name"] == "Aynur Aliyeva"
    assert values["issuer_position"] == "IT Manager"
    assert values["agreement_no"] == "2609171200"
    assert values["agreement_date"] == values["issue_date"] == "2026-09-17"
    assert values["return_date"] == ""
    assert "lock" not in values


def test_browser_form_and_batch_make_the_same_pdf(tmp_path):
    csv = tmp_path / "receivers.csv"
    csv.write_text(AYSEL_CSV, encoding="utf-8")
    assert cli.main([str(csv), "-o", str(tmp_path / "batch")]) == 0

    client = browser()
    done = submit(client, page(client.get("/")), receiver_name="Aysel Mammadova", receiver_status="Student",
                  receiver_id="S-1", receiver_faculty="Computer Science", receiver_contact="a@ufaz.az",
                  device_type="Other", device_type_other="Tablet", device_model="iPad Air", device_serial="SN1",
                  acc_charger="on", acc_bag="on", acc_other="on", acc_other_text="USB-C hub", condition="Good",
                  condition_notes="Scratch on lid", return_date="2027-06-30", return_on_request="on")
    (tmp_path / "browser").mkdir()
    browser_pdf = downloaded(done, tmp_path / "browser")
    [batch_pdf] = (tmp_path / "batch").glob("*.pdf")
    assert browser_pdf.name == batch_pdf.name
    assert fields(browser_pdf) == fields(batch_pdf)


def test_browser_form_clears_receiver_device_and_return_but_keeps_issuer_and_dates():
    client = browser()
    done = submit(client, page(client.get("/")), receiver_name="Aysel Mammadova", receiver_status="Student",
                  device_model="iPad Air", return_date="2027-06-30", return_until_end="on",
                  issuer_name="Aynur Aliyeva", issue_date="2026-09-16", lock="on")
    assert done.select_one("#download")["download"] == "Agreement_2609171200_Aysel_Mammadova.pdf"
    values = shown(done)
    for key in ("receiver_name", "device_model", "return_date"):
        assert values[key] == ""
    assert "receiver_status" not in values and "return_until_end" not in values
    assert values["issuer_name"] == "Aynur Aliyeva"
    assert values["issue_date"] == "2026-09-16"
    assert values["lock"] == "on"
    # same minute on the clock, yet the next number moves on
    assert values["agreement_no"] == "2609171201"


def test_browser_remembers_the_issuer_and_never_repeats_its_numbers():
    client = browser()
    other_tab = page(client.get("/"))
    submit(client, page(client.get("/")), receiver_name="Aysel Mammadova", issuer_name="Aynur Aliyeva")

    reopened = shown(page(client.get("/")))
    assert reopened["issuer_name"] == "Aynur Aliyeva"
    assert reopened["agreement_no"] == "2609171201"
    # a page shown before that agreement still offered 2609171200: it gets the next free number instead
    done = submit(client, other_tab, receiver_name="Elvin Hasanov")
    assert done.select_one("#download")["download"] == "Agreement_2609171201_Elvin_Hasanov.pdf"
    # a number typed in by hand is used as it is
    done = submit(client, page(client.get("/")), agreement_no="2609171200", receiver_name="Leyla Guliyeva")
    assert done.select_one("#download")["download"] == "Agreement_2609171200_Leyla_Guliyeva.pdf"


def test_browser_follows_the_settings_for_issuer_details_it_left_alone():
    before = browser(settings(issuer_position="IT Specialist"))
    submit(before, page(before.get("/")), receiver_name="Aysel Mammadova", issuer_name="Aynur Aliyeva")

    after = browser()   # the settings changed since
    after.cli.cookies.update(before.cli.cookies)
    reopened = shown(page(after.get("/")))
    assert reopened["issuer_name"] == "Aynur Aliyeva"
    assert reopened["issuer_position"] == "IT Manager"


def test_browser_form_ignores_issuer_details_remembered_by_an_older_version():
    client = browser()
    client.cli.cookies.set(web.MEMORY, quote(json.dumps({
        "issuer_name": "", "issuer_position": "IT Specialist", "issuer_contact": "it@ufaz.az",
        "numbered_at": "2026-09-17T12:00:00", "issued": 1})))
    values = shown(page(client.get("/")))
    assert [values[key] for key in web.ISSUER_FIELDS] == [settings()[key] for key in web.ISSUER_FIELDS]
    assert values["agreement_no"] == "2609171201"


def test_browser_form_ignores_an_unreadable_memory():
    client = browser(settings(issuer_name="Aynur Aliyeva"))
    client.cli.cookies.set(web.MEMORY, "not json")
    assert shown(page(client.get("/")))["issuer_name"] == "Aynur Aliyeva"


def test_browser_form_blocks_generate_without_a_name_or_with_a_bad_date():
    client = browser()
    bar = page(client.post("/check", data={"receiver_name": ""}))
    assert bar.select_one("button").has_attr("disabled")
    assert "Receiver full name is required" in bar.text

    refused = submit(client, page(client.get("/")), receiver_name="Aysel Mammadova", return_date="2026-02-31")
    assert refused.select_one("#download") is None
    assert "Return date is not a date" in refused.text
    assert shown(refused)["receiver_name"] == "Aysel Mammadova"   # nothing lost

    bar = page(client.post("/check", data={"receiver_name": "Aysel Mammadova", "return_date": "2027-02-28"}))
    assert not bar.select_one("button").has_attr("disabled")


def test_browser_form_shows_warnings_without_blocking(tmp_path):
    client = browser()
    bar = page(client.post("/check", data={"receiver_name": "Aysel Mammadova"}))
    assert "no return date" in bar.text
    assert not bar.select_one("button").has_attr("disabled")
    assert downloaded(submit(client, page(client.get("/")), receiver_name="Aysel Mammadova"), tmp_path).exists()


def test_browser_form_locks_the_fields_when_ticked(tmp_path):
    client = browser()
    locked = downloaded(submit(client, page(client.get("/")), receiver_name="Aysel Mammadova", lock="on"), tmp_path)
    assert int(PdfReader(str(locked)).get_fields()["receiver_name"].get("/Ff", 0)) & 1


def test_browser_form_uses_the_time_in_baku():
    assert abs(web.baku_now() - (datetime.now(timezone.utc) + timedelta(hours=4)).replace(tzinfo=None)) < timedelta(minutes=1)


# --- Command line -----------------------------------------------------------------
def test_web_with_a_csv_is_an_error():
    with pytest.raises(SystemExit, match="--web"):
        cli.main(["receivers.csv", "--web"])


def test_no_csv_and_no_terminal_is_an_error():
    with pytest.raises(SystemExit, match="no terminal"):
        cli.main([])


def test_dry_run_needs_a_csv():
    with pytest.raises(SystemExit, match="--dry-run needs a CSV"):
        cli.main(["--dry-run"])
