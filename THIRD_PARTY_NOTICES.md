# Third-Party Notices

This project is licensed under the MIT License. It depends on third-party
packages and can optionally use third-party fonts. Those dependencies keep
their own licenses.

## Runtime Dependencies

- ReportLab: BSD-style license.
- Pydantic: MIT license.
- PyYAML: MIT license.
- Typer: MIT license.
- Click: BSD-3-Clause license.

## Optional UI/Preview Dependencies

- Streamlit: Apache-2.0 license.
- PyMuPDF: GNU Affero General Public License v3.0.

PyMuPDF is used only for local PDF preview rendering in the Streamlit UI. The
core CLI/PDF generation path does not require PyMuPDF. `requirements.txt`
installs the full development/UI environment and therefore includes PyMuPDF; a
core install from `pyproject.toml` does not include it unless the `ui` extra is
selected. If AGPL dependency terms are not acceptable for your use case, do not
install the UI extra/full requirements file, or replace the preview renderer
with a dependency whose license fits your distribution requirements.

## Optional Font/Image Tooling

- FontTools: MIT license.
- Pillow: HPND license.

## Development Dependencies

- Pytest: MIT license.
- pytest-cov: MIT license.
- Ruff: MIT license.
- MyPy: MIT license.
- pre-commit: MIT license.
- types-PyYAML: Apache-2.0 license.

## MICR Fonts

This repository does not bundle a MICR font. Users provide a local MICR E-13B
font path in `config.local.yaml`.

GnuMICR is one candidate font for local testing. It is distributed under the
GNU General Public License, and downloaded copies should remain outside this
repository under `local_fonts/`, which is ignored by Git. If you redistribute
GnuMICR or another MICR font, review and comply with that font's license,
including any requirement to include license and source files.

## Generated Output and Local Data

Generated PDFs, local SQLite registers, local font downloads, and
`config.local.yaml` may contain sensitive account information. They are ignored
by Git and are not part of this project's license grant.
