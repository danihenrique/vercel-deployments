from __future__ import annotations

from typing import Callable, Optional

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from .config import load_config, save_config


class PreferencesDialog(Gtk.Dialog):
    """Simple preferences dialog to edit token, team and refresh options."""

    def __init__(self, on_save: Optional[Callable[[], None]] = None) -> None:
        super().__init__(title="Preferences")
        self.on_save = on_save
        self.set_default_size(420, 200)

        content = self.get_content_area()

        grid = Gtk.Grid(column_spacing=8, row_spacing=8, margin=12)
        content.add(grid)

        lbl_token = Gtk.Label(label="Vercel API Token:")
        lbl_token.set_xalign(0)
        self.entry_token = Gtk.Entry()
        self.entry_token.set_visibility(False)
        self.entry_token.set_invisible_char("•")

        lbl_team = Gtk.Label(label="Team ID (slug):")
        lbl_team.set_xalign(0)
        self.entry_team = Gtk.Entry()

        lbl_interval = Gtk.Label(label="Refresh interval (s):")
        lbl_interval.set_xalign(0)
        self.spin_interval = Gtk.SpinButton.new_with_range(5, 300, 5)

        lbl_max = Gtk.Label(label="Max items:")
        lbl_max.set_xalign(0)
        self.spin_max = Gtk.SpinButton.new_with_range(1, 50, 1)

        lbl_notify = Gtk.Label(label="Notify production events:")
        lbl_notify.set_xalign(0)
        self.chk_notify = Gtk.CheckButton()

        # Layout grid
        grid.attach(lbl_token, 0, 0, 1, 1)
        grid.attach(self.entry_token, 1, 0, 1, 1)
        grid.attach(lbl_team, 0, 1, 1, 1)
        grid.attach(self.entry_team, 1, 1, 1, 1)
        grid.attach(lbl_interval, 0, 2, 1, 1)
        grid.attach(self.spin_interval, 1, 2, 1, 1)
        grid.attach(lbl_max, 0, 3, 1, 1)
        grid.attach(self.spin_max, 1, 3, 1, 1)
        grid.attach(lbl_notify, 0, 4, 1, 1)
        grid.attach(self.chk_notify, 1, 4, 1, 1)

        # Buttons
        self.add_button("Cancel", Gtk.ResponseType.CANCEL)
        self.add_button("Save", Gtk.ResponseType.OK)

        self._load_from_config()

        self.connect("response", self._on_response)

        # Ensure all child widgets are visible when the dialog is presented.
        # GTK dialogs don't automatically show newly added children unless
        # show() / show_all() is invoked on the toplevel.
        self.show_all()

    def _load_from_config(self) -> None:
        cfg = load_config()
        self.entry_token.set_text(str(cfg.get("token") or ""))
        self.entry_team.set_text(str(cfg.get("team_id") or ""))
        self.spin_interval.set_value(float(cfg.get("refresh_interval") or 30))
        self.spin_max.set_value(float(cfg.get("max_items") or 10))
        val = cfg.get("notify_prod_events")
        self.chk_notify.set_active(True if val is None else bool(val))

    def _on_response(self, _dialog: Gtk.Dialog, response_id: int) -> None:
        if response_id == Gtk.ResponseType.OK:
            save_config(
                {
                    "token": self.entry_token.get_text().strip(),
                    "team_id": self.entry_team.get_text().strip(),
                    "refresh_interval": int(self.spin_interval.get_value()),
                    "max_items": int(self.spin_max.get_value()),
                    "notify_prod_events": bool(self.chk_notify.get_active()),
                }
            )
            if self.on_save:
                self.on_save()
        self.destroy()


