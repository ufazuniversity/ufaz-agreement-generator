# UFAZ IT — Device Issuance Agreement generator

Generates filled **Device Issuance Agreement** PDFs — for every receiver listed in a
CSV file (a *Batch*), or one at a time in an on-screen *Form* when no file is given. The
Form opens in the terminal, or as a web page in the browser (on your computer or on Vercel).
Each PDF is the standard one-page agreement with the receiver's details, device
details, dates and checkboxes already completed — only the three signatures remain
to be written by hand.

```
ufaz-agreement-generator/
├── pyproject.toml              package definition + `generate` command (managed by uv)
├── uv.lock                     exact pinned versions
├── CONTEXT.md                  glossary: Agreement, Receiver, Issuer, Batch, Form, …
├── docs/adr/                   why some decisions were made
├── receivers_template.csv      CSV to fill in (headers + 2 sample rows)
├── app.py                      entry point for Vercel: serves the Form in the browser
├── Containerfile               builds the ~60 MB image (`Dockerfile` is a link to it)
├── compose.yaml                one service: the web Form (podman compose / docker compose)
├── deploy/                     systemd unit, so Podman keeps the Form running
├── src/ufaz_agreement_generator/
│   ├── cli.py                  the `generate` command; runs a Batch or opens the Form
│   ├── agreement.py            receiver details -> filled PDF (shared by Batch and Form)
│   ├── form.py                 the Form in the terminal (Textual)
│   ├── web.py                  the Form in the browser (FastHTML)
│   ├── config.json             default issuer settings + agreement-number pattern
│   └── template/
│       └── UFAZ_IT_Device_Issuance_Agreement_Fillable.pdf   the blank fillable form
├── template/source/            build_template.py + logo — regenerates the blank template if the layout changes
└── tests/                      pytest tests for the Batch and the Form
```

## 1. Setup (once)

Install [uv](https://docs.astral.sh/uv/). Nothing else is needed: `uvx` builds the tool, fetches
a suitable Python (3.10 or newer) and caches everything on first run.

The PDF form and default settings are bundled, so the command works from any folder.
PDFs are written to `./output` in the folder you run it from.

### Settings

The bundled defaults are in `src/ufaz_agreement_generator/config.json`. They fill in Gadir
Rustamli (IT Manager) as the issuer. To use your own, copy
that file as `config.json` into the folder you run the command from (it is picked up
automatically), or pass `-c path/to/config.json`. For example:

```json
{
  "issuer_name": "Your Name",
  "issuer_position": "IT Specialist",
  "issuer_contact": "it@ufaz.az",
  "agreement_no_pattern": "{now:%y%m%d%H%M}",
  "agreement_no_start": 1,
  "prefill_signature_dates": true
}
```

* `issuer_*` are used whenever the CSV's issuer columns are empty, and pre-fill the Form.
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

Point `--from` at this project folder and give it the CSV:

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
| `--dry-run` | list what would be produced and show warnings, without writing files (CSV only) |
| `-t FILE`, `-c FILE` | use a different template or config |
| `--help` | list all options |

Rows with problems (unknown status, missing return date, …) are reported with `!` but do
not stop the rest of the batch. An existing PDF with the same name is replaced.

## 4. Or fill in one agreement at a time (the Form)

Run the same command without a CSV file:

```bash
uvx --from /path/to/ufaz-agreement-generator generate
```

A form opens in the terminal, with the same sections as the paper agreement. It starts
filled in with the issuer details from your settings, the next agreement number and
today's date — all of them can be changed.

* **F2** (or the *Generate* button) writes the PDF to `./output`.
* **F3** (or *Open PDF*) opens the last PDF in your PDF viewer, ready to print.
* **F10** quits.

The shortcuts are F-keys so they also work inside zellij or tmux, which take most Ctrl keys.

Generate stays disabled until the receiver's full name is filled in and every date is a real
date (DD/MM/YYYY). Other problems, like a missing return date, are shown in yellow above the
button but do not stop you. If the PDF already exists, the Form asks before replacing it.

After each agreement the receiver, device and return fields are cleared for the next one;
the issuer details and dates stay. Agreement numbers never repeat within a session: two
agreements made in the same minute get consecutive numbers.

`-o`, `-t`, `-c`, `--lock` and `--start` work the same as with a CSV. The Form needs a real
terminal; without one, give a CSV file or use `--web` instead.

## 5. Or fill them in in the browser

The same Form, as a web page:

```bash
uvx --from /path/to/ufaz-agreement-generator generate --web
```

It opens at <http://127.0.0.1:5001> in your browser; press Ctrl+C in the terminal to stop it.
It has the same sections, starting values and checks as the terminal Form, with a date picker
for the dates. The checks run as you type.

* **Generate** downloads the PDF in the browser. Nothing is written to `./output`, and the
  server keeps no copy. Click the file name next to *Downloaded* to download it again.
* Then the receiver, device and return fields are cleared for the next one; the issuer
  details and dates stay.
* The browser remembers the issuer details you changed and the last agreement number it used
  (in a cookie), so they are there next time, and one browser never gives the same number twice.
  Issuer details you left as they were follow `config.json`, even after it changes.
  Two different browsers generating in the same minute can get the same number, so check it
  (see `docs/adr/0001-no-shared-agreement-counter.md`).
* Tick *Lock the fields* to do what `--lock` does.
* Today's date and agreement numbers use the time in Baku, wherever the server runs.

`-t`, `-c`, `--start` and `--lock` (which ticks *Lock the fields* at the start) work as usual.
`--port 8080` picks another port; `--host 0.0.0.0` lets other computers on the network open it.

## 6. Deploy to Vercel

The repository deploys to [Vercel](https://vercel.com) as it is: Vercel reads `pyproject.toml`
and `uv.lock`, and serves `app` from `app.py`. No `vercel.json` or `requirements.txt` is needed.

1. Use a Vercel **Pro** team. The free Hobby plan can't deploy a private repository owned by
   a GitHub organization, and it is for personal, non-commercial use only.
2. In Vercel, *Add New → Project*, import `ufazuniversity/ufaz-agreement-generator` and click
   *Deploy*. Leave the build settings as they are.
3. Every push to `main` deploys again. Commit `uv.lock` whenever dependencies change: Vercel
   installs exactly what it lists.

The issuer defaults come from `src/ufaz_agreement_generator/config.json` (Gadir Rustamli). Anyone
else types their own details once, and their browser remembers them.

The production URL is open to anyone who has the link; there is no login. To limit it to
members of the Vercel team, turn on *Settings → Deployment Protection → Vercel Authentication*
for *All Deployments*.

## 7. Or run the web Form in a container

`Containerfile` builds a small image (about 60 MB; Docker counts the same image as 90 MB)
that serves the same Form on port 5001.
It works with **Podman** and with **Docker** — the same commands, one word apart:

```bash
podman build -t ufaz-agreement-form .
podman run --rm -p 5001:5001 ufaz-agreement-form
```

Open <http://127.0.0.1:5001>. Stop it with Ctrl+C.

* The container writes nothing and keeps no PDFs: each one is built in memory and downloaded
  by the browser. It runs as a normal user, not root, and works with rootless Podman.
* Because it writes nothing you can lock it down further:
  `--read-only --tmpfs /tmp --security-opt no-new-privileges`.
* To use your own issuer defaults, mount a settings file over the one the server reads:
  `-v "$PWD/config.json:/app/config.json:ro,Z"` (see [Settings](#settings)). The `,Z` is for
  SELinux hosts (Fedora, RHEL); it is harmless elsewhere.
* `-p 8080:5001` serves it on another port on your computer.
* To keep the image small it holds only what the browser Form uses: the terminal Form
  (`textual`) and Uvicorn's speed-ups are left out. The `Containerfile` says which, and the
  build stops if the server can no longer start without them.
* `Dockerfile` is a link to `Containerfile`, so `docker build .` still finds it.

### With compose

`compose.yaml` builds and runs the same service, locked down as above:

```bash
systemctl --user start podman.socket     # once per login; `podman compose` needs it
podman compose up --build -d             # or: podman-compose …, docker compose …
podman compose down
```

`podman compose` passes the work to a compose tool it finds. Docker's compose plugin reaches
Podman through that socket, and stops at *failed to connect to the docker API* without it;
`podman-compose`, if you install that one instead, needs no socket. Use `systemctl --user
enable --now podman.socket` to start it at every login.

### Keep it running with systemd (Podman)

`deploy/ufaz-agreement-form.container` is a *Quadlet* unit — a file that tells systemd to run
the container, and to start it again after a crash or a reboot:

```bash
podman build -t ufaz-agreement-form .
mkdir -p ~/.config/containers/systemd
cp deploy/ufaz-agreement-form.container ~/.config/containers/systemd/
systemctl --user daemon-reload
systemctl --user start ufaz-agreement-form
```

Check it with `systemctl --user status ufaz-agreement-form`, stop it with `systemctl --user
stop ufaz-agreement-form`; the container it runs is named `systemd-ufaz-agreement-form`. Run
`loginctl enable-linger $USER` once if it must also start when nobody is logged in.

The unit publishes the Form on `127.0.0.1:5001`, so only that computer can reach it. To let
the network in, change the `PublishPort` line to `5001:5001` and `daemon-reload` again.

## Tests

```bash
uv run pytest
```

## Changing the agreement template

The blank template is produced by `template/source/build_template.py` (reportlab). If the
contract wording or layout needs to change, edit that script and rebuild:

```bash
uv run --group template template/source/build_template.py src/ufaz_agreement_generator/template/UFAZ_IT_Device_Issuance_Agreement_Fillable.pdf template/source/ufaz_logo.png
```

Field names are defined there; `agreement.py`, `form.py` and `web.py` refer to them by name,
so keep them unchanged (or update the files together).
