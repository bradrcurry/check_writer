# check_printing

`check_printing` generates print-ready duplex PDFs for compact personal checks on US letter paper. It renders vector check fronts, matching backs, cut marks, registration marks, calibration pages, MICR text placement, and a local SQLite check register.

This project is for legitimate use with your own account information. Verify bank acceptance, printer output, MICR font metrics, toner requirements, check paper, and local requirements before relying on self-printed checks.

## Python Environment

Use Python 3.12.x. The project intentionally targets `>=3.12,<3.14` so it remains maintainable and can be upgraded to Python 3.13+ after dependency support is verified.

Windows:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .
```

Linux/macOS:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .
```

Required system dependencies:

- Python 3.12.x with `venv`.
- A PDF viewer that can print at 100% / Actual Size.
- A laser printer for real check output.
- Optional: a properly licensed MICR E-13B font file and MICR toner if required by your bank.

`requirements.txt` installs the full development/UI environment, including the optional
PyMuPDF PDF preview dependency. PyMuPDF is AGPL-3.0; for a core CLI/PDF-generation
install without that optional dependency, use `python -m pip install -e .` in a clean
environment instead.

## Quick Start

Create a local config:

```powershell
check-print init
```

Review `config.local.yaml` before using real data. It is ignored by Git because it may contain sensitive account information.

Generate an obvious fake sample PDF:

```powershell
check-print sample-pdf
```

Generate a calibration PDF:

```powershell
check-print calibration
```

Generate one check:

```powershell
check-print generate --payee "Duke Energy" --amount 123.45 --memo "Electric bill"
```

Generate a full blank sheet for handwriting later:

```powershell
check-print blank-sheet --start-number 1001 --output outputs/blank-checks.pdf
```

Generate a batch from CSV:

```powershell
check-print batch examples/checks.csv --output outputs/batch-checks.pdf
```

CSV columns:

- Required: `payee`, `amount`.
- Optional: `check_number`, `memo`, `date`, `written_amount`.
- Dates use `YYYY-MM-DD`.
- If `check_number` is blank, the CLI assigns the next available number from the local register.
- Duplicate register numbers are rejected unless `--reprint` is passed.

Other commands:

```powershell
check-print register
check-print void 1042 --notes "Printer jam"
check-print mark-printed 1042 --notes "Confirmed on printer"
check-print mark-cleared 1042 --cleared-date 2026-06-23 --notes "Posted by bank"
check-print export-register
```

Launch the local UI:

```powershell
streamlit run check_printing\ui.py
```

The UI uses the same YAML config, PDF generator, calibration generator, and SQLite register as the CLI.

A status banner at the top of every tab shows whether a real MICR font is loaded (vs. the Courier test fallback) and which duplex flip is active — the two settings most likely to ruin a real print run.

After any PDF is generated (single check, sheet, batch, calibration, or reprint), an inline preview renders the exact pages that will print, labeled by sheet and front/back. The preview uses PyMuPDF, an AGPL-3.0 dependency; install it with the UI extra only if those terms fit your use case:

```powershell
pip install "check-printing[ui]"
```

If PyMuPDF is not installed the rest of the UI still works and the preview area shows an install hint instead.

The UI has three tabs: **Register** (the landing view), **Write Checks**, and **Calibration**.

### Register tab (home)

- Select a row in the table to act on that exact entry (no typing check numbers).
- **Mark Printed / Mark Cleared / Void** update the selected check's status with an optional audit note.
- **Reprint Selected** generates the same check again and records a new `reprinted` row with a new PDF path/hash and audit note.
- **Use as Template** loads the selected register entry into Write Checks → Single check so you can adjust details before generating another audited row.

### Write Checks tab

A single tab with a mode toggle for the three ways to produce checks:

- **Single check** — one check, recorded in the register.
- **Six-up sheet** — a full sheet of blank checks for later handwriting, or a manually filled sheet of up to six rows.
- **From CSV** — batch generation from an uploaded CSV.

### Calibration tab (wizard)

A guided four-step flow: generate the calibration sheet, print it at 100% duplex, measure the drift in millimeters, then review and save the computed inch offsets to your config. Right/up drift is entered as positive; the wizard saves the offset that cancels it.

## Printing Guidance

- Print at 100% / Actual Size.
- Disable Fit to Page, Scale to Fit, Shrink Oversized Pages, or similar settings.
- Test on plain paper first.
- Set `duplex_flip` to match your printer driver (see below) and verify with the calibration page.
- Hold front/back calibration pages to light: each `FRONT n` must align with `BACK n`. If they land in opposite corners, switch `duplex_flip`.
- Print and measure the calibration page before printing real checks.
- Use appropriate check/security paper for real use.
- Verify output with your bank (including a MICR read / mobile-deposit scan) before relying on self-printed checks.

### Duplex flip

Duplex printers turn the page on either the long edge or the short edge. The back page must be mirrored on the matching axis so each back lands behind its front:

- `long_edge` (default) — mirrors columns. Use for long-edge / "flip on long edge" duplex.
- `short_edge` — mirrors rows. Use for short-edge / "flip on short edge" duplex.

```yaml
duplex_flip: long_edge
```

The calibration page renders with the configured flip and labels every slot, so a mismatch is visually obvious before you print real checks.

## Layouts

The default layout is `reliable_6up`. Built-in layouts:

| Layout | Check size | Grid | Notes |
| --- | --- | --- | --- |
| `reliable_6up` (default) | 5.0 x 2.5 in | rotated 3 x 2 | safe margins |
| `max_density_6up` | 5.25 x 2.625 in | rotated 3 x 2 | tighter margins |
| `large_6up` | 5.5 x 2.75 in | rotated 3 x 2 | largest 6-up that still fits; minimal vertical margin |
| `standard_3up` | 6.0 x 2.75 in | 1 x 3, **not** rotated | full personal-check size, three per sheet |

`standard_3up` matches a standard 6.0 x 2.75 in personal check, so it does not look compact — but only three fit per Letter sheet. Because it is a single column, it must use `duplex_flip: short_edge` (a single column cannot be mirrored by a long-edge flip); the UI and CLI warn if the combination cannot align.

If a check prints too small, first confirm you printed at 100% / Actual Size (use the calibration ruler to check that one printed inch measures one inch) before switching layouts — "Fit to page" scales every layout down equally.

Built-in layouts are defined in `check_printing/layout_templates.yaml`. To use custom layout templates, create a YAML file with the same shape and set `layout_templates_path` in `config.local.yaml`:

```yaml
layout: reliable_6up
layout_templates_path: C:/path/to/layout_templates.yaml
```

Template dimensions are expressed in inches:

```yaml
layouts:
  reliable_6up:
    check_width_in: 5.0
    check_height_in: 2.5
    columns: 3
    rows: 2
    rotated: true
```

## MICR Fonts

The project does not bundle a MICR font. Configure `micr_font_path` in `config.local.yaml` after reviewing the font license. Candidate fonts to evaluate include GnuMICR and other appropriately licensed MICR E-13B fonts from reputable open-source font collections.

Suggested local setup:

```yaml
micr_font_path: C:/Users/you/fonts/GnuMICR.ttf
```

For local testing, this project can use GnuMICR from `https://github.com/alerque/gnumicr`. Keep downloaded font files under `local_fonts/`, which is ignored by Git. If you redistribute the font, review and comply with its GPL-2.0 license terms, including keeping the license and source files with the font.

If no font is configured, or if the configured file does not exist, the CLI prints a warning and the generator uses Courier as a visible test fallback. That output should not be treated as bank-ready MICR. Real-world compatibility can depend on exact MICR font metrics, placement, paper, laser printer quality, toner, and bank processing rules.

The four MICR symbols (transit, on-us, amount, dash) are mapped automatically to whatever the registered font actually contains: real E-13B fonts such as GnuMICR map them onto ASCII `A B C D`, while the Courier fallback uses the Unicode MICR glyphs for visibility only. If a configured font contains none of these, generation fails rather than emitting a blank, unreadable MICR line.

### MICR clear band

The MICR line is positioned inside the ANSI X9 clear band (the bottom 5/8" of the check). The placement is configurable:

```yaml
micr:
  font_size_pt: 12.0             # ~8 CPI (E-13B pitch) with GnuMICR-compatible metrics
  baseline_from_bottom_in: 0.1875  # baseline above the check bottom edge (must be <= 0.625)
  right_margin_in: 0.25            # gap from the right reference edge
  field_order: personal            # personal (default) or business
```

Adjust these only after a test print, and confirm the line reads with your bank before relying on it.

### MICR field order and symbols

E-13B uses four symbols with specific roles (per ANSI X9.100-160):

- **Transit** `⑆` — brackets the routing number on **both** sides.
- **On-us** `⑈` — a **terminator** placed **after** each on-us value (account, serial); it is not a both-sides bracket.
- **Amount** `⑇` — brackets the amount field (left blank until the bank of first deposit encodes it).
- **Dash** `⑉` — separates parts of a number (e.g. Canadian/Mexican checks).

The arrangement differs between personal and business checks:

**`personal`** (default; standard ~6 in personal check) — the serial number lives in the on-us field, after the account number; there is no auxiliary on-us field:

```
⑆ routing ⑆   account ⑈ serial ⑈   [amount ⑇ ... ⑇]
```

**`business`** (longer business check) — the serial number is in a separate auxiliary on-us field at the far left, bracketed by on-us symbols:

```
⑈ serial ⑈   ⑆ routing ⑆   account ⑈   [amount ⑇ ... ⑇]
```

Field positions and the personal-vs-business layout are governed by ANSI X9 and your bank's spec, so confirm the exact layout against your own bank or a mobile-deposit scan before relying on either.

Before writing a PDF, the generator validates:

- Routing number: 9 digits with a valid ABA checksum.
- Account number: present.
- Check number: positive numeric value.

## Standards & Compliance

The generator targets the published check/MICR standards (ANSI X9.100-160 MICR formatting and X9.100-20 print specifications) as closely as a non-magnetic laser print allows. What the code does and does not guarantee:

**Implemented to spec**

- **MICR field order and symbols**: transit symbol brackets the routing number on both sides; the on-us symbol terminates each on-us value (account, serial). For a personal check (default) the order is routing, then account and serial in the on-us field; business checks use a separate auxiliary on-us field for the serial. The amount field is rightmost and left empty until the bank of first deposit encodes it. Configurable via `micr.field_order` (`personal` / `business`).
- **E-13B font** via a user-provided MICR font such as GnuMICR, mapped to its real symbol glyphs. The default `micr.font_size_pt` (12pt) renders GnuMICR at ~8 characters per inch, the E-13B pitch. A test guards this when the local font is available.
- **MICR clear band**: the bottom 5/8" (0.625") of the check holds only the MICR line. The check border, cut marks, memo/signature line, and "VOID AFTER" notice are kept above the band.
- **Edge clearance**: the generator rejects output if the MICR line would print within 1/8" of the left edge (use a wider layout or smaller font).
- **Check dimensions**: bank-stock checks are 6.0–8.75" wide and 2.75–3.66" tall. Only `standard_3up` (6.0 x 2.75") meets these. The compact 6-up layouts are **below** the minimum width and the app flags them as draft/handwriting layouts in the status banner and CLI.

**Not guaranteed — you must verify**

- **Magnetic ink/toner.** Without MICR (iron-oxide) toner the line is optically but not magnetically readable. This is the single biggest non-compliance for automated processing; many banks fall back to OCR but acceptance is not guaranteed.
- **Exact character positions and tolerances**, magnetic signal level, paper weight/moisture, and final bank acceptance. Confirm with a MICR gauge document or by running a test check through your bank or a mobile-deposit scan before relying on any output. This project is not a certified MICR test lab.

## Development

Run quality checks:

```powershell
ruff check .
mypy
pytest
```

CI runs Ruff, MyPy, and PyTest on Python 3.12.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).

Third-party packages and optional MICR fonts keep their own licenses. In
particular, the optional PyMuPDF preview dependency is AGPL-3.0, and GnuMICR is
GPL-licensed if you install it locally. See
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for details.

## Data Storage Warning

The local SQLite register tracks check metadata and audit history. Account and routing numbers are loaded from local configuration, not stored in register rows by default. Treat local configs and generated PDFs as sensitive files.

For generated checks and batches, the register stores the output PDF path and a SHA-256 hash of the PDF. `check-print export-register` exports register metadata as CSV, including `pdf_hash`, so printed output can be audited later.
