#!/usr/bin/python3
"""Desktop controls for the wired HyperX Pulsefire Haste 2."""
from concurrent.futures import ThreadPoolExecutor
import sys

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

import haste2ctl as hid
from mouse_view import MouseView


STYLE = """
.preview { background: radial-gradient(ellipse at center, #321922, #15141c 65%, #111117);
           border: 1px solid alpha(#e05370, 0.25); border-radius: 19px; }
.preview-caption { color: #f3bbc7; padding: 12px; }
.device-title { font-size: 26px; font-weight: 800; letter-spacing: -0.5px; }
.section { margin-top: 12px; }
.status { padding: 9px 12px; border-radius: 10px; background: alpha(currentColor, .055); }
.status.error { color: #ff7890; }
"""
RATES = sorted(hid.POLL_RATES)


def unpack(reply):
    if len(reply) != hid.REPORT_LEN or reply[:2] != b"\x33\x02":
        raise hid.DevError("The mouse returned an unexpected settings report.")
    return (
        hid.divisor_to_poll_rate(reply[hid.RR_OFFSET]),
        tuple(hid.decode_dpi(hid.read_stage_code(reply, slot)) for slot in range(hid.MAX_STAGES)),
        reply[hid.STAGE_MASK_OFFSET] & 31,
        reply[hid.ACTIVE_STAGE_OFFSET],
    )


def mouse():
    node, _why = hid.find_vendor_node()
    return hid.Mouse(node)


def read_mouse():
    with mouse() as device:
        table = unpack(device.read_config()[0])
        level, _ack = device.read_brightness()
    return table, level


def apply_performance(rate, stages, mask):
    with mouse() as device:
        current, _ack = device.read_config()
        _, _, _, active = unpack(current)
        updated = bytearray(current)
        updated[hid.RR_OFFSET] = hid.poll_rate_to_divisor(rate)
        updated[hid.STAGE_MASK_OFFSET] = (current[hid.STAGE_MASK_OFFSET] & ~31) | mask
        for slot, dpi in enumerate(stages):
            hid.write_stage_code(updated, slot, hid.encode_dpi(dpi))
        if not (active < hid.MAX_STAGES and mask & (1 << active)):
            updated[hid.ACTIVE_STAGE_OFFSET] = (mask & -mask).bit_length() - 1
        if updated != current and device.write_config(updated) != 0:
            raise hid.DevError("The mouse did not acknowledge the settings write.")
        result = unpack(device.read_config()[0])
        if result[:3] != (rate, stages, mask):
            raise hid.DevError("The settings read back from the mouse differ. Use Read mouse to check them.")
        return result


def apply_lighting(rgb, level, set_color):
    with mouse() as device:
        if set_color and device.set_color(rgb) != [0, 0]:
            raise hid.DevError("The mouse did not acknowledge the RGB frame.")
        actual, ack = hid._set_brightness_verified(device, level)
        if ack != 0 or actual != level:
            raise hid.DevError("The mouse did not confirm the requested brightness.")
    return actual


def apply_button(label, callback):
    button = Gtk.Button(label=label, halign=Gtk.Align.END, margin_top=9)
    button.add_css_class("suggested-action")
    button.connect("clicked", callback)
    return button


class Studio(Adw.Application):
    def __init__(self):
        super().__init__(application_id="org.local.HasteStudio")
        self.worker = ThreadPoolExecutor(max_workers=1)
        self.win = None
        self.connected = False
        self.preview_mode = "--preview" in sys.argv

    def do_activate(self):
        if self.win is not None:
            self.win.present()
            return
        provider = Gtk.CssProvider()
        provider.load_from_string(STYLE)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.win = Adw.ApplicationWindow(application=self, title="Haste Studio",
                                         default_width=965, default_height=860)
        self.win.set_size_request(760, 545)
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title="Haste Studio", subtitle="Mouse configuration"))
        self.read = Gtk.Button(label="Read mouse")
        self.read.connect("clicked", lambda _btn: self.read_mouse())
        header.pack_end(self.read)
        toolbar.add_top_bar(header)
        self.win.set_content(toolbar)

        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        toolbar.set_content(scroll)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=13,
                          margin_top=20, margin_bottom=20, margin_start=24, margin_end=24)
        scroll.set_child(content)

        title = Gtk.Label(label="Pulsefire Haste 2", xalign=0)
        title.add_css_class("device-title")
        content.append(title)
        sub = Gtk.Label(label="HYPERX   /   WIRED USB   /   03F0:0B97", xalign=0)
        sub.add_css_class("dim-label")
        content.append(sub)

        body = Gtk.Box(spacing=22)
        content.append(body)
        preview_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        preview_card.add_css_class("preview")
        self.preview = MouseView()
        preview_card.append(self.preview)
        caption = Gtk.Label(label="DRAG TO ROTATE  ·  RGB PREVIEW", justify=Gtk.Justification.CENTER)
        caption.add_css_class("preview-caption")
        preview_card.append(caption)
        body.append(preview_card)

        controls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, width_request=354, spacing=2)
        body.append(controls)
        performance = Adw.PreferencesGroup(title="Performance", description="USB report rate and up to five DPI stages.")
        controls.append(performance)
        self.rates = Adw.ComboRow(title="Polling rate",
            model=Gtk.StringList.new([f"{rate:,} Hz" for rate in RATES]))
        performance.add(self.rates)

        self.stages = []
        for i in range(hid.MAX_STAGES):
            row = Adw.ActionRow(title=f"DPI stage {i + 1}")
            stage = Gtk.SpinButton.new_with_range(hid.DPI_MIN, hid.DPI_MAX, hid.DPI_STEP)
            stage.set_valign(Gtk.Align.CENTER)
            stage.set_width_chars(5)
            stage.set_snap_to_ticks(True)
            stage.update_property([Gtk.AccessibleProperty.LABEL], [f"DPI stage {i + 1} value"])
            enabled = Gtk.Switch(valign=Gtk.Align.CENTER)
            enabled.update_property([Gtk.AccessibleProperty.LABEL], [f"Enable DPI stage {i + 1}"])
            row.add_suffix(stage)
            row.add_suffix(enabled)
            performance.add(row)
            self.stages.append((row, stage, enabled))
        self.performance_button = apply_button("Apply performance", self.save_performance)
        controls.append(self.performance_button)

        lighting = Adw.PreferencesGroup(title="RGB lighting", description="Static color and brightness.")
        lighting.add_css_class("section")
        controls.append(lighting)
        self.color = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(title="Mouse RGB color", with_alpha=False),
                                           valign=Gtk.Align.CENTER)
        rgba = Gdk.RGBA()
        rgba.parse("#f2334d")
        self.color.set_rgba(rgba)
        color_row = Adw.ActionRow(title="Static LED color", subtitle="Enable to send this color to the mouse")
        self.apply_color = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.apply_color.update_property([Gtk.AccessibleProperty.LABEL], ["Apply static LED color"])
        color_row.add_suffix(self.color)
        color_row.add_suffix(self.apply_color)
        lighting.add(color_row)

        self.brightness = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 255, 1)
        self.brightness.set_size_request(116, -1)
        self.brightness.set_valign(Gtk.Align.CENTER)
        self.brightness.update_property([Gtk.AccessibleProperty.LABEL], ["LED brightness"])
        self.level_row = Adw.ActionRow(title="Brightness")
        self.level_row.add_suffix(self.brightness)
        lighting.add(self.level_row)
        self.color.connect("notify::rgba", self.color_changed)
        self.brightness.connect("value-changed", self.update_preview)
        self.lighting_button = apply_button("Apply lighting", self.save_lighting)
        controls.append(self.lighting_button)

        self.status = Gtk.Label(xalign=0, wrap=True)
        self.status.add_css_class("status")
        content.append(self.status)
        self.win.present()
        if self.preview_mode:
            self.show_performance((1000, (400, 800, 1600, 3200, 6400), 15, 1))
            self.brightness.set_value(175)
            self.set_status("Preview mode · mouse settings are untouched")
            self.set_busy(False)
        else:
            self.read_mouse()

    def set_status(self, message, error=False):
        self.status.set_text(message)
        if error:
            self.status.add_css_class("error")
        else:
            self.status.remove_css_class("error")

    def set_busy(self, busy):
        self.read.set_sensitive(not busy and not self.preview_mode)
        for button in (self.performance_button, self.lighting_button):
            button.set_sensitive(not busy and self.connected and not self.preview_mode)

    def run_io(self, operation, callback, message):
        self.set_busy(True)
        self.set_status(message)
        task = self.worker.submit(operation)

        def finish():
            try:
                value = task.result()
            except (hid.DevError, OSError) as error:
                message = str(error).splitlines()[0]
                if "permission denied" in message:
                    message = "Mouse detected. Enable access for its configuration interface, then click Read mouse."
                self.set_status(message, error=True)
            else:
                callback(value)
            finally:
                self.set_busy(False)
            return GLib.SOURCE_REMOVE

        task.add_done_callback(lambda _task: GLib.idle_add(finish))

    def read_mouse(self):
        self.connected = False
        self.run_io(read_mouse, self.show_readings, "Reading the mouse…")

    def show_readings(self, value):
        table, brightness = value
        self.show_performance(table)
        self.brightness.set_value(brightness)
        self.connected = True
        self.set_status("Connected · Changes apply to the live profile.")

    def show_performance(self, table):
        rate, dpis, mask, active = table
        self.rates.set_selected(RATES.index(rate) if rate in RATES else Gtk.INVALID_LIST_POSITION)
        for i, ((row, stage, enabled), dpi) in enumerate(zip(self.stages, dpis)):
            enabled.set_active(bool(mask & (1 << i)))
            stage.set_value(dpi)
            row.set_subtitle("Active on mouse" if i == active else "")

    def save_performance(self, _button):
        rate = self.rates.get_selected()
        mask = sum(1 << i for i, (_, _, enabled) in enumerate(self.stages) if enabled.get_active())
        dpis = tuple(stage.get_value_as_int() for _, stage, _ in self.stages)
        if not mask or rate >= len(RATES):
            self.set_status("Choose a polling rate and enable at least one DPI stage.", error=True)
            return

        def applied(table):
            self.show_performance(table)
            self.set_status("Performance settings applied and read back from the mouse.")

        self.run_io(lambda: apply_performance(RATES[rate], dpis, mask), applied, "Applying performance settings…")

    def color_changed(self, *_args):
        self.apply_color.set_active(True)
        self.update_preview()

    def update_preview(self, *_args):
        rgba = self.color.get_rgba()
        self.preview.rgb = rgba.red, rgba.green, rgba.blue
        self.preview.brightness = self.brightness.get_value() / 255
        self.level_row.set_subtitle(f"{self.preview.brightness:.0%}")
        self.preview.queue_draw()

    def save_lighting(self, _button):
        rgba = self.color.get_rgba()
        rgb = tuple(round(value * 255) for value in (rgba.red, rgba.green, rgba.blue))
        level = round(self.brightness.get_value())
        changed = self.apply_color.get_active()

        def applied(actual):
            self.brightness.set_value(actual)
            self.set_status("Lighting applied. Brightness read back from the mouse.")

        self.run_io(lambda: apply_lighting(rgb, level, changed), applied, "Applying lighting…")


if __name__ == "__main__":
    sys.exit(Studio().run([sys.argv[0]]))
