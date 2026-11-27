"""Explorer-style tab strip and command bar for GNOME Files."""

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
gi.require_version("Nautilus", "4.0")
from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk, Nautilus


_STYLE = """
.explorer-title-row {
    background-color: var(--headerbar-bg-color);
    border-bottom: 1px solid var(--border-color);
    padding: 0 7px;
}
tabbar.explorer-tabs .box {
    background-color: transparent;
    box-shadow: none;
    padding: 0;
}
.explorer-sidebar-header { min-height: 36px; }
.explorer-sidebar-header button { min-height: 28px; min-width: 28px; }
tabbar.explorer-tabs tabbox {
    padding-top: 5px;
    padding-bottom: 4px;
}
tabbar.explorer-tabs tab { min-width: 232px; }
tabbar.explorer-tabs tabbox tab:selected,
tabbar.explorer-tabs tabbox.single-tab tab {
    background-color: var(--card-bg-color);
    box-shadow: inset 0 0 0 1px var(--border-color), inset 0 -2px var(--accent-color);
}
.explorer-new-tab { margin: 0 2px; border-radius: 8px; }
.explorer-commands {
    background-color: var(--headerbar-bg-color);
    border-bottom: 1px solid var(--border-color);
    padding: 3px 7px;
}
.explorer-commands button { border-radius: 7px; }
.explorer-commands separator { margin: 6px 4px; }
.explorer-command-window .diskinfo-panel label.heading {
    font-size: 1.13em;
    font-weight: 700;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--border-color);
}
.explorer-command-window .diskinfo-panel flowboxchild {
    border-radius: 10px;
}
.explorer-command-window .diskinfo-panel flowboxchild:not(:selected) {
    box-shadow: inset 0 0 0 1px var(--border-color);
}
.explorer-command-window .diskinfo-panel flowboxchild > .nautilus-view-cell {
    padding: 5px 9px;
}
.explorer-command-window .diskinfo-panel .unmounted {
    opacity: 0.82;
}
.explorer-command-window .diskinfo-panel .diskinfo-subtext {
    color: color-mix(in srgb, var(--window-fg-color) 76%, var(--window-bg-color));
    font-feature-settings: "tnum";
}
.explorer-command-window .diskinfo-panel levelbar.diskinfo-bar block {
    min-height: 5px;
    border-radius: 3px;
}
"""


def _widgets(widget):
    yield widget
    child = widget.get_first_child()
    while child is not None:
        yield from _widgets(child)
        child = child.get_next_sibling()


def _button(icon, label, action):
    button = Gtk.Button(icon_name=icon, action_name=action, tooltip_text=label)
    button.update_property([Gtk.AccessibleProperty.LABEL], [label])
    button.add_css_class("flat")
    return button


def _menu_button(label, entries, *, icon=None):
    model = Gio.Menu()
    for text, action, target in entries:
        item = Gio.MenuItem.new(text, None)
        item.set_action_and_target_value(action, target)
        model.append_item(item)
    button = Gtk.MenuButton(menu_model=model, tooltip_text=label)
    if icon:
        button.set_icon_name(icon)
    else:
        button.set_label(label)
    button.update_property([Gtk.AccessibleProperty.LABEL], [label])
    button.add_css_class("flat")
    return button


class ExplorerTabLayout(Gtk.LayoutManager):
    """Place the native tab contents at the leading edge of a wide tab."""

    def do_measure(self, tab, orientation, for_size):
        if orientation == Gtk.Orientation.HORIZONTAL:
            return 0, 118, -1, -1
        sizes = [child.measure(orientation, -1) for child in tab
                 if child.should_layout()]
        return (max((size[0] for size in sizes), default=0),
                max((size[1] for size in sizes), default=0), -1, -1)

    def do_allocate(self, tab, width, height, baseline):
        icon, title, indicator, close, attention = tab
        leading = 7
        trailing = width - 4
        rtl = tab.get_direction() == Gtk.TextDirection.RTL

        def place(child, start, size):
            area = Gdk.Rectangle()
            area.x = width - start - size if rtl else start
            area.y = 0
            area.width = size
            area.height = height
            child.size_allocate(area, baseline)

        def natural_width(child):
            return child.measure(Gtk.Orientation.HORIZONTAL, height)[1]

        if close.should_layout():
            close_width = natural_width(close)
            trailing -= close_width
            place(close, trailing, close_width)
        for child in (indicator, icon):
            if child.should_layout():
                size = natural_width(child)
                place(child, leading, size)
                leading += size
        if title.should_layout():
            # Adw updates its internal alignment on direction/indicator changes.
            if title.get_property("align") != 0.0:
                title.set_property("align", 0.0)
            place(title, leading, max(0, trailing - leading))
        if attention.should_layout():
            page = tab.get_property("page")
            size = min(36, width) if page and page.get_needs_attention() else 0
            place(attention, (width - size) // 2, size)


def _layout_tabs(model, position, _removed, added):
    for index in range(position, position + added):
        container = model.get_item(index)
        if container.get_css_name() != "tabboxchild":
            continue
        tab = container.get_first_child()
        if tab is None or tab.get_css_name() != "tab" or tab.has_css_class("pinned"):
            continue
        # Guard this adaptation to the known libadwaita tab template.
        children = list(tab)
        if ([child.get_css_name() for child in children] ==
                ["image", "widget", "button", "button", "indicator"]
                and children[1].has_css_class("tab-title")
                and children[1].find_property("align") is not None
                and children[2].has_css_class("tab-indicator")
                and children[3].has_css_class("tab-close-button")):
            tab.set_layout_manager(ExplorerTabLayout())


_HOME = Gio.File.new_for_path(GLib.get_home_dir())


def _update_tab_icon(slot, _property, page_ref):
    page = page_ref()
    if page is None:
        return
    location = slot.get_property("location")
    icon_name = "folder-symbolic"
    if location is not None:
        icon_name = {
            "computer": "computer-symbolic",
            "trash": "user-trash-symbolic",
            "recent": "document-open-recent-symbolic",
            "starred": "starred-symbolic",
            "network": "network-workgroup-symbolic",
        }.get(location.get_uri_scheme(), icon_name)
        if location.equal(_HOME):
            icon_name = "user-home-symbolic"
    icon = Gio.ThemedIcon.new(icon_name)
    if page.get_icon() is None or not icon.equal(page.get_icon()):
        page.set_icon(icon)


def _watch_tab_page(_view, page, _position):
    slot = page.get_child()
    if slot.find_property("location") is None or getattr(page, "_explorer_icon_watch", False):
        return
    page._explorer_icon_watch = True
    page_ref = page.weak_ref()
    slot.connect("notify::location", _update_tab_icon, page_ref)
    _update_tab_icon(slot, None, page_ref)


def _install_tab_titlebar(owner, tabs, toolbar, overlay, split):
    # The native tab bar still owns tab selection, scrolling, drag and close.
    tabs.add_css_class("explorer-tabs")
    tabs.set_autohide(False)
    tabs.set_expand_tabs(True)
    tabs.set_hexpand(False)
    for child in _widgets(tabs):
        if isinstance(child, Gtk.ScrolledWindow):
            child.set_propagate_natural_width(True)
        elif child.get_css_name() == "tabbox":
            model = child.observe_children()
            child._explorer_tab_children = model
            model.connect("items-changed", _layout_tabs)
            _layout_tabs(model, 0, 0, model.get_n_items())

    view = tabs.get_view()
    view.connect("page-attached", _watch_tab_page)
    for position in range(view.get_n_pages()):
        _watch_tab_page(view, view.get_nth_page(position), position)

    row = Gtk.Box(spacing=3)
    row.add_css_class("explorer-title-row")
    owner.remove(tabs)
    row.append(tabs)
    plus = _button("list-add-symbolic", "New tab (Ctrl+T)", "win.new-tab")
    plus.add_css_class("explorer-new-tab")
    plus.set_valign(Gtk.Align.CENTER)
    row.append(plus)
    row.append(Gtk.Box(hexpand=True))
    controls = Gtk.WindowControls(
        side=Gtk.PackType.END,
        decoration_layout=":minimize,maximize,close",
        valign=Gtk.Align.CENTER,
    )
    row.append(controls)

    # Keep a draggable region between the tabs and native window controls.
    handle = Gtk.WindowHandle(child=row)
    stack = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    stack.append(handle)
    overlay.set_child(None)
    split.set_vexpand(True)
    stack.append(split)
    overlay.set_child(stack)

    for area in (toolbar, split.get_sidebar()):
        header = next((child for child in _widgets(area)
                       if isinstance(child, Adw.HeaderBar)), None)
        if header is not None:
            header.set_show_start_title_buttons(False)
            header.set_show_end_title_buttons(False)
            if area != toolbar:
                header.add_css_class("explorer-sidebar-header")


def _command_bar(*, picker=False):
    bar = Gtk.Box(spacing=2)
    bar.add_css_class("explorer-commands")
    new = Gtk.Button(label="New folder", action_name="view.new-folder")
    new.add_css_class("flat")
    bar.append(new)

    groups = (
        (
            ("edit-cut-symbolic", "Cut", "view.cut"),
            ("edit-copy-symbolic", "Copy", "view.copy"),
            ("edit-paste-symbolic", "Paste", "view.paste"),
            ("document-edit-symbolic", "Rename", "view.rename"),
            ("user-trash-symbolic", "Move to Trash", "view.move-to-trash"),
        ),
        (
            ("go-up-symbolic", "Go up one folder", "slot.up"),
            ("view-refresh-symbolic", "Refresh", "slot.reload"),
        ),
    )
    for group in groups[-1:] if picker else groups:
        bar.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        for icon, label, action in group:
            bar.append(_button(icon, label, action))

    bar.append(Gtk.Box(hexpand=True))
    bar.append(_menu_button("Sort", [
        ("Name, A to Z", "view.sort", GLib.Variant("(sb)", ("name", False))),
        ("Name, Z to A", "view.sort", GLib.Variant("(sb)", ("name", True))),
        ("Date modified", "view.sort", GLib.Variant("(sb)", ("date_modified", True))),
        ("Size", "view.sort", GLib.Variant("(sb)", ("size", True))),
        ("Type", "view.sort", GLib.Variant("(sb)", ("type", False))),
    ]))
    bar.append(_menu_button("View", [
        ("Details", "slot.files-view-mode", GLib.Variant("u", 1)),
        ("Icons", "slot.files-view-mode", GLib.Variant("u", 2)),
        ("Show hidden files", "view.show-hidden-files", None),
        ("Choose columns", "view.visible-columns", None),
    ]))
    if picker:
        return bar
    bar.append(_menu_button("More commands", [
        ("Restore closed tab", "win.restore-tab", None),
        ("Select all", "view.select-all", None),
        ("Copy folder path", "view.copy-current-location", None),
        ("Properties", "view.properties", None),
        ("Folder properties", "view.current-directory-properties", None),
    ], icon="view-more-symbolic"))
    return bar


class ExplorerCommandBar(GObject.GObject, Nautilus.MenuProvider):
    def __init__(self):
        super().__init__()
        self._windows = Gtk.Window.get_toplevels()
        self._windows.connect("items-changed", self._on_windows_changed)
        self._provider = Gtk.CssProvider()
        self._provider.load_from_string(_STYLE)
        self._style_installed = False
        self._on_windows_changed(self._windows, 0, 0, self._windows.get_n_items())

    def _on_windows_changed(self, model, position, _removed, added):
        for index in range(position, position + added):
            window = model.get_item(index)
            if GObject.type_name(window.__gtype__) in {"NautilusWindow", "NautilusFileChooser"}:
                GLib.idle_add(self._decorate, window, priority=GLib.PRIORITY_LOW)

    def _decorate(self, window):
        if window.has_css_class("explorer-command-window"):
            return GLib.SOURCE_REMOVE

        template = {
            widget.get_buildable_id(): widget for widget in _widgets(window)
        }
        tabs = template.get("tab_bar")
        toolbar = template.get("toolbar")
        picker = GObject.type_name(window.__gtype__) == "NautilusFileChooser"
        owner = toolbar.get_ancestor(Adw.ToolbarView) if toolbar else None
        if owner is None:
            return GLib.SOURCE_REMOVE
        if not picker and (
            not isinstance(tabs, Adw.TabBar) or tabs.get_parent() != toolbar.get_parent()
        ):
            return GLib.SOURCE_REMOVE

        if not self._style_installed:
            Gtk.StyleContext.add_provider_for_display(
                window.get_display(), self._provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )
            self._style_installed = True

        window.add_css_class("explorer-command-window")
        if picker:
            owner.add_top_bar(_command_bar(picker=True))
            return GLib.SOURCE_REMOVE

        overlay = template.get("toast_overlay")
        split = template.get("split_view")
        if isinstance(overlay, Adw.ToastOverlay) and isinstance(split, Adw.OverlaySplitView):
            if overlay.get_child() == split and split.get_sidebar() is not None:
                _install_tab_titlebar(owner, tabs, toolbar, overlay, split)

        owner.add_top_bar(_command_bar())
        return GLib.SOURCE_REMOVE
