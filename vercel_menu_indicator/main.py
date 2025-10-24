import signal

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Notify", "0.7")
from gi.repository import Gtk, Notify

from .indicator import VercelIndicator


def main() -> None:
    """Application entrypoint.

    Initializes notifications and starts the GTK main loop with the
    Vercel Deployments indicator.
    """
    Notify.init("Vercel Deployments")

    # Ensure Ctrl+C stops the app when run from terminal
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    _indicator = VercelIndicator()
    Gtk.main()


if __name__ == "__main__":
    main()


