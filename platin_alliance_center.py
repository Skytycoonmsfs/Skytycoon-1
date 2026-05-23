# -*- coding: utf-8 -*-
"""SkyTycoon Pro — 13-Säulen Allianz-Zentrale (Extensions-only, kein main.py-Layout-Umbau)."""

from __future__ import annotations

import json
import time
from typing import Any

import requests
from PySide6.QtCore import Qt, QRunnable, QThreadPool, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from skytycoon_theme import SKY_DARK_PANEL_STYLE, SKY_DARK_SCROLL_CSS

PLATIN_BLUE_SCROLL_CSS = SKY_DARK_SCROLL_CSS
PLATIN_BLUE_PANEL = SKY_DARK_PANEL_STYLE
ALLIANCE_HTTP_TIMEOUT_SEC = 14


class _FnRunnable(QRunnable):
    __slots__ = ("_fn",)

    def __init__(self, fn: Any) -> None:
        super().__init__()
        self._fn = fn

    def run(self) -> None:
        self._fn()


def platin_blue_scroll_wrap(content: QWidget) -> QWidget:
    shell = QWidget()
    shell.setStyleSheet(PLATIN_BLUE_PANEL)
    outer = QVBoxLayout(shell)
    outer.setContentsMargins(4, 4, 4, 4)
    outer.setSpacing(6)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setStyleSheet(PLATIN_BLUE_SCROLL_CSS)
    scroll.setSizePolicy(
        QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
    )
    content.setSizePolicy(
        QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
    )
    scroll.setWidget(content)
    outer.addWidget(scroll, 1)
    return shell


def _ensure_alliance_inner_tabs(main_window: Any) -> Any:
    """Legacy-Inner-Tabs müssen existieren (main._wrap_alliance_wallstreet_subtabs)."""
    if not getattr(main_window, "_alliance_wallstreet_wrapped", False):
        wrap = getattr(main_window, "_wrap_alliance_wallstreet_subtabs", None)
        if callable(wrap):
            try:
                wrap()
            except Exception as exc:
                print(f"[SkyTycoon] Allianz-Wrap: {exc!s}", flush=True)
    inner = getattr(main_window, "_alliance_inner_tabs", None)
    if inner is None:
        inner = getattr(main_window, "alliance_inner_tabs", None)
    return inner


def install_platin_alliance_13_center(main_window: Any, injector: Any) -> bool:
    center_prev = getattr(main_window, "_platin_alliance_13_center", None)
    if getattr(main_window, "_platin_alliance_13_installed", False):
        if center_prev is not None:
            try:
                if center_prev.parent() is not None:
                    return True
            except RuntimeError:
                pass
        main_window._platin_alliance_13_installed = False
    inner = _ensure_alliance_inner_tabs(main_window)
    if inner is None:
        print("[SkyTycoon] Allianz-13: kein alliance_inner_tabs.", flush=True)
        return False
    if isinstance(inner, PlatinAlliance13Center):
        return True
    parent = inner.parentWidget()
    layout = parent.layout() if parent is not None else None
    if layout is None:
        return False
    try:
        if inner.receivers(inner.currentChanged) > 0:
            inner.currentChanged.disconnect()
    except (RuntimeError, TypeError):
        pass
    idx = layout.indexOf(inner)
    stretch = layout.stretch(idx) if idx >= 0 else 1
    layout.removeWidget(inner)
    inner.hide()
    main_window._platin_alliance_inner_legacy = inner
    try:
        center = PlatinAlliance13Center(main_window, injector)
    except Exception as exc:
        print(f"[SkyTycoon] Allianz-13 Aufbau: {exc!s}", flush=True)
        layout.insertWidget(idx if idx >= 0 else 0, inner, stretch)
        inner.show()
        return False
    layout.insertWidget(idx if idx >= 0 else 0, center, stretch)
    main_window._platin_alliance_13_center = center
    main_window.alliance_inner_tabs = center.tabs
    main_window._platin_alliance_13_installed = True
    print("[SkyTycoon] Allianz 13-Säulen-Zentrale aktiv.", flush=True)
    QTimer.singleShot(400, center._safe_initial_refresh)
    return True


class PlatinAlliance13Center(QWidget):
    """13 funktionale Allianz-Säulen — Cloud-API + bestehende MainWindow-Widgets."""

    _async_done = Signal(object)

    def __init__(self, main_window: Any, injector: Any) -> None:
        super().__init__()
        self.mw = main_window
        self.inj = injector
        self._async_done.connect(self._on_async_done)
        self._async_callback: Any = None
        self._pillar_refresh_inflight = False
        self._pillar_refresh_pending: bool = False
        self._stolen_widgets: set[int] = set()
        self.setStyleSheet(PLATIN_BLUE_PANEL)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        self.tabs.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._tab_specs = self._pillar_specs()
        self._pages: dict[str, QWidget] = {}
        for key, _de, _en, builder in self._tab_specs:
            page = QWidget()
            page.setStyleSheet(PLATIN_BLUE_PANEL)
            bl = QVBoxLayout(page)
            bl.setContentsMargins(8, 8, 8, 8)
            bl.setSpacing(8)
            builder(bl)
            bl.addStretch()
            self._pages[key] = page
            title = self._t(_de, _en)
            self.tabs.addTab(platin_blue_scroll_wrap(page), title)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        lay.addWidget(self.tabs, 1)
        self._alliance_refresh_timer = QTimer(self)
        self._alliance_refresh_timer.setSingleShot(True)
        self._alliance_refresh_timer.setInterval(750)
        self._alliance_refresh_timer.timeout.connect(self._debounced_refresh_current)
        self._cached_state: dict[str, Any] = {}
        self._state_sig: str = ""
        self._poll = QTimer(self)
        self._poll.setInterval(20_000)
        self._poll.timeout.connect(self._poll_tick)
        self._poll.start()

    def _safe_initial_refresh(self) -> None:
        try:
            if self.parent() is not None:
                self.refresh_current_pillar(fetch_state=True)
        except Exception as exc:
            print(f"[SkyTycoon] Allianz-Refresh: {exc!s}", flush=True)

    def _safe_embed(self, lay: QVBoxLayout, widget: QWidget | None, *, stretch: int = 1) -> QWidget | None:
        """Widget einmalig einbetten — kein Doppel-Reparent (Qt-Absturz)."""
        if widget is None:
            return None
        stolen = getattr(self, "_stolen_widgets", None)
        if stolen is None:
            self._stolen_widgets = set()
            stolen = self._stolen_widgets
        wid = id(widget)
        try:
            if widget.parent() is lay:
                lay.addWidget(widget, stretch)
                return widget
            if wid in stolen:
                lay.addWidget(widget, stretch)
                return widget
            widget.setParent(None)
            stolen.add(wid)
            widget.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
            lay.addWidget(widget, stretch)
            return widget
        except RuntimeError:
            return None

    def _clear_table_cell_widgets(self, table: QTableWidget, col: int) -> None:
        try:
            for ri in range(table.rowCount()):
                table.removeCellWidget(ri, col)
        except RuntimeError:
            pass

    def _en(self) -> bool:
        fn = getattr(self.inj, "_ui_lang_en", None)
        return bool(fn()) if callable(fn) else False

    def _t(self, de: str, en: str) -> str:
        return en if self._en() else de

    def _tr(self, key: str, default: str) -> str:
        tr = getattr(self.mw, "_tr", None)
        if callable(tr):
            return tr(key, default)
        return default

    def _api(self) -> str:
        return (self.inj._api_base() or "").strip().rstrip("/")

    def _headers(self) -> dict[str, str]:
        return self.inj._headers()

    def _hid_body(self) -> dict[str, Any]:
        import skytycoon_extensions as ext

        return {
            "hardware_id": ext._normalize_client_hwid(
                self.inj.m, self.inj.db_path
            )
        }

    def _pool(self) -> QThreadPool:
        fn = getattr(self.inj, "_pool", None)
        if callable(fn):
            return fn()
        return QThreadPool.globalInstance()

    def _run_async(self, work: Any, done: Any) -> None:
        """HTTP/JSON im Thread-Pool — UI-Thread bleibt frei."""
        self._async_callback = done

        def _job() -> None:
            try:
                out = work()
            except Exception as exc:
                out = {"ok": False, "error": str(exc)[:120]}
            self._async_done.emit(out)

        self._pool().start(_FnRunnable(_job))

    def _on_async_done(self, payload: object) -> None:
        cb = self._async_callback
        self._async_callback = None
        if callable(cb):
            cb(payload)

    def _post_blocking(self, path: str, extra: dict | None = None) -> dict:
        base = self._api()
        if not base:
            return {"ok": False, "error": "offline"}
        body = dict(self._hid_body())
        if extra:
            body.update(extra)
        try:
            r = requests.post(
                f"{base}{path}",
                json=body,
                headers=self._headers(),
                timeout=ALLIANCE_HTTP_TIMEOUT_SEC,
            )
            return r.json() if r.content else {"ok": False}
        except (requests.RequestException, json.JSONDecodeError, ValueError) as exc:
            return {"ok": False, "error": str(exc)[:120]}

    def _get_blocking(self, path: str, params: dict | None = None) -> dict:
        base = self._api()
        if not base:
            return {"ok": False, "error": "offline"}
        try:
            r = requests.get(
                f"{base}{path}",
                params=params or {},
                headers=self._headers(),
                timeout=ALLIANCE_HTTP_TIMEOUT_SEC,
            )
            return r.json() if r.content else {"ok": False}
        except (requests.RequestException, json.JSONDecodeError, ValueError) as exc:
            return {"ok": False, "error": str(exc)[:120]}

    def _post(self, path: str, extra: dict | None = None) -> dict:
        """Nur für kurze synchrone Pfade — Tab-Refresh nutzt _run_async."""
        return self._post_blocking(path, extra)

    def _get(self, path: str, params: dict | None = None) -> dict:
        return self._get_blocking(path, params)

    def _pillar_specs(self) -> list[tuple[str, str, str, Any]]:
        return [
            ("bourse", "📊 Allianz-Börse", "📊 Alliance Exchange", self._build_bourse),
            ("stock", "📈 Aktienmarkt", "📈 Stock Market", self._build_stock),
            ("auction", "🔨 Allianz-Auktionen", "🔨 Alliance Auctions", self._build_auction),
            ("hq", "🏢 Allianz-HQ", "🏢 Alliance HQ", self._build_hq),
            ("fuel", "⛽ Kerosin-Großlager", "⛽ Alliance Fuel Depot", self._build_fuel),
            ("jobs", "📋 Auftrags-Börse", "📋 Contract Board", self._build_jobs),
            ("members", "👑 Mitglieder", "👑 Members", self._build_members),
            ("ticker", "💬 Live-Ticker", "💬 Live Ticker", self._build_ticker),
            ("leader", "🏆 Leaderboard", "🏆 Leaderboard", self._build_leaderboard),
            ("midnight", "⏰ Mitternacht", "⏰ Midnight UTC", self._build_midnight),
            ("routes", "🏢 Routen-Pacht", "🏢 Route Leases", self._build_routes),
            ("insurance", "🛡️ Kasko", "🛡️ Hull Insurance", self._build_insurance),
            ("shipyard", "🛠️ Großwerft", "🛠️ Alliance Shipyard", self._build_shipyard),
        ]

    def _lbl(self, lay: QVBoxLayout, text: str, *, hdr: bool = False) -> QLabel:
        w = QLabel(text)
        w.setWordWrap(True)
        if hdr:
            w.setStyleSheet("color:#00a2ff;font-weight:700;font-size:14px;")
        lay.addWidget(w)
        return w

    def _build_bourse(self, lay: QVBoxLayout) -> None:
        self._lbl(
            lay,
            self._tr(
                "alliance13.bourse.hdr",
                "Ein-/Auszahlungen & Meilen-Dividenden (PostgreSQL-Pool)",
            ),
            hdr=True,
        )
        self.lbl_pool = self._lbl(lay, "—")
        row = QHBoxLayout()
        self.spin_donate = QDoubleSpinBox()
        self.spin_donate.setRange(100, 50_000_000)
        self.spin_donate.setSuffix(" Cr.")
        self.spin_donate.setValue(5000)
        self.btn_donate = QPushButton(
            self._tr("alliance13.bourse.deposit", "💰 In Allianz-Kasse einzahlen")
        )
        self.btn_donate.clicked.connect(self._on_donate)
        self.btn_dividend = QPushButton(
            self._tr("alliance13.bourse.dividend", "📊 Meilen-Dividende verteilen")
        )
        self.btn_dividend.clicked.connect(self._on_dividend)
        row.addWidget(self.spin_donate)
        row.addWidget(self.btn_donate)
        row.addWidget(self.btn_dividend)
        lay.addLayout(row)
        if hasattr(self.mw, "btn_alliance_donate"):
            self.mw.btn_alliance_donate.hide()

    def _build_stock(self, lay: QVBoxLayout) -> None:
        self._lbl(
            lay,
            self._tr(
                "alliance13.stock.formula",
                "Firmenwert = Credits + Flotten-Marktwert · Live-Kurs",
            ),
            hdr=True,
        )
        self.table_stock = QTableWidget(0, 6)
        self.table_stock.setHorizontalHeaderLabels(
            [
                self._tr("alliance13.col.name", "Allianz"),
                self._tr("alliance13.col.price", "Kurs"),
                self._tr("alliance13.col.value", "Firmenwert"),
                self._tr("alliance13.col.owned", "Anteile"),
                self._tr("alliance13.col.side", "Aktion"),
                "",
            ]
        )
        self.table_stock.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table_stock.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        lay.addWidget(self.table_stock, 1)
        if hasattr(self.mw, "table_pc_wallstreet"):
            self.mw.table_pc_wallstreet.hide()

    def _build_auction(self, lay: QVBoxLayout) -> None:
        self._lbl(
            lay,
            self._tr(
                "alliance13.auction.hint",
                "Geschlossener Broker · atomarer Row-Lock gegen Duplikat-Cheats",
            ),
            hdr=True,
        )
        self.table_auction = QTableWidget(0, 6)
        self.table_auction.setHorizontalHeaderLabels(
            [
                "ID",
                self._tr("alliance13.col.item", "Objekt"),
                self._tr("alliance13.col.bid", "Gebot"),
                self._tr("alliance13.col.ends", "Ende UTC"),
                self._tr("alliance13.col.bid_btn", "Bieten"),
                self._tr("alliance13.col.status", "Status"),
            ]
        )
        self.table_auction.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        lay.addWidget(self.table_auction, 1)
        br = QHBoxLayout()
        self.spin_bid = QDoubleSpinBox()
        self.spin_bid.setRange(100, 99_000_000)
        self.btn_bid = QPushButton(self._tr("alliance13.auction.bid", "🔨 Gebot abgeben"))
        self.btn_bid.clicked.connect(self._on_auction_bid)
        self.btn_refresh_auction = QPushButton(self._tr("common.refresh", "🔄 Aktualisieren"))
        self.btn_refresh_auction.clicked.connect(self._refresh_auctions)
        br.addWidget(self.spin_bid)
        br.addWidget(self.btn_bid)
        br.addWidget(self.btn_refresh_auction)
        lay.addLayout(br)

    def _build_hq(self, lay: QVBoxLayout) -> None:
        self._lbl(
            lay,
            self._tr(
                "alliance13.hq.hint",
                "Tech-Baum: Kerosin -5 %, Cargo +10 % — wirkt auf Server-Berechnungen",
            ),
            hdr=True,
        )
        dash = getattr(self.mw, "advanced_alliance_dashboard", None)
        if dash is not None and dash.parent() is not lay:
            btn = QPushButton(
                self._tr(
                    "alliance13.hq.open_mega",
                    "🏛️ Allianz-Zentrale (Hubs & MMO) öffnen",
                )
            )
            btn.clicked.connect(self._open_mega_dashboard)
            lay.addWidget(btn)
            sub = getattr(dash, "sub_tabs", None)
            if sub is not None:
                try:
                    sub.setSizePolicy(
                        QSizePolicy.Policy.Expanding,
                        QSizePolicy.Policy.Expanding,
                    )
                except RuntimeError:
                    pass
        else:
            self._lbl(lay, self._tr("alliance13.hq.missing", "HQ-Widget lädt …"))

    def _open_mega_dashboard(self) -> None:
        go = getattr(self.mw, "_alliance_go_mega_sub", None)
        if callable(go):
            try:
                go(0)
            except Exception:
                pass
        req = getattr(self.mw, "_request_alliance_mega_state", None)
        if callable(req):
            try:
                req()
            except Exception:
                pass

    def _build_fuel(self, lay: QVBoxLayout) -> None:
        self._lbl(
            lay,
            self._tr(
                "alliance13.fuel.hint",
                "Großlager · Preise gekoppelt an Web-Krisenradar",
            ),
            hdr=True,
        )
        self.lbl_fuel = self._lbl(lay, "—")
        row = QHBoxLayout()
        self.spin_fuel_liters = QSpinBox()
        self.spin_fuel_liters.setRange(1000, 5_000_000)
        self.spin_fuel_liters.setSuffix(" L")
        self.spin_fuel_liters.setValue(50_000)
        self.btn_fuel_buy = QPushButton(
            self._tr("alliance13.fuel.buy", "⛽ Treibstoff bevorraten")
        )
        self.btn_fuel_buy.clicked.connect(self._on_fuel_buy)
        row.addWidget(self.spin_fuel_liters)
        row.addWidget(self.btn_fuel_buy)
        lay.addLayout(row)

    def _build_jobs(self, lay: QVBoxLayout) -> None:
        self._lbl(
            lay,
            self._tr(
                "alliance13.jobs.hint",
                "Großauftrag in Teil-Frachtbriefe · Credit-Split bei Landung",
            ),
            hdr=True,
        )
        self.table_jobs = QTableWidget(0, 5)
        self.table_jobs.setHorizontalHeaderLabels(
            [
                self._tr("alliance13.col.route", "Route"),
                self._tr("alliance13.col.share", "Anteil %"),
                self._tr("alliance13.col.pilot", "Pilot"),
                self._tr("alliance13.col.status", "Status"),
                self._tr("alliance13.col.cr", "Credits"),
            ]
        )
        self.table_jobs.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        lay.addWidget(self.table_jobs, 1)
        br = QHBoxLayout()
        self.edit_job_route = QLineEdit()
        self.edit_job_route.setPlaceholderText("EDDF-EGLL")
        self.spin_job_parts = QSpinBox()
        self.spin_job_parts.setRange(2, 12)
        self.spin_job_parts.setValue(3)
        self.btn_job_split = QPushButton(
            self._tr("alliance13.jobs.split", "📋 Auftrag splitten")
        )
        self.btn_job_split.clicked.connect(self._on_job_split)
        br.addWidget(self.edit_job_route)
        br.addWidget(self.spin_job_parts)
        br.addWidget(self.btn_job_split)
        lay.addLayout(br)

    def _build_members(self, lay: QVBoxLayout) -> None:
        self._lbl(
            lay,
            self._tr(
                "alliance13.members.hint",
                "Rechtsklick-Beförderung · Co-Owner · Schatzmeister · Sperren",
            ),
            hdr=True,
        )
        tbl = getattr(self.mw, "table_alliance_members", None)
        if tbl is not None:
            try:
                tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                tbl.customContextMenuRequested.connect(self._on_members_context)
            except RuntimeError:
                pass
            embedded = self._safe_embed(lay, tbl)
            self.table_members = embedded if embedded is not None else tbl
        else:
            self.table_members = QTableWidget(0, 4)
            lay.addWidget(self.table_members, 1)
        br = QHBoxLayout()
        self.combo_member_role = QComboBox()
        for role, de, en in (
            ("co_leader", "Co-Owner", "Co-Owner"),
            ("treasurer", "Schatzmeister", "Treasurer"),
            ("captain", "Kapitän", "Captain"),
            ("member", "Mitglied", "Member"),
            ("banned", "Gesperrt", "Banned"),
        ):
            self.combo_member_role.addItem(self._t(de, en), role)
        self.btn_promote = QPushButton(
            self._tr("alliance13.members.promote", "👑 Rolle setzen")
        )
        self.btn_promote.clicked.connect(self._on_member_promote)
        br.addWidget(self.combo_member_role)
        br.addWidget(self.btn_promote)
        lay.addLayout(br)

    def _build_ticker(self, lay: QVBoxLayout) -> None:
        self.ticker_log = QTextEdit()
        self.ticker_log.setReadOnly(True)
        self.ticker_log.setMinimumHeight(220)
        lay.addWidget(self.ticker_log, 1)

    def _build_leaderboard(self, lay: QVBoxLayout) -> None:
        self.table_leader = QTableWidget(0, 5)
        self.table_leader.setHorizontalHeaderLabels(
            [
                "#",
                self._tr("alliance13.col.name", "Allianz"),
                self._tr("alliance13.col.wealth", "Vermögen"),
                self._tr("alliance13.col.xp", "XP"),
                self._tr("alliance13.col.members", "Mitglieder"),
            ]
        )
        self.table_leader.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        lay.addWidget(self.table_leader, 1)

    def _build_midnight(self, lay: QVBoxLayout) -> None:
        self.lbl_midnight = self._lbl(
            lay,
            self._tr("alliance13.midnight.wait", "Countdown zum 00:00 UTC Reset …"),
            hdr=True,
        )
        self._lbl(
            lay,
            self._tr(
                "alliance13.midnight.detail",
                "Kurz-/Langstrecken-Flugbörse & Krisenradar werden automatisch zurückgesetzt.",
            ),
        )

    def _build_routes(self, lay: QVBoxLayout) -> None:
        self._lbl(
            lay,
            self._tr(
                "alliance13.routes.hint",
                "Streckenrechte · Pacht-Gutschrift bei Fremdflügen",
            ),
            hdr=True,
        )
        tbl = getattr(self.mw, "table_alliance_leases", None)
        if tbl is not None:
            embedded = self._safe_embed(lay, tbl)
            self.table_routes = embedded if embedded is not None else tbl
        else:
            self.table_routes = QTableWidget(0, 4)
            lay.addWidget(self.table_routes, 1)
        br = QHBoxLayout()
        self.edit_lease_route = QLineEdit()
        self.edit_lease_route.setPlaceholderText("EDDF-KJFK")
        self.spin_lease_fee = QDoubleSpinBox()
        self.spin_lease_fee.setRange(0, 500_000)
        self.spin_lease_fee.setSuffix(" Cr./Flug")
        self.btn_lease = QPushButton(
            self._tr("alliance13.routes.lease", "🏢 Route pachten")
        )
        self.btn_lease.clicked.connect(self._on_route_lease)
        br.addWidget(self.edit_lease_route)
        br.addWidget(self.spin_lease_fee)
        br.addWidget(self.btn_lease)
        lay.addLayout(br)

    def _build_insurance(self, lay: QVBoxLayout) -> None:
        self._lbl(
            lay,
            self._tr(
                "alliance13.insurance.hint",
                "Versicherungspool · Auto-Regulierung bei Unwetter-Crashs",
            ),
            hdr=True,
        )
        self.btn_insurance_sync = QPushButton(
            self._tr("alliance13.insurance.sync", "🛡️ Pool synchronisieren")
        )
        self.btn_insurance_sync.clicked.connect(self._on_insurance_sync)
        lay.addWidget(self.btn_insurance_sync)

    def _build_shipyard(self, lay: QVBoxLayout) -> None:
        self._lbl(
            lay,
            self._tr(
                "alliance13.shipyard.hint",
                "Shared-Ersatzteile · SELECT FOR UPDATE",
            ),
            hdr=True,
        )
        self.table_shipyard = QTableWidget(0, 5)
        self.table_shipyard.setHorizontalHeaderLabels(
            [
                self._tr("alliance13.col.part", "Teil"),
                self._tr("alliance13.col.qty", "Menge"),
                self._tr("alliance13.col.cond", "Zustand"),
                self._tr("alliance13.col.holder", "Inhaber"),
                self._tr("alliance13.col.action", "Aktion"),
            ]
        )
        self.table_shipyard.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        lay.addWidget(self.table_shipyard, 1)
        br = QHBoxLayout()
        self.edit_part_type = QLineEdit()
        self.edit_part_type.setPlaceholderText("ENGINE_CFM")
        self.spin_part_qty = QSpinBox()
        self.spin_part_qty.setRange(1, 99)
        self.btn_part_deposit = QPushButton(
            self._tr("alliance13.shipyard.deposit", "📥 Teil einlagern")
        )
        self.btn_part_deposit.clicked.connect(self._on_shipyard_deposit)
        self.btn_part_take = QPushButton(
            self._tr("alliance13.shipyard.take", "📤 Teil entnehmen")
        )
        self.btn_part_take.clicked.connect(self._on_shipyard_take)
        br.addWidget(self.edit_part_type)
        br.addWidget(self.spin_part_qty)
        br.addWidget(self.btn_part_deposit)
        br.addWidget(self.btn_part_take)
        lay.addLayout(br)

    def _on_tab_changed(self, _ix: int) -> None:
        self._alliance_refresh_timer.start()

    def _debounced_refresh_current(self) -> None:
        if not self._alliance_hub_visible():
            return
        self.refresh_current_pillar(fetch_state=True)

    def _current_pillar_key(self) -> str:
        ix = self.tabs.currentIndex()
        if 0 <= ix < len(self._tab_specs):
            return str(self._tab_specs[ix][0])
        return ""

    def _alliance_hub_visible(self) -> bool:
        fn = getattr(self.mw, "_is_main_hub_active", None)
        if callable(fn):
            try:
                return bool(fn("_hub_ix_alliance"))
            except Exception:
                pass
        tw = getattr(self.mw, "tab_widget", None)
        if tw is None:
            return False
        ix = getattr(self.mw, "_hub_ix_alliance", -1)
        safe = getattr(self.mw, "_safe_tab_index", None)
        if callable(safe):
            try:
                ix = int(safe("_hub_ix_alliance"))
            except Exception:
                pass
        return 0 <= ix < tw.count() and tw.currentIndex() == ix

    def _poll_tick(self) -> None:
        if not self._alliance_hub_visible():
            return
        ix = self.tabs.currentIndex()
        key = self._tab_specs[ix][0] if 0 <= ix < len(self._tab_specs) else ""
        if key in ("ticker", "midnight", "stock", "auction", "leader"):
            self.refresh_current_pillar(fetch_state=False)

    def refresh_current_pillar(self, *, fetch_state: bool = True) -> None:
        """Nur sichtbare Säule — Netzwerk im Hintergrund."""
        try:
            if self.parent() is None:
                return
            if not self._alliance_hub_visible():
                return
            if self._pillar_refresh_inflight:
                self._pillar_refresh_pending = True
                return
            self._pillar_refresh_inflight = True
            key = self._current_pillar_key()
            if fetch_state and hasattr(self.mw, "_refresh_alliance_panel"):
                try:
                    self.mw._refresh_alliance_panel()
                except Exception:
                    pass

            def _work() -> dict:
                state = dict(self._cached_state)
                if fetch_state:
                    state = self._post_blocking("/api/v1/alliance/platin/state", {})
                net = self._load_pillar_network_blocking(key, state)
                return {"state": state, "key": key, "net": net}

            def _done(payload: object) -> None:
                self._pillar_refresh_inflight = False
                try:
                    if self.parent() is None:
                        return
                    if not isinstance(payload, dict):
                        if self._pillar_refresh_pending:
                            self._pillar_refresh_pending = False
                            self.refresh_current_pillar(fetch_state=True)
                        return
                    state = payload.get("state")
                    if isinstance(state, dict) and state.get("ok"):
                        try:
                            sig = json.dumps(
                                state, sort_keys=True, ensure_ascii=False
                            )[:4096]
                        except (TypeError, ValueError):
                            sig = str(state)[:4096]
                        if sig != self._state_sig:
                            self._state_sig = sig
                            self._apply_state(state)
                        self._cached_state = state
                    key = str(payload.get("key") or "")
                    net = payload.get("net")
                    if isinstance(net, dict):
                        self._apply_pillar_network(key, net)
                    self._refresh_pillar_local(key, self._cached_state)
                    if self._pillar_refresh_pending:
                        self._pillar_refresh_pending = False
                        self.refresh_current_pillar(fetch_state=True)
                except Exception as exc:
                    print(f"[SkyTycoon] Allianz-UI: {exc!s}", flush=True)

            self._run_async(_work, _done)
        except Exception as exc:
            self._pillar_refresh_inflight = False
            print(f"[SkyTycoon] Allianz-Refresh: {exc!s}", flush=True)

    def refresh_all(self) -> None:
        """Kompatibilität: entspricht refresh_current_pillar."""
        self.refresh_current_pillar(fetch_state=True)

    def _load_pillar_network_blocking(self, key: str, state: dict) -> dict:
        if key == "stock":
            hid_body = self._hid_body()
            un = str(
                self.inj.m.app_meta_get(self.inj.db_path, "pilot_display_name", "")
                or ""
            ).strip()
            return {
                "kind": "stock",
                "j": self._get_blocking(
                    "/api/v1/wallstreet/dashboard",
                    {"hardware_id": hid_body.get("hardware_id", ""), "username": un},
                ),
            }
        if key == "auction":
            return {
                "kind": "auction",
                "j": self._post_blocking("/api/v1/alliance/auction/list", {}),
            }
        if key == "leader":
            return {
                "kind": "leader",
                "j": self._get_blocking("/api/v1/alliance/leaderboard/global", {"limit": 50}),
            }
        if key == "ticker":
            return {"kind": "ticker", "j": self._get_blocking("/api/v1/web/ticker/live", {"limit": 40})}
        if key == "midnight":
            return {"kind": "midnight", "j": self._get_blocking("/api/v1/alliance/midnight/status", {})}
        return {"kind": key}

    def _apply_pillar_network(self, key: str, net: dict) -> None:
        kind = str(net.get("kind") or key)
        j = net.get("j")
        if kind == "stock" and isinstance(j, dict):
            self._apply_stock_json(j)
        elif kind == "auction" and isinstance(j, dict):
            self._apply_auctions_json(j)
        elif kind == "leader" and isinstance(j, dict):
            self._apply_leaderboard_json(j)
        elif kind == "ticker" and isinstance(j, dict):
            self._apply_ticker_json(j)
        elif kind == "midnight" and isinstance(j, dict):
            self._apply_midnight_json(j)

    def _refresh_pillar_local(self, key: str, data: dict) -> None:
        if key == "jobs":
            self._refresh_jobs(data)
        elif key == "shipyard":
            self._refresh_shipyard(data)
        elif key == "members" and hasattr(self.mw, "_refresh_alliance_members"):
            try:
                self.mw._refresh_alliance_members()
            except Exception:
                pass
        elif key == "hq" and hasattr(self.mw, "_refresh_alliance_panel"):
            try:
                self.mw._refresh_alliance_panel()
            except Exception:
                pass

    def _refresh_pillar(self, key: str) -> None:
        self.refresh_current_pillar(fetch_state=False)

    def _apply_state(self, data: dict) -> None:
        if not hasattr(self, "lbl_pool") or not hasattr(self, "lbl_fuel"):
            return
        pool = float(data.get("alliance_credits", 0) or 0)
        self.lbl_pool.setText(
            self._tr("alliance13.bourse.pool_fmt", "Kassenstand: {cr} Credits").format(
                cr=f"{pool:,.0f}".replace(",", ".")
            )
        )
        fuel = data.get("fuel_depot") or {}
        if isinstance(fuel, dict):
            liters = float(fuel.get("liters", 0) or 0)
            cap = float(fuel.get("cap_liters", 0) or 0)
            mult = float(fuel.get("crisis_multiplier", 1) or 1)
            self.lbl_fuel.setText(
                self._tr(
                    "alliance13.fuel.status_fmt",
                    "Lager: {lit:.0f} / {cap:.0f} L · Krisen-Faktor ×{mult:.2f}",
                ).format(lit=liters, cap=cap, mult=mult)
            )

    def _apply_stock_json(self, j: dict) -> None:
        stocks = list(j.get("stocks") or [])
        self._clear_table_cell_widgets(self.table_stock, 4)
        self.table_stock.setRowCount(len(stocks))
        for ri, st in enumerate(stocks):
            aid = str(st.get("alliance_id") or "")
            name = str(st.get("name") or aid)
            price = float(st.get("share_price", 0) or 0)
            val = float(st.get("total_profit", 0) or 0)
            owned = float(st.get("owned_shares", 0) or 0)
            self.table_stock.setItem(ri, 0, QTableWidgetItem(name))
            self.table_stock.setItem(ri, 1, QTableWidgetItem(f"{price:,.0f}"))
            self.table_stock.setItem(ri, 2, QTableWidgetItem(f"{val:,.0f}"))
            self.table_stock.setItem(ri, 3, QTableWidgetItem(f"{owned:.1f}"))
            buy = QPushButton("BUY")
            sell = QPushButton("SELL")
            buy.clicked.connect(
                lambda _c=False, a=aid: self._trade_stock(a, "buy")
            )
            sell.clicked.connect(
                lambda _c=False, a=aid: self._trade_stock(a, "sell")
            )
            box = QWidget()
            bl = QHBoxLayout(box)
            bl.setContentsMargins(2, 2, 2, 2)
            bl.addWidget(buy)
            bl.addWidget(sell)
            self.table_stock.setCellWidget(ri, 4, box)
        if hasattr(self.mw, "_refresh_pc_wallstreet_table"):
            try:
                self.mw._refresh_pc_wallstreet_table(j)
            except Exception:
                pass

    def _refresh_stock(self) -> None:
        self.refresh_current_pillar(fetch_state=False)

    def _trade_stock(self, alliance_id: str, side: str) -> None:
        body = {
            "alliance_id": alliance_id,
            "side": side,
            "shares": 1.0,
        }

        def _done(j: object) -> None:
            if isinstance(j, dict) and not j.get("ok"):
                QMessageBox.warning(
                    self.mw,
                    "Wallstreet",
                    str(j.get("error") or j.get("message") or "Trade failed"),
                )
            self.refresh_current_pillar(fetch_state=False)

        self._run_async(
            lambda: self._post_blocking("/api/v1/wallstreet/trade", body),
            _done,
        )

    def _apply_auctions_json(self, j: dict) -> None:
        rows = list(j.get("auctions") or [])
        self._clear_table_cell_widgets(self.table_auction, 4)
        self.table_auction.setRowCount(len(rows))
        for ri, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            aid = str(row.get("auction_id") or row.get("id") or "")
            self.table_auction.setItem(ri, 0, QTableWidgetItem(aid))
            self.table_auction.setItem(
                ri, 1, QTableWidgetItem(str(row.get("title") or row.get("item_type") or "—"))
            )
            self.table_auction.setItem(
                ri, 2, QTableWidgetItem(f"{float(row.get('current_bid', 0) or 0):,.0f}")
            )
            self.table_auction.setItem(
                ri, 3, QTableWidgetItem(str(row.get("ends_utc") or "—"))
            )
            btn = QPushButton("BID")
            btn.clicked.connect(
                lambda _c=False, a=aid: self._on_auction_bid_id(a)
            )
            self.table_auction.setCellWidget(ri, 4, btn)
            self.table_auction.setItem(
                ri, 5, QTableWidgetItem(str(row.get("status") or "open"))
            )

    def _on_auction_bid(self) -> None:
        row = self.table_auction.currentRow()
        if row < 0:
            return
        it = self.table_auction.item(row, 0)
        if it:
            self._on_auction_bid_id(it.text())

    def _refresh_auctions(self) -> None:
        self.refresh_current_pillar(fetch_state=False)

    def _on_auction_bid_id(self, auction_id: str) -> None:
        extra = {"auction_id": auction_id, "bid": float(self.spin_bid.value())}

        def _done(j: object) -> None:
            if isinstance(j, dict) and not j.get("ok"):
                QMessageBox.warning(
                    self.mw, "Auction", str(j.get("error") or "bid failed")
                )
            self.refresh_current_pillar(fetch_state=False)

        self._run_async(
            lambda: self._post_blocking("/api/v1/alliance/auction/bid", extra),
            _done,
        )

    def _apply_ticker_json(self, j: dict) -> None:
        lines = list(j.get("lines") or j.get("events") or [])
        if not lines and isinstance(j.get("ticker"), str):
            lines = [j["ticker"]]
        txt = "\n".join(str(x) for x in lines[-40:])
        self.ticker_log.setPlainText(txt or "—")

    def _refresh_ticker(self) -> None:
        self.refresh_current_pillar(fetch_state=False)

    def _apply_leaderboard_json(self, j: dict) -> None:
        rows = list(j.get("alliances") or [])
        self.table_leader.setRowCount(len(rows))
        for ri, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            self.table_leader.setItem(ri, 0, QTableWidgetItem(str(ri + 1)))
            self.table_leader.setItem(
                ri, 1, QTableWidgetItem(str(row.get("name") or "—"))
            )
            self.table_leader.setItem(
                ri, 2, QTableWidgetItem(f"{float(row.get('wealth', 0) or 0):,.0f}")
            )
            self.table_leader.setItem(
                ri, 3, QTableWidgetItem(f"{int(row.get('xp', 0) or 0):,}")
            )
            self.table_leader.setItem(
                ri, 4, QTableWidgetItem(str(int(row.get('members', 0) or 0)))
            )

    def _refresh_leaderboard(self) -> None:
        self.refresh_current_pillar(fetch_state=False)

    def _apply_midnight_json(self, j: dict) -> None:
        sec = int(j.get("seconds_to_midnight_utc", 0) or 0)
        h, rem = divmod(sec, 3600)
        m, s = divmod(rem, 60)
        self.lbl_midnight.setText(
            self._tr(
                "alliance13.midnight.countdown_fmt",
                "⏰ Nächster 00:00 UTC Reset in {h:02d}:{m:02d}:{s:02d}",
            ).format(h=h, m=m, s=s)
        )

    def _refresh_midnight(self) -> None:
        self.refresh_current_pillar(fetch_state=False)

    def _refresh_jobs(self, data: dict) -> None:
        jobs = list((data or {}).get("job_splits") or [])
        self.table_jobs.setRowCount(len(jobs))
        for ri, row in enumerate(jobs):
            if not isinstance(row, dict):
                continue
            self.table_jobs.setItem(
                ri, 0, QTableWidgetItem(str(row.get("route") or "—"))
            )
            self.table_jobs.setItem(
                ri, 1, QTableWidgetItem(f"{float(row.get('share_pct', 0) or 0):.1f}%")
            )
            self.table_jobs.setItem(
                ri, 2, QTableWidgetItem(str(row.get("pilot") or "—"))
            )
            self.table_jobs.setItem(
                ri, 3, QTableWidgetItem(str(row.get("status") or "open"))
            )
            self.table_jobs.setItem(
                ri, 4, QTableWidgetItem(f"{float(row.get('credits', 0) or 0):,.0f}")
            )

    def _refresh_shipyard(self, data: dict) -> None:
        parts = list((data or {}).get("shipyard_parts") or [])
        self.table_shipyard.setRowCount(len(parts))
        for ri, row in enumerate(parts):
            if not isinstance(row, dict):
                continue
            self.table_shipyard.setItem(
                ri, 0, QTableWidgetItem(str(row.get("part_type") or "—"))
            )
            self.table_shipyard.setItem(
                ri, 1, QTableWidgetItem(str(int(row.get("qty", 0) or 0)))
            )
            self.table_shipyard.setItem(
                ri, 2, QTableWidgetItem(str(row.get("condition") or "—"))
            )
            self.table_shipyard.setItem(
                ri, 3, QTableWidgetItem(str(row.get("holder") or "pool"))
            )
            self.table_shipyard.setItem(
                ri, 4, QTableWidgetItem(str(row.get("status") or "—"))
            )

    def _on_donate(self) -> None:
        amt = float(self.spin_donate.value())
        if hasattr(self.mw, "_on_alliance_donate_clicked"):
            if hasattr(self.mw, "spin_alliance_donate"):
                self.mw.spin_alliance_donate.setValue(amt)
            self.mw._on_alliance_donate_clicked()
        else:
            self._post("/api/v1/user/alliance/donate", {"amount": amt})
        QTimer.singleShot(400, lambda: self.refresh_current_pillar(fetch_state=True))

    def _on_dividend(self) -> None:
        dash = getattr(self.mw, "advanced_alliance_dashboard", None)
        if dash is not None and hasattr(dash, "execute_distribute_dividends"):
            dash.execute_distribute_dividends()
        else:
            self._post(
                "/api/v1/alliance/finance/distribute_dividends",
                {"amount": float(self.spin_donate.value())},
            )
        QTimer.singleShot(400, lambda: self.refresh_current_pillar(fetch_state=True))

    def _on_fuel_buy(self) -> None:
        extra = {"liters": int(self.spin_fuel_liters.value())}

        def _done(j: object) -> None:
            if isinstance(j, dict) and not j.get("ok"):
                QMessageBox.warning(self.mw, "Fuel", str(j.get("error") or "failed"))
            self.refresh_current_pillar(fetch_state=True)

        self._run_async(
            lambda: self._post_blocking("/api/v1/alliance/fuel/buy", extra),
            _done,
        )

    def _on_job_split(self) -> None:
        route = self.edit_job_route.text().strip().upper()
        parts = int(self.spin_job_parts.value())
        extra = {"route": route, "parts": parts}

        def _done(j: object) -> None:
            if isinstance(j, dict) and not j.get("ok"):
                QMessageBox.warning(self.mw, "Jobs", str(j.get("error") or "failed"))
            self.refresh_current_pillar(fetch_state=True)

        self._run_async(
            lambda: self._post_blocking("/api/v1/alliance/jobs/split", extra),
            _done,
        )

    def _on_route_lease(self) -> None:
        route = self.edit_lease_route.text().strip().upper()
        fee = float(self.spin_lease_fee.value())
        extra = {"route": route, "fee_per_flight": fee}

        def _done(j: object) -> None:
            if isinstance(j, dict) and not j.get("ok"):
                QMessageBox.warning(self.mw, "Routes", str(j.get("error") or "failed"))
            if hasattr(self.mw, "_refresh_alliance_panel"):
                self.mw._refresh_alliance_panel()
            self.refresh_current_pillar(fetch_state=True)

        self._run_async(
            lambda: self._post_blocking("/api/v1/web/alliance/route-lease", extra),
            _done,
        )

    def _on_shipyard_deposit(self) -> None:
        extra = {
            "part_type": self.edit_part_type.text().strip(),
            "qty": int(self.spin_part_qty.value()),
        }

        def _done(j: object) -> None:
            if isinstance(j, dict) and not j.get("ok"):
                QMessageBox.warning(self.mw, "Shipyard", str(j.get("error") or "failed"))
            self.refresh_current_pillar(fetch_state=True)

        self._run_async(
            lambda: self._post_blocking("/api/v1/alliance/shipyard/deposit", extra),
            _done,
        )

    def _on_shipyard_take(self) -> None:
        extra = {
            "part_type": self.edit_part_type.text().strip(),
            "qty": int(self.spin_part_qty.value()),
        }

        def _done(j: object) -> None:
            if isinstance(j, dict) and not j.get("ok"):
                QMessageBox.warning(self.mw, "Shipyard", str(j.get("error") or "failed"))
            self.refresh_current_pillar(fetch_state=True)

        self._run_async(
            lambda: self._post_blocking("/api/v1/alliance/shipyard/withdraw", extra),
            _done,
        )

    def _selected_member_hwid(self) -> str:
        row = self.table_members.currentRow()
        if row < 0:
            return ""
        it = self.table_members.item(row, 0)
        if it is None:
            return ""
        data = it.data(Qt.ItemDataRole.UserRole)
        return str(data or it.text() or "").strip()

    def _on_members_context(self, pos) -> None:
        self._on_member_promote()

    def _on_insurance_sync(self) -> None:
        fn = getattr(self.mw, "_request_alliance_mega_state", None)
        if callable(fn):
            fn()
        self.refresh_current_pillar(fetch_state=True)

    def _on_member_promote(self) -> None:
        hw = self._selected_member_hwid()
        if not hw:
            return
        role = str(self.combo_member_role.currentData() or "member")
        if hasattr(self.mw, "_alliance_post"):
            self.mw._alliance_post(
                "/api/v1/user/alliance/member_action",
                {"target_hardware_id": hw, "action": "set_role", "role": role},
            )
        else:
            self._post(
                "/api/v1/user/alliance/member_action",
                {"target_hardware_id": hw, "action": "set_role", "role": role},
            )
        QTimer.singleShot(500, lambda: self.refresh_current_pillar(fetch_state=True))


def fix_crew_hub_overlap(main_window: Any, injector: Any) -> None:
    """Crew-Hub: eine Scroll-Ebene, expanding — kein Überlappen."""
    if getattr(main_window, "_platin_crew_layout_fixed", False):
        return
    intro = getattr(main_window, "label_crew_intro", None)
    if intro is None:
        return
    sa = getattr(main_window, "scroll_hr_portal", None) or getattr(
        main_window, "scroll_hr_candidates", None
    )
    if isinstance(sa, QScrollArea):
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.Shape.NoFrame)
        sa.setStyleSheet(PLATIN_BLUE_SCROLL_CSS)
        sa.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
    root = intro
    for _ in range(12):
        p = root.parentWidget()
        if p is None:
            break
        root = p
    root.setSizePolicy(
        QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
    )
    main_window._platin_crew_layout_fixed = True
