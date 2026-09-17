# UFAZ IT — Device Issuance Agreement generator

Generates a filled **Device Issuance Agreement** PDF for every receiver listed in a
CSV file. Each PDF is the standard one-page agreement with the receiver's
details, device details, dates and checkboxes already completed — only the three
signatures remain to be written by hand.

```
ufaz-agreement-generator/
├── pyproject.toml              package definition + `generate` command (managed by uv)
├── uv.lock                     exact pinned versions
├── receivers_template.csv      CSV to fill in (headers + 2 sample rows)
├── src/ufaz_agreement_generator/
│   ├── cli.py                  the generator
│   ├── config.json             default issuer settings + agreement-number pattern
│   └── template/
│       └── UFAZ_IT_Device_Issuance_Agreement_Fillable.pdf   the blank fillable form
└── template/source/            build_template.py + logo — regenerates the blank form if the layout changes
```

## 1. Setup (once)

Install [uv](https://docs.astral.sh/uv/). Nothing else is needed: `uvx` builds the tool, fetches
a suitable Python (3.9 or newer) and caches everything on first run.

The PDF form and default settings are bundled, so the command works from any folder.
PDFs are written to `./output` in the folder you run it from.

### Settings

The bundled defaults are in `src/ufaz_agreement_generator/config.json`. To use your own, copy
that file as `config.json` into the folder you run the command from (it is picked up
automatically), or pass `-c path/to/config.json`:

```json
{
  "issuer_name": "Gadir Rustamli",
  "issuer_position": "IT Specialist",
  "issuer_contact": "it@ufaz.az",
  "agreement_no_pattern": "{now:%y%m%d%H%M}",
  "agreement_no_start": 1,
  "prefill_signature_dates": true
}
```

* `issuer_*` are used whenever the CSV's issuer columns are empty.
* `agreement_no_pattern` numbers rows that have no agreement number. The default gives
  YYMMDDhhmm from the time you run the command (e.g. `2609171524`); each further row adds one
  minute, so numbers in a batch stay unique. Placeholders: `{now:...}` (that time, with
  [strftime codes](https://docs.python.org/3/library/datetime.html#format-codes)), `{year}`,
  `{seq}` (row counter, starting at `agreement_no_start` or `--start`), `{date}` (YYYYMMDD).
* `prefill_signature_dates` also writes the issue date into the two signature-block date fields.

## 2. Fill in the CSV

Copy `receivers_template.csv` and add one row per receiver (it has 2 sample rows to replace).
The only required column is **Receiver name**; everything else is optional.

| Column | What to enter |
|---|---|
| Agreement No. | empty = auto-number from `agreement_no_pattern` (2609171524, 2609171525, …) |
| Date | agreement date; empty = today |
| Receiver name | full name — **required** |
| Status | Staff · Teacher · Student (synonyms like *lecturer*, *employee* also work) |
| ID No. | employee or student ID |
| Faculty / Department, Phone / e-mail, Brand & model, Serial / Inventory No. | free text |
| Device type | Laptop · Desktop PC · Monitor — anything else is written to *Other* |
| Accessories | comma-separated, e.g. `Charger, Bag, USB-C hub` — Charger, Bag, Mouse and Keyboard tick their box, the rest go to *Other* |
| Condition | New · Good · Used |
| Notes | existing scratches, defects, missing parts |
| Issue date | empty = agreement date |
| Return date | leave empty if using one of the next two columns |
| Until end of employment/studies, Upon request | Yes / No |
| Issuer name, Issuer position, Issuer contact | empty = default from `config.json` |

Dates can be `16/09/2026`, `16.09.2026` or `2026-09-16`; they are printed as DD/MM/YYYY.
Values that contain a comma (like the accessories list) must be in double quotes —
spreadsheet apps do this for you when they save as CSV.

The delimiter (`,`, `;` or tab) is detected automatically. Save as UTF-8 so letters like
*ə*, *ş* and *ğ* come through; in Excel pick **CSV UTF-8 (Comma delimited)**.

Column headers are matched loosely (case, spaces and punctuation are ignored), so you can
rename them or use your own export from another system as long as the meaning is recognisable.

## 3. Generate

Point `--from` at this project folder:

```bash
uvx --from /path/to/ufaz-agreement-generator generate receivers.csv
```

Or straight from GitHub, without cloning (the repository is private, so this uses your SSH key):

```bash
uvx --from git+ssh://git@github.com/ufazuniversity/ufaz-agreement-generator generate receivers.csv
```

To keep a permanent `generate` command instead, install it once with
`uv tool install /path/to/ufaz-agreement-generator` (re-run with `--reinstall` after changes).

Output:

```
  ✓ Agreement_2609171524_Aysel_Mammadova.pdf
  ✓ Agreement_2609171525_Dr._Elvin_Hasanov.pdf

Done — 2 of 2 agreement(s) written to .../output
```

Useful options:

| Option | Effect |
|---|---|
| `-o FOLDER` | write PDFs somewhere else |
| `--lock` | make the fields read-only so the printed values can't be edited afterwards |
| `--start 57` | first `{seq}` number, for a custom `agreement_no_pattern` that uses it |
| `--dry-run` | list what would be produced and show warnings, without writing files |
| `-t FILE`, `-c FILE` | use a different template or config |
| `--help` | list all options |

Rows with problems (unknown status, missing return date, …) are reported with `!` but do
not stop the rest of the batch.

## Changing the form itself

The blank template is produced by `template/source/build_template.py` (reportlab). If the
contract wording or layout needs to change, edit that script and rebuild:

```bash
uv run --group template template/source/build_template.py src/ufaz_agreement_generator/template/UFAZ_IT_Device_Issuance_Agreement_Fillable.pdf template/source/ufaz_logo.png
```

Field names are defined there; `cli.py` refers to them by name, so keep them
unchanged (or update both files together).
