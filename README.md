# UFAZ IT — Device Issuance Agreement generator

Generates a filled **Device Issuance Agreement** PDF for every receiver listed in an
Excel or CSV file. Each PDF is the standard one-page agreement with the receiver's
details, device details, dates and checkboxes already completed — only the three
signatures remain to be written by hand.

```
ufaz-agreement-generator/
├── generate_agreements.py      the script
├── config.json                 issuer defaults + agreement-number pattern
├── receivers_template.xlsx     spreadsheet to fill in (with dropdowns and 2 sample rows)
├── pyproject.toml              dependencies (managed by uv)
├── uv.lock                     exact pinned versions
├── template/
│   ├── UFAZ_IT_Device_Issuance_Agreement_Fillable.pdf   the blank fillable form
│   └── source/                 build_template.py + logo — regenerates the blank form if the layout changes
└── output/                     generated PDFs land here
```

## 1. Setup (once)

Install [uv](https://docs.astral.sh/uv/). Then, in this folder:

```bash
uv sync
```

This creates `.venv/` and installs the pinned dependencies. uv also fetches a suitable
Python (3.9 or newer) if you don't have one.

Open `config.json` and set the defaults for your department:

```json
{
  "issuer_name": "Gadir Rustamli",
  "issuer_position": "IT Specialist",
  "issuer_contact": "it@ufaz.az",
  "agreement_no_pattern": "IT-{year}-{seq:03d}",
  "agreement_no_start": 1,
  "prefill_signature_dates": true
}
```

* `issuer_*` are used whenever the spreadsheet's issuer columns are empty.
* `agreement_no_pattern` numbers rows that have no agreement number. Placeholders: `{year}`,
  `{seq}` (row counter, starting at `agreement_no_start` or `--start`), `{date}` (YYYYMMDD).
* `prefill_signature_dates` also writes the issue date into the two signature-block date fields.

## 2. Fill in the spreadsheet

Open `receivers_template.xlsx`, one row per receiver. The **"How to fill"** sheet describes
every column. The only required column is **Receiver name**; everything else is optional.

| Column | Accepted values |
|---|---|
| Status | Staff · Teacher · Student (synonyms like *lecturer*, *employee* also work) |
| Device type | Laptop · Desktop PC · Monitor — anything else is written to *Other* |
| Accessories | comma-separated, e.g. `Charger, Bag, USB-C hub` — known items tick their box, the rest go to *Other* |
| Condition | New · Good · Used |
| Dates | real Excel dates or text (`16/09/2026`, `2026-09-16`); printed as DD/MM/YYYY |
| Until end of employment/studies, Upon request | Yes / No |

Column headers are matched loosely (case, spaces and punctuation are ignored), so you can
rename them or use your own export from another system as long as the meaning is recognisable.
A CSV with the same headers works too.

## 3. Generate

```bash
uv run generate_agreements.py receivers_template.xlsx
```

Output:

```
  ✓ Agreement_IT-2026-001_Aysel_Mammadova.pdf
  ✓ Agreement_IT-2026-002_Dr._Elvin_Hasanov.pdf

Done — 2 of 2 agreement(s) written to .../output
```

Useful options:

| Option | Effect |
|---|---|
| `-o FOLDER` | write PDFs somewhere else |
| `--lock` | make the fields read-only so the printed values can't be edited afterwards |
| `--start 57` | first sequence number for auto-generated agreement numbers |
| `--sheet NAME` | use a specific worksheet |
| `--dry-run` | list what would be produced and show warnings, without writing files |
| `-t FILE`, `-c FILE` | use a different template or config |

Rows with problems (unknown status, missing return date, …) are reported with `!` but do
not stop the rest of the batch.

## Changing the form itself

The blank template is produced by `template/source/build_template.py` (reportlab). If the
contract wording or layout needs to change, edit that script and rebuild:

```bash
uv run --group template template/source/build_template.py template/UFAZ_IT_Device_Issuance_Agreement_Fillable.pdf template/source/ufaz_logo.png
```

Field names are defined there; `generate_agreements.py` refers to them by name, so keep them
unchanged (or update both files together).
