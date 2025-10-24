from __future__ import annotations

import threading
import webbrowser
from pathlib import Path
from typing import Dict, List, Optional

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Notify", "0.7")
from gi.repository import GLib, Gtk, Notify, Pango

try:
    gi.require_version("AyatanaAppIndicator3", "0.1")
    from gi.repository import AyatanaAppIndicator3 as AppIndicator3
except (ImportError, ValueError):
    gi.require_version("AppIndicator3", "0.1")
    from gi.repository import AppIndicator3

from .api import Deployment, VercelClient
from .config import load_config, save_config
from .preferences import PreferencesDialog


APPINDICATOR_ID = "vercel-deployments"


class VercelIndicator:
    """GNOME AppIndicator showing Vercel deployment status and quick links."""

    def __init__(self) -> None:
        self.indicator = AppIndicator3.Indicator.new(
            APPINDICATOR_ID,
            "vercel-deployments",
            AppIndicator3.IndicatorCategory.APPLICATION_STATUS,
        )
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)

        self.menu = Gtk.Menu()
        self.indicator.set_menu(self.menu)

        self._refresh_timer_id: Optional[int] = None
        self._refresh_in_progress = False
        self._last_overall_status: Optional[str] = None
        self._prod_seen: Dict[str, str] = {}
        self._prod_seen_bootstrapped: bool = False

        self._reconfigure()
        self._build_static_menu()
        # If no token is set yet, prompt preferences first to guide the user.
        # This avoids an immediate 401 and is friendlier UX.
        cfg = load_config()
        if not (cfg.get("token") or "").strip():
            GLib.idle_add(self._open_preferences, None)
        else:
            self._schedule_refresh(immediate=True)

    # -------- Configuration / Preferences --------
    def _reconfigure(self) -> None:
        cfg = load_config()
        self.refresh_interval = int(cfg.get("refresh_interval") or 30)
        self.max_items = int(cfg.get("max_items") or 10)
        token = str(cfg.get("token") or "")
        team_id = str(cfg.get("team_id") or "")
        self.client = VercelClient(token=token, team_id=team_id or None)
        val = cfg.get("notify_prod_events")
        self.notify_prod_events = True if val is None else bool(val)

    def _open_preferences(self, _widget: Gtk.MenuItem) -> None:
        dialog = PreferencesDialog(on_save=self._on_prefs_saved)
        dialog.set_modal(True)
        dialog.present()

    def _on_prefs_saved(self) -> None:
        # Re-read config and restart refresh loop
        self._reconfigure()
        self._schedule_refresh(immediate=True)

    # -------- Menu construction --------
    def _build_static_menu(self) -> None:
        for child in list(self.menu.get_children()):
            self.menu.remove(child)

        # Dynamic section will be inserted before the separator
        self.dynamic_section = Gtk.Menu()

        # We'll rebuild dynamic items directly on self.menu (no submenus)
        header = Gtk.MenuItem(label="Vercel Deployments")
        header.set_sensitive(False)
        self.menu.append(header)

        self._dynamic_insert_position = 1  # after header

        self.menu.append(Gtk.SeparatorMenuItem())

        item_refresh = Gtk.MenuItem(label="Refresh now")
        item_refresh.connect("activate", self._manual_refresh)
        self.menu.append(item_refresh)

        item_prefs = Gtk.MenuItem(label="Preferences…")
        item_prefs.connect("activate", self._open_preferences)
        self.menu.append(item_prefs)

        self.menu.append(Gtk.SeparatorMenuItem())

        item_quit = Gtk.MenuItem(label="Quit")
        item_quit.connect("activate", self._quit)
        self.menu.append(item_quit)

        self.menu.show_all()

    def _rebuild_dynamic_items(self, deployments: List[Deployment]) -> None:
        # Remove any previous dynamic items (between header and first separator)
        children = self.menu.get_children()
        # header at index 0, separator at index 1 currently; dynamic items go from 1..(before first separator we appended later)
        # We will rebuild all items and re-add separators accordingly for simplicity.
        self._build_static_menu()

        insert_index = 1  # after header
        for dep in deployments[: self.max_items]:
            # Visual status hint using emoji for quick scanning
            status_emoji = {
                "ready": "✅",
                "building": "🟡",
                "error": "❌",
            }.get(dep.status, "🟡")

            branch = dep.branch or "?"
            short_sha = dep.commit_sha[:7] if dep.commit_sha else ""
            author = dep.author or ""
            target = dep.target or ""

            primary = dep.name or "(unknown)"
            when = self._humanize_time(dep.created_at)
            
            # Create main menu item with compact info
            main_item = Gtk.MenuItem()
            main_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            main_row.set_margin_start(6)
            main_row.set_margin_end(6)
            main_row.set_margin_top(2)
            main_row.set_margin_bottom(2)
            
            # Compact label: status + project + author + time
            compact_text = f"{status_emoji} {primary} · {author} · {when}"
            compact_label = Gtk.Label(label=compact_text)
            compact_label.set_xalign(0)
            compact_label.set_ellipsize(Pango.EllipsizeMode.END)
            compact_label.set_hexpand(True)
            
            main_row.pack_start(compact_label, True, True, 0)
            main_item.add(main_row)
            
            # Create submenu with detailed info
            submenu = Gtk.Menu()
            main_item.set_submenu(submenu)
            
            # Header with project name and status
            header_item = Gtk.MenuItem(label=f"{status_emoji} {primary} — {dep.status}")
            header_item.set_sensitive(False)
            submenu.append(header_item)
            
            submenu.append(Gtk.SeparatorMenuItem())
            
            # Environment and branch info
            if target or branch:
                env_text = f"Environment: {target or 'unknown'}"
                if branch:
                    env_text += f" • Branch: {branch}"
                env_item = Gtk.MenuItem(label=env_text)
                env_item.set_sensitive(False)
                submenu.append(env_item)
            
            # Commit info
            if short_sha:
                commit_text = f"Commit: {short_sha}"
                if dep.commit_message:
                    commit_text += f" • {dep.commit_message.strip()}"
                commit_item = Gtk.MenuItem(label=commit_text)
                commit_item.set_sensitive(False)
                submenu.append(commit_item)
            
            # Author and time
            author_text = f"Author: {author}" if author else "Author: unknown"
            time_text = f"Deployed: {when}"
            author_item = Gtk.MenuItem(label=author_text)
            author_item.set_sensitive(False)
            submenu.append(author_item)
            
            time_item = Gtk.MenuItem(label=time_text)
            time_item.set_sensitive(False)
            submenu.append(time_item)
            
            submenu.append(Gtk.SeparatorMenuItem())
            
            # Preview button (opens deployment URL)
            if dep.url:
                preview_item = Gtk.MenuItem(label="🔗 Preview")
                def on_preview(_w: Gtk.MenuItem, d: Deployment = dep) -> None:
                    webbrowser.open_new_tab(f"https://{d.url}" if not d.url.startswith("http") else d.url)
                preview_item.connect("activate", on_preview)
                submenu.append(preview_item)
            
            
            # Insert after header keeping the original ordering
            self.menu.insert(main_item, insert_index)
            insert_index += 1

        self.menu.show_all()

    # -------- Refresh logic --------
    def _set_icon_for_status(self, status: str) -> None:
        # Keep the indicator icon as the Vercel logo for brand recognition.
        # We communicate status via menu emojis and notifications.
        self.indicator.set_icon("vercel-menu-indicator-symbolic")

    def _overall_status(self, deployments: List[Deployment]) -> str:
        if any(d.status == "building" for d in deployments):
            return "building"
        if any(d.status == "error" for d in deployments):
            return "error"
        return "ready"

    def _manual_refresh(self, _widget: Gtk.MenuItem) -> None:
        self._schedule_refresh(immediate=True)

    def _schedule_refresh(self, immediate: bool = False) -> None:
        if self._refresh_timer_id is not None:
            GLib.source_remove(self._refresh_timer_id)
            self._refresh_timer_id = None

        if immediate:
            self._spawn_refresh_thread()

        # Note: return True keeps the timeout repeating
        self._refresh_timer_id = GLib.timeout_add_seconds(self.refresh_interval, self._refresh_timeout_cb)

    def _refresh_timeout_cb(self) -> bool:
        self._spawn_refresh_thread()
        return True

    def _spawn_refresh_thread(self) -> None:
        if self._refresh_in_progress:
            return
        self._refresh_in_progress = True

        def worker() -> None:
            try:
                deployments = self.client.list_deployments(limit=self.max_items)
            except Exception as exc:
                deployments = []
                # Show error state icon if request fails
                GLib.idle_add(self._set_icon_for_status, "error")
                Notify.Notification.new("Vercel", f"Failed to fetch deployments: {exc}", None).show()
            GLib.idle_add(self._apply_update, deployments)

        threading.Thread(target=worker, daemon=True).start()

    def _apply_update(self, deployments: List[Deployment]) -> None:
        self._refresh_in_progress = False
        self._rebuild_dynamic_items(deployments)

        overall = self._overall_status(deployments) if deployments else "error"
        self._set_icon_for_status(overall)
        if overall != self._last_overall_status and self._last_overall_status is not None:
            # Notify on state change after first refresh
            Notify.Notification.new("Vercel", f"Overall status: {overall}", None).show()
        self._last_overall_status = overall

        # Notify on production deployment events (new or status changes)
        if self.notify_prod_events:
            self._notify_production_events(deployments)

    # -------- App lifecycle --------
    def _quit(self, _widget: Gtk.MenuItem) -> None:
        Gtk.main_quit()

    # -------- Notifications for production deployments --------
    def _notify_production_events(self, deployments: List[Deployment]) -> None:
        # Bootstrap: on the very first refresh we only record state to avoid spamming
        production = [d for d in deployments if (d.target or "").lower() == "production"]
        if not self._prod_seen_bootstrapped:
            for d in production:
                self._prod_seen[d.id] = d.status
            self._prod_seen_bootstrapped = True
            return

        for d in production:
            previous = self._prod_seen.get(d.id)
            if previous is None or previous != d.status:
                self._send_prod_notification(d)
                self._prod_seen[d.id] = d.status

    def _send_prod_notification(self, d: Deployment) -> None:
        # Align notification details with the menu format for consistency.
        status_emoji = {
            "ready": "✅",
            "building": "🟡",
            "error": "❌",
        }.get(d.status, "🟡")
        short_sha = d.commit_sha[:7] if d.commit_sha else ""
        when = self._humanize_time(d.created_at)
        # First line: project, target and status
        title = f"{d.name} — production — {d.status} {status_emoji}"
        # Second line: branch, sha, commit message (snippet), author, time
        msg = (d.commit_message or "").strip().splitlines()[0] if d.commit_message else ""
        if msg and len(msg) > 80:
            msg = msg[:77] + "…"
        subtitle_bits = []
        if d.branch:
            subtitle_bits.append(d.branch)
        if short_sha:
            subtitle_bits.append(short_sha)
        if msg:
            subtitle_bits.append(msg)
        if d.author:
            subtitle_bits.append(d.author)
        subtitle_bits.append(when)
        body = " · ".join(subtitle_bits) if subtitle_bits else "Production deployment event"
        try:
            Notify.Notification.new("Vercel", f"{title}\n{body}", None).show()
        except Exception:
            pass

    # -------- Helpers --------
    def _humanize_time(self, dt_utc) -> str:
        # Convert to local timezone
        local = dt_utc.astimezone()
        now = GLib.DateTime.new_now_local()
        # Compare days
        today = GLib.DateTime.new_now_local().format("%Y-%m-%d")
        the_day = GLib.DateTime.new_from_unix_local(int(dt_utc.timestamp())).format("%Y-%m-%d")
        if the_day == today:
            return f"today at {dt_utc.astimezone().strftime('%H:%M')}"
        # Yesterday check
        y_dt = GLib.DateTime.new_now_local().add_days(-1)
        yesterday = y_dt.format("%Y-%m-%d")
        if the_day == yesterday:
            return f"yesterday at {dt_utc.astimezone().strftime('%H:%M')}"
        return dt_utc.astimezone().strftime("%b %d, %H:%M")



