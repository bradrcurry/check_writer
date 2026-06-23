from __future__ import annotations

from collections.abc import Callable
from datetime import date as dt_date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, cast

import streamlit as st

from check_printing.calibration import generate_calibration_pdf
from check_printing.cli import (
    _ensure_register_numbers_available,
    _next_check_number,
    blank_checks,
    load_checks_csv,
)
from check_printing.config import DEFAULT_CONFIG_PATH, load_config, save_config
from check_printing.files import sha256_file
from check_printing.micr import (
    MicrFieldOrder,
    MicrFontRegistration,
    MicrSymbolMap,
    register_micr_font,
)
from check_printing.models import (
    AccountProfile,
    AppConfig,
    BackgroundStyle,
    Calibration,
    Check,
    CheckStatus,
    DuplexFlip,
    MicrSettings,
    PatternSettings,
)
from check_printing.pdf_generator import prepare_checks_pdf, write_checks_pdf
from check_printing.preview import (
    PREVIEW_UNAVAILABLE_MESSAGE,
    preview_available,
    render_pdf_to_pngs,
)
from check_printing.routing_directory import (
    FED_SEARCH_URL,
    RoutingDirectoryEntry,
    load_routing_directory,
    lookup_routing_number,
    search_bank_name,
)
from check_printing.storage import CheckRegister, RegisterEntry
from check_printing.templates import Layout, get_layout, load_layouts


def main() -> None:
    st.set_page_config(page_title="check_printing", layout="wide")
    st.title("check_printing")

    config_path = Path(st.sidebar.text_input("Config path", value=str(DEFAULT_CONFIG_PATH)))
    st.session_state["config_path"] = str(config_path)
    config = _load_or_default(config_path)
    edited_config = _render_config_sidebar(config, config_path)

    _render_status_banner(edited_config)

    tabs = st.tabs(["Register", "Write Checks", "Calibration"])
    with tabs[0]:
        _render_register_tab(edited_config)
    with tabs[1]:
        _render_write_checks_tab(edited_config)
    with tabs[2]:
        _render_calibration_tab(edited_config)


WRITE_MODES = ("Single check", "Six-up sheet", "From CSV")


def _render_write_checks_tab(config: AppConfig) -> None:
    # "Use as Template" from the Register tab pre-sets st.session_state["write-mode"]
    # to "Single check"; otherwise the radio defaults to the first option.
    mode = st.radio(
        "What do you want to print?",
        options=WRITE_MODES,
        horizontal=True,
        key="write-mode",
    )
    st.divider()
    if mode == "Single check":
        _render_generate_tab(config)
    elif mode == "Six-up sheet":
        _render_sheet_tab(config)
    else:
        _render_batch_tab(config)


def _render_status_banner(config: AppConfig) -> None:
    """Surface the settings most likely to ruin a real print run."""
    micr_col, duplex_col = st.columns(2)

    registration = register_micr_font(config.micr_font_path, config.micr.symbol_map)
    if registration.warning:
        micr_col.warning(f"MICR: {registration.warning}", icon="⚠️")
    else:
        micr_col.success(f"MICR font loaded ({registration.font_name})", icon="✅")

    flip_warning = _duplex_flip_warning(config)
    if flip_warning:
        duplex_col.warning(f"Duplex flip: **{config.duplex_flip.value}** — {flip_warning}", icon="⚠️")
    else:
        duplex_col.info(
            f"Duplex flip: **{config.duplex_flip.value}** — verify with the Calibration page.",
            icon="🔁",
        )

    layout = _layout_or_none(config)
    if layout is None:
        return
    size_warning = layout.dimension_warning()
    if size_warning:
        st.warning(f"Layout **{config.layout}**: {size_warning}", icon="📏")
    else:
        st.success(
            f"Layout **{config.layout}** is ANSI bank-spec size "
            f"({layout.check_width_in:.2f} x {layout.check_height_in:.2f} in).",
            icon="📏",
        )


def _layout_or_none(config: AppConfig) -> Layout | None:
    try:
        return get_layout(config.layout, config.layout_templates_path)
    except Exception:
        return None


def _duplex_flip_warning(config: AppConfig) -> str | None:
    layout = _layout_or_none(config)
    if layout is None:
        return None
    return layout.duplex_flip_warning(config.duplex_flip.value)


def _load_or_default(config_path: Path) -> AppConfig:
    try:
        return load_config(config_path)
    except Exception as exc:
        st.sidebar.error(str(exc))
        return AppConfig()


def _render_config_sidebar(config: AppConfig, config_path: Path) -> AppConfig:
    st.sidebar.header("Profile")
    _init_profile_state(config)
    account_id = st.sidebar.text_input("Account ID", key="profile_account_id")
    payor_name = st.sidebar.text_input("Payor name", key="profile_payor_name")
    payor_address = st.sidebar.text_area(
        "Payor address",
        key="profile_payor_address",
        height=70,
    )
    bank_name = st.sidebar.text_input("Bank name", key="profile_bank_name")
    bank_address = st.sidebar.text_area(
        "Bank address",
        key="profile_bank_address",
        height=70,
    )
    routing_number = st.sidebar.text_input("Routing number", key="profile_routing_number")
    account_number = st.sidebar.text_input("Account number", key="profile_account_number")
    fractional = st.sidebar.text_input(
        "Fractional routing",
        key="profile_fractional_routing",
    )
    routing_directory_path = _path_or_none(
        st.sidebar.text_input(
            "Routing directory path",
            value=str(config.routing_directory_path or ""),
            help="Optional local FedACH fixed-width file or CSV for bank lookup.",
        )
    )
    _render_routing_lookup(config, routing_directory_path)

    st.sidebar.header("Template")
    layout_templates_path_text = st.sidebar.text_input(
        "Layout templates path",
        value=str(config.layout_templates_path or ""),
    )
    layout_templates_path = _path_or_none(layout_templates_path_text)
    layout_names = _layout_names(layout_templates_path)
    layout = st.sidebar.selectbox(
        "Layout",
        options=layout_names,
        index=layout_names.index(config.layout) if config.layout in layout_names else 0,
    )
    flip_values = [flip.value for flip in DuplexFlip]
    duplex_flip = st.sidebar.selectbox(
        "Duplex flip",
        options=flip_values,
        index=flip_values.index(config.duplex_flip.value),
        help="Must match your printer driver's duplex setting. Verify with the calibration page.",
    )

    st.sidebar.header("Output")
    output_dir = Path(st.sidebar.text_input("Output directory", value=str(config.output_dir)))
    database_path = Path(st.sidebar.text_input("Database path", value=str(config.database_path)))
    micr_font_path = _path_or_none(
        st.sidebar.text_input("MICR font path", value=str(config.micr_font_path or ""))
    )
    with st.sidebar.expander("Advanced MICR"):
        micr_font_size = st.number_input(
            "MICR font size",
            min_value=1.0,
            max_value=24.0,
            value=config.micr.font_size_pt,
            step=0.25,
            help="12pt is calibrated for GnuMICR-compatible metrics at roughly 8 CPI.",
        )
        micr_baseline = st.number_input(
            "MICR baseline from bottom",
            min_value=0.0,
            max_value=0.625,
            value=config.micr.baseline_from_bottom_in,
            step=0.01,
            help="Must stay inside the bottom 5/8 inch clear band.",
        )
        micr_right_margin = st.number_input(
            "MICR right margin",
            min_value=0.0,
            max_value=1.0,
            value=config.micr.right_margin_in,
            step=0.01,
        )
        field_order_values = [order.value for order in MicrFieldOrder]
        micr_field_order = st.selectbox(
            "MICR field order",
            options=field_order_values,
            index=field_order_values.index(config.micr.field_order.value),
        )
        symbol_map_values = [symbol_map.value for symbol_map in MicrSymbolMap]
        micr_symbol_map = st.selectbox(
            "MICR symbol map",
            options=symbol_map_values,
            index=symbol_map_values.index(config.micr.symbol_map.value),
        )

    st.sidebar.header("Calibration")
    front_x = st.sidebar.number_input("Front X offset", value=config.calibration.front_x_offset_in)
    front_y = st.sidebar.number_input("Front Y offset", value=config.calibration.front_y_offset_in)
    back_x = st.sidebar.number_input("Back X offset", value=config.calibration.back_x_offset_in)
    back_y = st.sidebar.number_input("Back Y offset", value=config.calibration.back_y_offset_in)

    st.sidebar.header("Background")
    style_values = [style.value for style in BackgroundStyle]
    style = st.sidebar.selectbox(
        "Pattern",
        options=style_values,
        index=style_values.index(config.pattern.style.value),
    )
    intensity = st.sidebar.slider(
        "Intensity",
        min_value=0.0,
        max_value=0.20,
        value=config.pattern.intensity,
        step=0.01,
    )

    edited = AppConfig(
        account=AccountProfile(
            account_id=account_id,
            payor_name=payor_name,
            payor_address=_lines(payor_address),
            bank_name=bank_name,
            bank_address=_lines(bank_address),
            routing_number=routing_number,
            account_number=account_number,
            fractional_routing_number=fractional or None,
            void_after_days=config.account.void_after_days,
        ),
        micr_font_path=micr_font_path,
        micr=MicrSettings(
            font_size_pt=float(micr_font_size),
            baseline_from_bottom_in=float(micr_baseline),
            right_margin_in=float(micr_right_margin),
            field_order=MicrFieldOrder(str(micr_field_order)),
            symbol_map=MicrSymbolMap(str(micr_symbol_map)),
        ),
        layout=str(layout),
        layout_templates_path=layout_templates_path,
        routing_directory_path=routing_directory_path,
        duplex_flip=DuplexFlip(str(duplex_flip)),
        output_dir=output_dir,
        database_path=database_path,
        fake_test_mode=config.fake_test_mode,
        calibration=Calibration(
            front_x_offset_in=float(front_x),
            front_y_offset_in=float(front_y),
            back_x_offset_in=float(back_x),
            back_y_offset_in=float(back_y),
        ),
        pattern=PatternSettings(style=BackgroundStyle(str(style)), intensity=float(intensity)),
    )

    if st.sidebar.button("Save config"):
        try:
            save_config(edited, config_path)
            st.sidebar.success(f"Saved {config_path}")
        except Exception as exc:
            st.sidebar.error(str(exc))
    return edited


def _init_profile_state(config: AppConfig) -> None:
    defaults = {
        "profile_account_id": config.account.account_id,
        "profile_payor_name": config.account.payor_name,
        "profile_payor_address": "\n".join(config.account.payor_address),
        "profile_bank_name": config.account.bank_name,
        "profile_bank_address": "\n".join(config.account.bank_address),
        "profile_routing_number": config.account.routing_number,
        "profile_account_number": config.account.account_number,
        "profile_fractional_routing": config.account.fractional_routing_number or "",
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def _render_routing_lookup(config: AppConfig, routing_directory_path: Path | None) -> None:
    with st.sidebar.expander("Routing lookup"):
        st.caption(
            "Search a local FedACH fixed-width file or CSV. Verify the selected routing "
            "number with your bank before printing checks."
        )
        st.link_button("Open Federal Reserve directory", FED_SEARCH_URL)
        if routing_directory_path is None:
            st.info("Set Routing directory path to enable local search.")
            return
        try:
            entries = load_routing_directory(routing_directory_path)
        except Exception as exc:
            st.warning(str(exc))
            return

        st.caption(f"Loaded {len(entries):,} routing entries.")
        if st.button("Find current routing number"):
            matches = lookup_routing_number(entries, str(st.session_state["profile_routing_number"]))
            st.session_state["routing_lookup_matches"] = matches
            st.session_state["routing_lookup_mode"] = "routing"
        name_query = st.text_input(
            "Search bank name",
            value=str(st.session_state.get("profile_bank_name", config.account.bank_name)),
            key="routing_lookup_name_query",
        )
        if st.button("Search bank name"):
            st.session_state["routing_lookup_matches"] = search_bank_name(entries, name_query)
            st.session_state["routing_lookup_mode"] = "name"
        _render_routing_matches()


def _render_routing_matches() -> None:
    matches = cast(
        list[RoutingDirectoryEntry],
        st.session_state.get("routing_lookup_matches", []),
    )
    if "routing_lookup_matches" not in st.session_state:
        return
    if not matches:
        st.warning("No routing directory matches found.")
        return
    selected_label = st.selectbox(
        "Matching routing numbers",
        options=[entry.label for entry in matches],
        key="routing_lookup_selected_label",
    )
    selected = matches[[entry.label for entry in matches].index(str(selected_label))]
    st.write(
        {
            "routing_number": selected.routing_number,
            "bank_name": selected.customer_name,
            "address": selected.address,
            "city": selected.city,
            "state": selected.state,
            "zip": selected.zip_code,
            "phone": selected.phone,
        }
    )
    if st.button("Apply selected bank"):
        _apply_routing_entry(selected)


def _apply_routing_entry(entry: RoutingDirectoryEntry) -> None:
    st.session_state["profile_routing_number"] = entry.routing_number
    st.session_state["profile_bank_name"] = entry.customer_name
    st.session_state["profile_bank_address"] = "\n".join(entry.bank_address_lines)
    st.success("Applied selected bank fields. Save config to persist them.")
    st.rerun()


def _render_generate_tab(config: AppConfig) -> None:
    defaults = _generate_defaults(config)
    with st.form("generate-check"):
        col_a, col_b, col_c = st.columns(3)
        payee = col_a.text_input("Payee", value=str(defaults["payee"]))
        amount_text = col_b.text_input("Amount", value=str(defaults["amount"]))
        check_number_text = col_c.text_input("Check number", value=str(defaults["check_number"]))
        check_date = cast(dt_date, st.date_input("Date", value=cast(dt_date, defaults["date"])))
        memo = st.text_input("Memo", value=str(defaults["memo"]))
        output_path = st.text_input("Output PDF", value=str(defaults["output_path"]))
        reprint = st.checkbox("Reprint", value=bool(defaults["reprint"]))
        submitted = st.form_submit_button("Generate PDF")

    if submitted:
        try:
            register = CheckRegister(config.database_path)
            check_number = (
                int(check_number_text)
                if check_number_text.strip()
                else _next_check_number(register, config.account.account_id)
            )
            check = Check(
                check_number=check_number,
                payee=payee,
                amount=_parse_decimal(amount_text),
                date=check_date,
                memo=memo,
            )
            _ensure_register_numbers_available(
                register, config.account.account_id, [check], allow_reprint=reprint
            )
            _generate_and_record([check], config, Path(output_path), register, reprint)
            _clear_generate_defaults()
            _show_download(Path(output_path))
        except Exception as exc:
            st.error(str(exc))


def _render_batch_tab(config: AppConfig) -> None:
    with st.form("batch-checks"):
        uploaded = st.file_uploader("CSV file", type=["csv"])
        output_path = st.text_input("Output PDF", value=str(config.output_dir / "batch-checks.pdf"))
        reprint = st.checkbox("Allow reprints")
        submitted = st.form_submit_button("Generate batch")

    if submitted:
        if uploaded is None:
            st.error("CSV file is required")
            return
        try:
            register = CheckRegister(config.database_path)
            with NamedTemporaryFile("wb", suffix=".csv", delete=False) as handle:
                handle.write(uploaded.getbuffer())
                csv_path = Path(handle.name)
            try:
                checks = load_checks_csv(csv_path, register, config.account.account_id)
            finally:
                csv_path.unlink(missing_ok=True)
            _ensure_register_numbers_available(
                register, config.account.account_id, checks, allow_reprint=reprint
            )
            _generate_and_record(checks, config, Path(output_path), register, reprint)
            _show_download(Path(output_path))
        except Exception as exc:
            st.error(str(exc))


def _render_sheet_tab(config: AppConfig) -> None:
    register = CheckRegister(config.database_path)
    st.subheader("Blank Sheet")
    with st.form("blank-sheet"):
        start_number_text = st.text_input(
            "First check number",
            value=str(_next_check_number(register, config.account.account_id)),
        )
        blank_output = st.text_input(
            "Blank sheet PDF",
            value=str(config.output_dir / "blank-checks.pdf"),
        )
        blank_reprint = st.checkbox("Allow blank sheet reprint")
        blank_submitted = st.form_submit_button("Generate 6 Blank Checks")

    if blank_submitted:
        try:
            first_number = int(start_number_text)
            checks = blank_checks(first_number)
            _ensure_register_numbers_available(
                register, config.account.account_id, checks, allow_reprint=blank_reprint
            )
            _generate_and_record(
                checks,
                config,
                Path(blank_output),
                register,
                allow_reprint=blank_reprint,
                notes="Printed as blank check stock",
            )
            _show_download(Path(blank_output))
        except Exception as exc:
            st.error(str(exc))

    st.subheader("Manual Sheet")
    rows = []
    next_number = _next_check_number(register, config.account.account_id)
    for index in range(6):
        rows.append(
            {
                "include": index == 0,
                "check_number": next_number + index,
                "payee": "",
                "amount": "0.00",
                "date": dt_date.today().isoformat(),
                "memo": "",
            }
        )
    edited_rows = st.data_editor(
        rows,
        hide_index=True,
        use_container_width=True,
        num_rows="fixed",
        key="manual-sheet-editor",
    )
    manual_output = st.text_input(
        "Manual sheet PDF",
        value=str(config.output_dir / "manual-check-sheet.pdf"),
    )
    manual_reprint = st.checkbox("Allow manual sheet reprints")
    if st.button("Generate Manual Sheet"):
        try:
            checks = _checks_from_manual_rows(edited_rows)
            if not checks:
                raise ValueError("Select at least one row to print")
            _ensure_register_numbers_available(
                register, config.account.account_id, checks, allow_reprint=manual_reprint
            )
            _generate_and_record(
                checks,
                config,
                Path(manual_output),
                register,
                allow_reprint=manual_reprint,
            )
            _show_download(Path(manual_output))
        except Exception as exc:
            st.error(str(exc))


MM_PER_INCH = 25.4


def _drift_mm_to_offset_in(drift_mm: float) -> float:
    """Convert measured drift (mm) into the inch offset that corrects it.

    The offset cancels the drift, so it is the negative of the measured drift.
    """
    return round(-drift_mm / MM_PER_INCH, 4)


def _render_calibration_tab(config: AppConfig) -> None:
    st.subheader("Calibration wizard")
    st.caption(
        "Align printed content to your printer. Work through the steps; the last step "
        "computes offsets you can save to your config."
    )

    st.markdown("**Step 1 — Generate the calibration sheet**")
    output_path = st.text_input("Calibration PDF", value=str(config.output_dir / "calibration.pdf"))
    if st.button("Generate calibration"):
        try:
            generate_calibration_pdf(
                Path(output_path),
                config.layout,
                config.layout_templates_path,
                config.duplex_flip.value,
            )
            st.success(f"Wrote {output_path}")
            _show_download(Path(output_path))
        except Exception as exc:
            st.error(str(exc))

    st.markdown("**Step 2 — Print at 100% / Actual Size**")
    st.caption(
        "Disable Fit to Page / Scale to Fit. Print both pages duplex on plain paper. "
        f"Confirm each FRONT n aligns with BACK n for the **{config.duplex_flip.value}** flip; "
        "if not, change Duplex flip in the sidebar and regenerate."
    )

    st.markdown("**Step 3 — Measure drift**")
    st.caption(
        "Using the ruler on the printout, measure how far the grid drifted from the true "
        "ruler marks. Right and up are positive."
    )
    front_col1, front_col2 = st.columns(2)
    front_x_mm = front_col1.number_input("Front drift → right (mm)", value=0.0, step=0.5)
    front_y_mm = front_col2.number_input("Front drift → up (mm)", value=0.0, step=0.5)
    back_col1, back_col2 = st.columns(2)
    back_x_mm = back_col1.number_input("Back drift → right (mm)", value=0.0, step=0.5)
    back_y_mm = back_col2.number_input("Back drift → up (mm)", value=0.0, step=0.5)

    st.markdown("**Step 4 — Review & save offsets**")
    computed = Calibration(
        front_x_offset_in=_drift_mm_to_offset_in(front_x_mm),
        front_y_offset_in=_drift_mm_to_offset_in(front_y_mm),
        back_x_offset_in=_drift_mm_to_offset_in(back_x_mm),
        back_y_offset_in=_drift_mm_to_offset_in(back_y_mm),
    )
    st.write(
        {
            "front_x_offset_in": computed.front_x_offset_in,
            "front_y_offset_in": computed.front_y_offset_in,
            "back_x_offset_in": computed.back_x_offset_in,
            "back_y_offset_in": computed.back_y_offset_in,
        }
    )
    if st.button("Save offsets to config"):
        try:
            updated = config.model_copy(update={"calibration": computed})
            save_config(updated, Path(st.session_state.get("config_path", str(DEFAULT_CONFIG_PATH))))
            st.success("Saved calibration offsets. Regenerate the calibration sheet to verify.")
        except Exception as exc:
            st.error(str(exc))


def _render_register_tab(config: AppConfig) -> None:
    register = CheckRegister(config.database_path)
    entries = register.list_entries()
    if not entries:
        st.info("No checks recorded yet. Generate a check to populate the register.")
        return

    st.caption("Select a row to update its status or reprint it.")
    selection = st.dataframe(
        _entry_rows(entries),
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="register-table",
    )
    selected = _selected_entry(entries, selection)
    if selected is None:
        st.info("No row selected.")
        return

    st.markdown(f"**Selected:** {_entry_label(selected)}")
    _render_selected_entry_details(selected)
    _render_register_status_actions(config, register, selected)
    _render_register_reprint_actions(config, register, selected)


def _selected_entry(entries: list[RegisterEntry], selection: Any) -> RegisterEntry | None:
    if not selection:
        return None
    selection_data = _selection_value(selection, "selection", {})
    rows = _selection_value(selection_data, "rows", [])
    if not rows:
        return None
    index = int(rows[0])
    if 0 <= index < len(entries):
        return entries[index]
    return None


def _selection_value(value: Any, key: str, default: Any) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _render_selected_entry_details(entry: RegisterEntry) -> None:
    with st.expander("Selected check audit details", expanded=False):
        st.write(
            {
                "register_id": entry.id,
                "status": entry.status.value,
                "account_id": entry.account_id,
                "check_number": entry.check_number,
                "check_date": entry.check_date.isoformat(),
                "created_at": entry.created_at,
                "printed_at": entry.printed_at or "",
                "cleared_date": entry.cleared_date.isoformat() if entry.cleared_date else "",
                "pdf_path": entry.pdf_path or "",
                "pdf_hash": entry.pdf_hash or "",
                "notes": entry.notes,
            }
        )


def _render_register_status_actions(
    config: AppConfig, register: CheckRegister, entry: RegisterEntry
) -> None:
    notes = st.text_input("Status note", key=f"status-note-{entry.id}")
    cleared_date = cast(
        dt_date,
        st.date_input("Cleared date", value=entry.cleared_date or dt_date.today()),
    )
    confirm_void = st.checkbox(
        "Confirm void selected check",
        key=f"confirm-void-{entry.id}",
        disabled=entry.status == CheckStatus.VOIDED,
    )
    col_printed, col_cleared, col_void = st.columns(3)

    if col_printed.button("Mark Printed", disabled=entry.status == CheckStatus.VOIDED):
        _apply_status(
            register,
            lambda: register.mark_printed(config.account.account_id, entry.check_number, notes=notes),
        )
    if col_cleared.button("Mark Cleared", disabled=entry.status == CheckStatus.VOIDED):
        _apply_status(
            register,
            lambda: register.mark_cleared(
                config.account.account_id,
                entry.check_number,
                cleared_date=cleared_date,
                notes=notes,
            ),
        )
    if col_void.button("Void", disabled=entry.status == CheckStatus.VOIDED):
        if not confirm_void:
            st.error("Confirm the void action before updating the register.")
            return
        _apply_status(
            register,
            lambda: register.mark_status(
                config.account.account_id,
                entry.check_number,
                CheckStatus.VOIDED,
                notes=notes,
            ),
        )


def _apply_status(register: CheckRegister, action: Callable[[], None]) -> None:
    try:
        action()
        st.success("Updated register")
        st.rerun()
    except Exception as exc:
        st.error(str(exc))


def _render_register_reprint_actions(
    config: AppConfig, register: CheckRegister, selected: RegisterEntry
) -> None:
    st.subheader("Reprint or Edit")
    col_a, col_b = st.columns(2)
    output_path = col_a.text_input(
        "Reprint output PDF",
        value=str(config.output_dir / f"check-{selected.check_number}-reprint.pdf"),
    )
    reprint_note = col_b.text_input(
        "Reprint note",
        value=f"Reprint of register entry #{selected.id}",
    )
    confirm_reprint = st.checkbox(
        "Confirm audited reprint",
        key=f"confirm-reprint-{selected.id}",
    )

    action_a, action_b = st.columns(2)
    if action_a.button("Reprint Selected"):
        if not confirm_reprint:
            st.error("Confirm the audited reprint before generating a duplicate check number.")
            return
        if not reprint_note.strip():
            st.error("A reprint note is required.")
            return
        try:
            check = _check_from_entry(selected)
            _generate_and_record(
                [check],
                config,
                Path(output_path),
                register,
                allow_reprint=True,
                notes=reprint_note.strip(),
            )
            _show_download(Path(output_path))
        except Exception as exc:
            st.error(str(exc))

    if action_b.button("Use as Template"):
        _set_generate_defaults(selected, config)
        st.session_state["write-mode"] = "Single check"
        st.success("Loaded into Write Checks → Single check. Open that tab to print.")


def _generate_and_record(
    checks: list[Check],
    config: AppConfig,
    output_path: Path,
    register: CheckRegister,
    allow_reprint: bool,
    notes: str = "",
) -> None:
    micr_registration = prepare_checks_pdf(checks, config)
    _show_micr_warning(micr_registration)
    write_checks_pdf(checks, config, output_path, micr_registration)
    pdf_hash = sha256_file(output_path)
    for check in checks:
        register.add_check(
            config.account.account_id,
            check,
            status=CheckStatus.PRINTED,
            pdf_path=output_path,
            pdf_hash=pdf_hash,
            notes=notes,
            allow_reprint=allow_reprint,
        )
    st.success(f"Wrote {output_path}")


def _check_from_entry(entry: RegisterEntry) -> Check:
    return Check(
        check_number=entry.check_number,
        payee=entry.payee,
        amount=entry.amount,
        date=entry.check_date,
        memo=entry.memo,
    )


def _checks_from_manual_rows(rows: list[dict[str, object]]) -> list[Check]:
    checks: list[Check] = []
    for row in rows:
        if not bool(row.get("include")):
            continue
        checks.append(
            Check(
                check_number=int(str(row["check_number"])),
                payee=str(row["payee"]).strip(),
                amount=_parse_decimal(str(row["amount"])),
                date=dt_date.fromisoformat(str(row["date"])),
                memo=str(row.get("memo", "")).strip(),
            )
        )
    return checks


def _entry_label(entry: RegisterEntry) -> str:
    return (
        f"#{entry.id} | check {entry.check_number} | {entry.status.value} | "
        f"{entry.check_date.isoformat()} | {entry.payee} | ${entry.amount}"
    )


def _generate_defaults(config: AppConfig) -> dict[str, object]:
    return {
        "payee": st.session_state.get("generate_payee", ""),
        "amount": st.session_state.get("generate_amount", "0.00"),
        "check_number": st.session_state.get("generate_check_number", ""),
        "date": st.session_state.get("generate_date", dt_date.today()),
        "memo": st.session_state.get("generate_memo", ""),
        "output_path": st.session_state.get(
            "generate_output_path", str(config.output_dir / "single-check.pdf")
        ),
        "reprint": st.session_state.get("generate_reprint", False),
    }


def _set_generate_defaults(entry: RegisterEntry, config: AppConfig) -> None:
    st.session_state["generate_payee"] = entry.payee
    st.session_state["generate_amount"] = str(entry.amount)
    st.session_state["generate_check_number"] = str(entry.check_number)
    st.session_state["generate_date"] = entry.check_date
    st.session_state["generate_memo"] = entry.memo
    st.session_state["generate_output_path"] = str(
        config.output_dir / f"check-{entry.check_number}-edited.pdf"
    )
    st.session_state["generate_reprint"] = True


def _clear_generate_defaults() -> None:
    for key in (
        "generate_payee",
        "generate_amount",
        "generate_check_number",
        "generate_date",
        "generate_memo",
        "generate_output_path",
        "generate_reprint",
    ):
        st.session_state.pop(key, None)


def _show_download(path: Path) -> None:
    st.download_button(
        "Download PDF",
        data=path.read_bytes(),
        file_name=path.name,
        mime="application/pdf",
    )
    _show_preview(path)


def _show_preview(path: Path) -> None:
    """Render the generated PDF inline so the exact print output is reviewable."""
    if not path.exists():
        return
    if not preview_available():
        st.info(PREVIEW_UNAVAILABLE_MESSAGE)
        return
    try:
        pages = render_pdf_to_pngs(path)
    except Exception as exc:  # rendering failure should not break generation
        st.warning(f"Could not render preview: {exc}")
        return

    with st.expander("Preview generated PDF", expanded=True):
        labels = _page_labels(len(pages))
        for label, image in zip(labels, pages, strict=True):
            st.caption(label)
            st.image(image, use_column_width=True)


def _page_labels(page_count: int) -> list[str]:
    """Label duplex pages as alternating Front/Back sheets."""
    labels: list[str] = []
    for index in range(page_count):
        sheet = index // 2 + 1
        side = "Front" if index % 2 == 0 else "Back"
        labels.append(f"Sheet {sheet} — {side}")
    return labels


def _entry_rows(entries: list[RegisterEntry]) -> list[dict[str, Any]]:
    return [
        {
            "id": entry.id,
            "check_number": entry.check_number,
            "date": entry.check_date.isoformat(),
            "status": entry.status.value,
            "amount": str(entry.amount),
            "payee": entry.payee,
            "memo": entry.memo,
            "printed_at": entry.printed_at or "",
            "notes": entry.notes,
            "pdf_path": entry.pdf_path or "",
            "pdf_hash": entry.pdf_hash or "",
            "cleared_date": entry.cleared_date.isoformat() if entry.cleared_date else "",
        }
        for entry in entries
    ]


def _layout_names(layout_templates_path: Path | None) -> list[str]:
    try:
        return sorted(load_layouts(layout_templates_path))
    except Exception as exc:
        st.sidebar.error(str(exc))
        return sorted(load_layouts())


def _show_micr_warning(registration: MicrFontRegistration) -> None:
    if registration.warning:
        st.warning(registration.warning)


def _parse_decimal(value: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("Amount must be a decimal value such as 123.45") from exc


def _path_or_none(value: str) -> Path | None:
    stripped = value.strip()
    return Path(stripped) if stripped else None


def _lines(value: str) -> list[str]:
    return [line.strip() for line in value.splitlines() if line.strip()]


if __name__ == "__main__":
    main()
