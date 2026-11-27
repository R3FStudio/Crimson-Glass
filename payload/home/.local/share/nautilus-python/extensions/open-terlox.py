"""Open local folders from Files in the preferred terminal."""

import gi

gi.require_version("Nautilus", "4.0")
from gi.repository import Gio, GLib, GObject, Nautilus


class OpenTerlox(GObject.GObject, Nautilus.MenuProvider):
    def get_background_items(self, current_folder):
        return self._items_for_folder(current_folder, "background")

    def get_file_items(self, files):
        if len(files) != 1 or not files[0].is_directory():
            return []
        return self._items_for_folder(files[0], "selection")

    def _items_for_folder(self, folder, context):
        path = folder.get_location().get_path()
        if path is None:
            return []

        item = Nautilus.MenuItem(
            name=f"OpenTerlox::{context}",
            label="Open in Terminal",
            tip="Open the selected folder in your default terminal",
        )
        item.connect("activate", self._open, path)
        return [item]

    def _open(self, _item, path):
        try:
            Gio.Subprocess.new(
                ["/usr/bin/xdg-terminal-exec", f"--dir={path}"],
                Gio.SubprocessFlags.NONE,
            )
        except GLib.Error as error:
            print(f"Could not start terminal: {error.message}")
