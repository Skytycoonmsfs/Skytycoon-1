# -*- coding: utf-8 -*-
"""SkyTycoon Pro — Einstellungen (DE/EN), erweitert ohne main.py-Layout."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class SkyTycoonSettingsDialog(QDialog):
    def __init__(self, main_window: Any, db_path: Path) -> None:
        super().__init__(main_window)
        self._mw = main_window
        self._path = db_path
        import main as m

        self._m = m
        self._tr = getattr(main_window, "_tr", m.i18n_db)
        self.setWindowTitle(self._tr("settings.title", "Einstellungen / Settings"))
        self.setMinimumSize(520, 560)
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget()
        root = QVBoxLayout(body)
        intro = QLabel(
            self._tr(
                "settings.intro",
                "Sprache, Cloud, IONOS und optionale Realismus-Module. "
                "Änderungen werden lokal gespeichert.",
            )
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        form = QFormLayout()
        self.combo_lang = QComboBox()
        self.combo_lang.addItem(self._tr("settings.lang_de", "Deutsch"), "de")
        self.combo_lang.addItem(self._tr("settings.lang_en", "English"), "en")
        cur = (m.app_meta_get(db_path, "ui_lang", "de") or "de")[:2].lower()
        self.combo_lang.setCurrentIndex(0 if cur != "en" else 1)
        form.addRow(self._tr("settings.lang", "Sprache / Language"), self.combo_lang)
        self.edit_cloud_pw = QLineEdit()
        self.edit_cloud_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit_cloud_pw.setPlaceholderText(
            self._tr("settings.cloud_pw_ph", "Cloud-Passwort (IONOS)")
        )
        existing = m.cloud_password_get(db_path)
        if existing:
            self.edit_cloud_pw.setText(existing)
        form.addRow(self._tr("settings.cloud_pw", "Cloud-Passwort"), self.edit_cloud_pw)
        self.edit_ionos = QLineEdit()
        self.edit_ionos.setPlaceholderText("https://skytycoon.info")
        self.edit_ionos.setText(
            (m.ionos_server_url() or m.ionos_api_base_url() or "").strip()
        )
        form.addRow(self._tr("settings.ionos_url", "IONOS-URL"), self.edit_ionos)
        root.addLayout(form)

        grp_ionos = QGroupBox(
            self._tr("settings.ionos_group", "IONOS-Server & Online-Netzwerk")
        )
        gl = QVBoxLayout(grp_ionos)
        hint = self._tr(
            "settings.ionos_url_hint",
            "Basis-URL (ENV): SKYTYCOON_IONOS_SERVER_URL oder SKYTYCOON_IONOS_API_BASE. "
            "Beispiel: {ex}",
        ).format(ex=m.ionos_api_base_url() or "https://skytycoon.info")
        lbl_hint = QLabel(hint)
        lbl_hint.setWordWrap(True)
        lbl_hint.setStyleSheet("color:#90caf9;font-size:12px;")
        gl.addWidget(lbl_hint)
        self.cb_online = QCheckBox(
            self._tr(
                "settings.cb_online_features",
                "SkyTycoon Online-Netzwerk aktivieren (Live-Radar, Markt, Support, Lizenz).",
            )
        )
        self.cb_online.setChecked(m.app_meta_get(db_path, "online_network_enabled", "0") == "1")
        gl.addWidget(self.cb_online)
        root.addWidget(grp_ionos)

        grp_realism = QGroupBox(
            self._tr(
                "settings.realism_group",
                "Erweiterte Realismus-Module (Optional)",
            )
        )
        rgl = QVBoxLayout(grp_realism)
        self._realism_boxes: list[tuple[str, QCheckBox]] = []
        for key, i18n_key, default in (
            ("realism_passenger_rage", "settings.cb_passenger_rage", "Kabinen-Eskalations-System"),
            ("realism_flex_toga", "settings.cb_flex_temp", "Triebwerks-Verschleiß (TOGA vs. FLEX)"),
            ("realism_airport_slots", "settings.cb_airport_slots", "Flughafen-Slot-Management"),
            ("realism_customs_smuggling", "settings.cb_customs_smuggling", "Zoll & Schmuggel (Cargo)"),
            ("realism_vip_catering", "settings.cb_vip_catering", "VIP & First-Class-Catering"),
            ("realism_engine_failures", "settings.cb_engine_failures", "Triebwerksschäden (Vogelschlag)"),
        ):
            cb = QCheckBox(self._tr(i18n_key, default))
            cb.setChecked(m.app_meta_get(db_path, key, "0") == "1")
            rgl.addWidget(cb)
            self._realism_boxes.append((key, cb))
        root.addWidget(grp_realism)

        grp_sound = QGroupBox(self._tr("settings.sound_group", "Audio & Copilot"))
        sgl = QFormLayout(grp_sound)
        self.spin_v1 = QSpinBox()
        self.spin_v1.setRange(55, 200)
        self.spin_v1.setValue(int(m.app_meta_get(db_path, "copilot_v1_kts", "125") or "125"))
        self.spin_vr = QSpinBox()
        self.spin_vr.setRange(60, 210)
        self.spin_vr.setValue(int(m.app_meta_get(db_path, "copilot_vr_kts", "135") or "135"))
        sgl.addRow(self._tr("sound.v1vr", "V1 / VR (kt)"), self.spin_v1)
        sgl.addRow(self._tr("sound.vr_label", "VR"), self.spin_vr)
        self.cb_auto_announce = QCheckBox(
            self._tr("settings.cb_auto_announce", "Automatische Kabinen-Durchsagen")
        )
        self.cb_auto_announce.setChecked(
            m.app_meta_get(db_path, "auto_announcements", "1") == "1"
        )
        sgl.addRow("", self.cb_auto_announce)
        root.addWidget(grp_sound)

        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        row = QHBoxLayout()
        btn_pull = QPushButton(
            self._tr("settings.btn_cloud_pull", "☁ Niederlassungen von IONOS laden")
        )
        btn_pull.clicked.connect(self._pull_branches_now)
        btn_ok = QPushButton(self._tr("settings.save", "Speichern"))
        btn_cancel = QPushButton(self._tr("settings.cancel", "Abbrechen"))
        btn_ok.clicked.connect(self._save)
        btn_cancel.clicked.connect(self.reject)
        row.addWidget(btn_pull)
        row.addStretch()
        row.addWidget(btn_ok)
        row.addWidget(btn_cancel)
        outer.addLayout(row)

    def _pull_branches_now(self) -> None:
        ok, msg = self._m.career_cloud_pull_branches_to_local(self._path)
        if ok:
            QMessageBox.information(
                self,
                self._tr("settings.title", "Einstellungen"),
                self._tr(
                    "settings.branches_pulled",
                    "Cloud-Pull: {n} Niederlassungen übernommen.",
                ).format(n=msg),
            )
            if hasattr(self._mw, "_refresh_realty_broker_table_rows"):
                self._mw._refresh_realty_broker_table_rows()
        else:
            err = (msg or "").strip()
            if err == "no_cloud":
                txt = self._tr(
                    "broker.cloud_disabled",
                    "Cloud-Abgleich: keine Basis-URL oder kein Cloud-Passwort.",
                )
            else:
                txt = self._tr(
                    "settings.branches_pull_fail",
                    "Cloud-Pull fehlgeschlagen: {e}",
                ).format(e=err)
            QMessageBox.warning(self, self._tr("settings.title", "Einstellungen"), txt)

    def _save(self) -> None:
        lang = str(self.combo_lang.currentData() or "de")
        pw = (self.edit_cloud_pw.text() or "").strip()
        url = (self.edit_ionos.text() or "").strip().rstrip("/")
        try:
            self._m.app_meta_set(self._path, "ui_lang", lang)
            self._m.app_meta_set(self._path, "app_language", lang)
            if pw:
                self._m.cloud_password_set(self._path, pw)
            if url:
                self._m.app_meta_set(self._path, "ionos_server_url", url[:500])
                self._m.app_meta_set(self._path, "ionos_api_base", url[:500])
            self._m.app_meta_set(
                self._path,
                "online_network_enabled",
                "1" if self.cb_online.isChecked() else "0",
            )
            for meta_key, cb in self._realism_boxes:
                self._m.app_meta_set(self._path, meta_key, "1" if cb.isChecked() else "0")
            self._m.app_meta_set(
                self._path, "copilot_v1_kts", str(int(self.spin_v1.value()))
            )
            self._m.app_meta_set(
                self._path, "copilot_vr_kts", str(int(self.spin_vr.value()))
            )
            self._m.app_meta_set(
                self._path,
                "auto_announcements",
                "1" if self.cb_auto_announce.isChecked() else "0",
            )
        except OSError as exc:
            QMessageBox.warning(
                self,
                self._tr("settings.title", "Einstellungen"),
                str(exc),
            )
            return
        if hasattr(self._mw, "_on_online_network_toggled"):
            try:
                self._mw._on_online_network_toggled(self.cb_online.isChecked())
            except Exception:
                pass
        if hasattr(self._mw, "_apply_language"):
            try:
                self._mw._apply_language(lang)
            except Exception:
                pass
        if hasattr(self._mw, "force_brute_ui_refresh"):
            self._mw.force_brute_ui_refresh()
        self.accept()
