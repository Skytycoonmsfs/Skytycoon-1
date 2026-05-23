# -*- coding: utf-8 -*-
"""Karriere-Status: Original-Layout (Bild 2) — ohne klobige Profil-Kasten."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QScrollArea, QVBoxLayout, QWidget


def _patch_cloud_dashboard_refresh_ceo(main_mod: Any) -> None:
    win_cls = getattr(main_mod, "MainWindow", None)
    if win_cls is None or getattr(win_cls, "_platin_ceo_cloud_patch", False):
        return
    if not hasattr(win_cls, "_force_thread_safe_dashboard_refresh"):
        return
    orig = win_cls._force_thread_safe_dashboard_refresh

    def _force_thread_safe_dashboard_refresh_platin(self: Any, data: dict) -> None:
        orig(self, data)
        try:
            self._refresh_ceo_report_panel()
        except Exception:
            pass

    win_cls._force_thread_safe_dashboard_refresh = (
        _force_thread_safe_dashboard_refresh_platin
    )
    win_cls._platin_ceo_cloud_patch = True


def patch_career_original_layout(main_mod: Any) -> None:
    win_cls = getattr(main_mod, "MainWindow", None)
    if win_cls is None or getattr(win_cls, "_platin_career_layout_patch", False):
        return

    def _refresh_ceo_report_panel_platin(self: Any) -> None:
        if not hasattr(self, "lbl_ceo_greeting"):
            return
        ceo = getattr(self, "frame_ceo_report", None)
        if ceo is not None:
            ceo.show()
            ceo.setMaximumHeight(16_777_215)
        db_path = main_mod.DB_PATH
        branch_rows = main_mod.fetch_airline_branches_realty_rows(db_path)
        n_br = len(branch_rows)
        self.lbl_ceo_infra_title.setText(
            self._tr("dash.infra", "Global infrastructure")
        )
        summary_html = self._tr(
            "dash.operate",
            'You currently operate <span style="color:#8ac7ff;font-weight:700">{n}</span> '
            "active branches worldwide.",
        ).format(n=n_br)
        self.lbl_ceo_infra_sum.setText(summary_html)
        tier_keys = {
            1: "morning.office_tier_1",
            2: "morning.office_tier_2",
            3: "morning.office_tier_3",
            4: "morning.office_tier_4",
            5: "morning.office_tier_5",
        }
        top4 = sorted(
            branch_rows,
            key=lambda r: (-int(r.get("level") or 1), -float(r.get("invested") or 0.0)),
        )[:4]
        lines: list[str] = []
        for r in top4:
            icao = str(r.get("icao") or "").strip().upper()[:4]
            lv = max(1, min(5, int(r.get("level") or 1)))
            tkey = tier_keys.get(lv, "morning.office_tier_1")
            tier = self._tr(tkey, "Level {lv}").format(lv=lv)
            ap_lab = (
                main_mod.airport_route_label(icao) if icao else "—"
            )
            lines.append(
                self._tr(
                    "morning.branch_line_fmt",
                    "  · {ap} — {tier}",
                ).format(ap=ap_lab, tier=tier)
            )
        empty_txt = self._tr("morning.branch_list_empty", "—")
        self.lbl_ceo_infra_list.setText("\n".join(lines) if lines else empty_txt)
        pilot = (
            main_mod.app_meta_get(db_path, "pilot_display_name", "").strip()
            or main_mod.app_meta_get(db_path, "pilot_name", "").strip()
            or "Pilot"
        )
        airline = (
            main_mod.app_meta_get(db_path, "selected_airline_name", "").strip()
            or main_mod.app_meta_get(db_path, "selected_airline_icao", "").strip()
            or "Airline"
        )
        ui = (
            main_mod.app_meta_get(db_path, "ui_lang", "de") or "de"
        ).strip().lower()
        if ui.startswith("en"):
            greet = f"Good morning, Cpt. {pilot}. Status report for {airline}:"
        else:
            greet = self._tr(
                "morning.greeting",
                "Guten Morgen, Cpt. {pilot}. Status-Bericht für {airline}:",
            ).format(pilot=pilot, airline=airline)
        self.lbl_ceo_greeting.setText(greet)
        models = main_mod.list_owned_models(db_path)
        fly_n = 0
        crit_n = 0
        for model in models:
            info = main_mod.get_aircraft_parts(db_path, model)
            parts = info.get("parts") or {}
            vals = [float(parts.get(c, 100.0)) for c in main_mod.PART_CODES]
            if all(v >= 80.0 for v in vals):
                fly_n += 1
            if any(v < 45.0 for v in vals):
                crit_n += 1
        credits_val = getattr(self, "_credits", None)
        if credits_val is None:
            credits_val = main_mod.load_credits(db_path)
        bal = main_mod.format_eur_de(float(credits_val or 0))
        loan_line = self._tr(
            "morning.finance_no_loan", "No active bank loan."
        )
        if main_mod.LoanManager.has_loan(db_path):
            daily = main_mod.LoanManager.current_daily_payment(db_path)
            loan_line = self._tr(
                "morning.finance_loan",
                "Loan payment due (approx. next 24 h): {amt}",
            ).format(amt=main_mod.format_eur_de(max(0.0, daily)))
        self.lbl_ceo_body.setText(
            self._tr("morning.body_fmt", "{fleet}\n\n{fin}").format(
                fleet=self._tr(
                    "morning.fleet_fmt",
                    "Fleet: {fly} airworthy · {crit} with critical hangar status.",
                ).format(fly=fly_n, crit=crit_n),
                fin=self._tr(
                    "dash.finance",
                    "Finance balance: {bal}. {loan}",
                ).format(bal=bal, loan=loan_line),
            )
        )

    def _refresh_career_profile_strip_platin(self: Any) -> None:
        strip = getattr(self, "frame_career_profile_strip", None)
        if strip is not None:
            strip.hide()
            strip.setMaximumHeight(0)
        if hasattr(self, "_refresh_career_hub_header"):
            self._refresh_career_hub_header()

    win_cls._refresh_ceo_report_panel = _refresh_ceo_report_panel_platin
    win_cls._refresh_career_profile_strip = _refresh_career_profile_strip_platin
    win_cls._platin_career_layout_patch = True
    _patch_cloud_dashboard_refresh_ceo(main_mod)


def _career_status_page(win: Any, injector: Any) -> QWidget | None:
    career_ix = getattr(win, "_hub_ix_career", None)
    inner = getattr(win, "_hub_tabwidgets", {}).get(career_ix)
    if inner is None:
        return None
    page = inner.widget(0)
    if page is None:
        return None
    unwrap = getattr(injector, "_hub_tab_unwrap", None)
    if callable(unwrap):
        return unwrap(page) or page
    sa = page.findChild(QScrollArea)
    if sa is not None and sa.widget() is not None:
        return sa.widget()
    return page


def restore_career_original_layout(win: Any, injector: Any) -> None:
    """Entfernt die 3 Kasten-Streifen; zeigt CEO-Status + Logo wie Bild 2."""
    print("[SkyTycoon] Karriere-Layout: Original-Status wird angewendet …", flush=True)

    strip = getattr(win, "frame_career_profile_strip", None)
    if strip is not None:
        parent = strip.parentWidget()
        if parent is not None:
            lay = parent.layout()
            if lay is not None:
                lay.removeWidget(strip)
        strip.hide()
        strip.setMaximumHeight(0)

    career_page = _career_status_page(win, injector)
    ceo = getattr(win, "frame_ceo_report", None)
    if career_page is not None and ceo is not None:
        lay = career_page.layout()
        if isinstance(lay, QVBoxLayout) and lay.indexOf(ceo) < 0:
            dash = getattr(win, "frame_career_dash", None)
            idx = lay.indexOf(dash) if dash is not None else 0
            lay.insertWidget(max(0, idx) + 1, ceo, 0)
        ceo.setStyleSheet(
            "#frame_ceo_report { background-color:#0b0f19; border:1px solid #2a3a52; "
            "border-radius:8px; padding:12px; }"
        )
        ceo.show()
        ceo.setMaximumHeight(16_777_215)

    dash = getattr(win, "frame_career_dash", None)
    if dash is not None:
        dash.hide()
        dash.setMaximumHeight(0)

    for attr, style in (
        ("lbl_ceo_greeting", "font-size:17px;font-weight:700;color:#8ac7ff;"),
        ("lbl_ceo_infra_title", "font-size:15px;font-weight:700;color:#8ac7ff;"),
        ("lbl_ceo_infra_sum", "font-size:14px;color:#b8d4f0;"),
        ("lbl_ceo_infra_list", "font-size:13px;color:#a8a8b0;"),
        ("lbl_ceo_body", "font-size:14px;color:#a8a8b0;line-height:1.45;"),
        ("label_career_status_title", "font-weight:700;font-size:15px;color:#8ac7ff;"),
        ("label_career_status_detail", "color:#a8a8b0;"),
    ):
        w = getattr(win, attr, None)
        if w is not None:
            w.setStyleSheet(style)

    logo = getattr(win, "label_airline_logo_dash", None)
    if logo is not None:
        logo.setMinimumSize(120, 120)
        logo.setMaximumSize(120, 120)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setStyleSheet(
            "QLabel { background-color:#0b0f19; border:1px solid #2a3a52; "
            "border-radius:8px; padding:6px; color:#8ac7ff; font-weight:700; "
            "font-size:28px; }"
        )

    news = getattr(win, "label_global_news_banner", None)
    if news is not None:
        news.setStyleSheet(
            "background-color:#1a1a1e;color:#e8e8ec;font-weight:700;font-size:13px;"
            "padding:10px 14px;border:1px solid #3a3a42;border-radius:6px;"
        )

    brand = getattr(win, "label_brand_pilot", None)
    if brand is not None:
        brand.hide()

    try:
        if hasattr(win, "force_absolute_logo_render"):
            win.force_absolute_logo_render()
    except Exception:
        pass

    try:
        win._refresh_ceo_report_panel()
    except Exception:
        pass
    try:
        win._refresh_career_status_dashboard()
    except Exception:
        pass

    win._platin_career_layout_restored = True
