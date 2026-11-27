"""Resolve the desktop GTK palette for the app's CSS and Cairo drawings."""

import os
import re
from pathlib import Path

from gi.repository import GLib, Gtk


# Modern GTK palettes use CSS variables. Older themes expose named colors.
ROLES = {
    'background': ('window-bg-color', 'theme_bg_color'),
    'foreground': ('window-fg-color', 'theme_fg_color'),
    'sidebar': ('sidebar-bg-color', ''),
    'header': ('headerbar-bg-color', ''),
    'surface': ('card-bg-color', ''),
    'popover': ('popover-bg-color', ''),
    'border': ('border-color', 'borders'),
    'accent': ('accent-bg-color', 'theme_selected_bg_color'),
    'metric': ('accent-color', ''),
    'selection': ('accent-bg-color', 'theme_selected_bg_color'),
    'selection_foreground': ('accent-fg-color', 'theme_selected_fg_color'),
}


def legacy_colors(name, variant):
    """Read named colors from a GTK3-only theme without loading its widget CSS."""
    if name in ('', '.', '..') or '/' in name:
        return ''
    if variant and ('/' in variant or '\\' in variant):
        variant = ''
    theme_dirs = [
        Path(GLib.get_user_data_dir()) / 'themes',
        Path.home() / '.themes',
        *(Path(path) / 'themes' for path in GLib.get_system_data_dirs()),
        Path(os.environ.get('GTK_DATA_PREFIX', '/usr')) / 'share/themes',
    ]
    themes = [directory / name for directory in theme_dirs]
    files = [f'gtk-{variant}.css', 'gtk.css'] if variant else ['gtk.css']
    minor = Gtk.get_minor_version()
    gtk4_dirs = (f'gtk-4.{version}' for version in range(minor + minor % 2, -1, -2))
    for directory in gtk4_dirs:
        if any((theme / directory / file).is_file() for theme in themes for file in files):
            return ''

    for file in files:
        for theme in themes:
            try:
                css = (theme / 'gtk-3.0' / file).read_text(encoding='utf-8')
            except (OSError, UnicodeError):
                continue
            css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
            return '\n'.join(re.findall(r'@define-color\s+[\w-]+\s+[^;{}]+;', css))
    return ''


def hex_color(color):
    return '#' + ''.join(f'{round(channel * 255):02x}' for channel in
                         (color.red, color.green, color.blue))


def mix(background, foreground, fraction):
    return '#' + ''.join(
        f'{round(int(background[i:i+2], 16) * (1 - fraction) + int(foreground[i:i+2], 16) * fraction):02x}'
        for i in (1, 3, 5)
    )


def luminance(color):
    rgb = [int(color[i:i+2], 16) / 255 for i in (1, 3, 5)]
    linear = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4 for value in rgb]
    return sum(channel * weight for channel, weight in zip(linear, (.2126, .7152, .0722)))


def contrast(first, second):
    dark, light = sorted((luminance(first), luminance(second)))
    return (light + .05) / (dark + .05)


class GtkPalette:
    def __init__(self, settings):
        self.settings = settings
        self.theme = None
        self.legacy_provider = None
        self.probes = {}
        provider = Gtk.CssProvider()
        rules = []
        for role, (variable, _) in ROLES.items():
            probe = Gtk.Label()
            probe.add_css_class('rice-probe-' + role)
            context = probe.get_style_context()
            context.add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)
            rules.append(f'.rice-probe-{role} {{ color: var(--{variable}, transparent); }}')
            self.probes[role] = probe
        if Gtk.get_minor_version() >= 16:
            provider.load_from_data('\n'.join(rules).encode())

    def colors(self, force=False):
        override = os.environ.get('GTK_THEME')
        if override:
            name, _, variant = override.rpartition(':') if ':' in override else (override, '', '')
        else:
            name = self.settings.get_property('gtk-theme-name') or ''
            variant = 'dark' if self.settings.get_property('gtk-application-prefer-dark-theme') else ''
        user_css = Path(GLib.get_user_config_dir()) / 'gtk-4.0/gtk.css'
        if not force and not override and name in ('', 'Default', 'Adwaita') and not user_css.is_file():
            return None
        if (name, variant) != self.theme:
            legacy = legacy_colors(name, variant)
            provider = None
            if legacy:
                provider = Gtk.CssProvider()
                provider.load_from_data(legacy.encode())
            for probe in self.probes.values():
                context = probe.get_style_context()
                if self.legacy_provider is not None:
                    context.remove_provider(self.legacy_provider)
                if provider is not None:
                    context.add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)
            self.legacy_provider = provider
            self.theme = name, variant

        colors = {}
        for role, (_, named_color) in ROLES.items():
            probe = self.probes[role]
            if Gtk.get_minor_version() >= 16:
                color = probe.get_color()
                if color.alpha >= .99:
                    colors[role] = hex_color(color)
                    continue
            if named_color and (role != 'border' or self.legacy_provider is None):
                found, color = probe.get_style_context().lookup_color(named_color)
                if found and color.alpha >= .99:
                    colors[role] = hex_color(color)
        if not {'background', 'foreground', 'accent'} <= colors.keys():
            return None

        background, foreground, accent = (colors[key] for key in ('background', 'foreground', 'accent'))
        if contrast(background, foreground) < 4.5:
            foreground = max(('#000000', '#ffffff'), key=lambda color: contrast(background, color))
            colors['foreground'] = foreground
        colors.setdefault('sidebar', background)
        colors.setdefault('header', colors['sidebar'])
        colors.setdefault('surface', mix(background, foreground, .06))
        colors.setdefault('popover', colors['surface'])
        colors.setdefault('border', mix(background, foreground, .22))
        colors['muted'] = mix(foreground, background, .22)
        colors.setdefault('metric', accent)
        for role in ('muted', 'metric'):
            if min(contrast(colors[role], colors[key]) for key in ('background', 'surface')) < 4.5:
                colors[role] = mix(colors[role], foreground, .55)
                if min(contrast(colors[role], colors[key]) for key in ('background', 'surface')) < 4.5:
                    colors[role] = foreground
        colors.setdefault('selection', accent)
        selected = colors['selection']
        if contrast(colors.get('selection_foreground', foreground), selected) < 4.5:
            colors['selection_foreground'] = max(('#000000', '#ffffff'), key=lambda color: contrast(selected, color))
        else:
            colors.setdefault('selection_foreground', foreground)
        return colors
