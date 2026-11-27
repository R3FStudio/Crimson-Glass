#!/usr/bin/python3
"""Apply the curated Debian 13 GNOME profile."""
import argparse
import filecmp
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime
from urllib.parse import quote

import full_profile

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = {
    'gnome-shell': 'shell',
    'desktop-interface': 'desktop/interface',
    'desktop-background': 'desktop/background',
    'desktop-screensaver': 'desktop/screensaver',
    'desktop-wm-preferences': 'desktop/wm/preferences',
    'mutter': 'mutter',
    'nautilus': 'nautilus',
    'settings-daemon-plugins-power': 'settings-daemon/plugins/power',
}
PACKAGES = (
    'adwaita-icon-theme', 'bluez', 'curl', 'dconf-cli', 'flatpak', 'fonts-noto-core',
    'gcc', 'gir1.2-gtop-2.0', 'gir1.2-gtk-4.0', 'gir1.2-adw-1',
    'glib2.0-bin', 'goverlay', 'libadwaita-1-dev', 'libhidapi-hidraw0',
    'mangohud', 'mesa-vulkan-drivers', 'pkg-config', 'python3-gi',
    'python3-hid', 'python3-nautilus', 'vulkan-tools', 'wine', 'zenity',
)
MIME_TYPES = (
    'application/x-msdownload', 'application/vnd.microsoft.portable-executable',
    'application/x-msi',
)
BOOT_FILES = (
    'boot/grub/readable-32.pf2', 'etc/default/grub.d/96-crimson-os-prober.cfg',
    'etc/default/grub.d/97-eac-linux.cfg', 'etc/default/grub.d/98-readable-menu.cfg',
    'etc/default/grub.d/99-wait-for-choice.cfg',
)
ZRAM_CONFIG = 'etc/systemd/zram-generator.conf.d/50-crimson-glass.conf'
MEMORY_SYSCTL = 'etc/sysctl.d/60-crimson-memory.conf'

DEVICE_FILES = (
    'etc/udev/rules.d/71-hyperx-haste2.rules', 'etc/modprobe.d/trcc-lcd.conf',
    'etc/modules-load.d/trcc-sg.conf', 'etc/modules-load.d/trcc-rapl.conf',
)

def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)

def display_state():
    from gi.repository import Gio
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        reply = bus.call_sync('org.gnome.Mutter.DisplayConfig', '/org/gnome/Mutter/DisplayConfig',
                              'org.gnome.Mutter.DisplayConfig', 'GetCurrentState',
                              None, None, Gio.DBusCallFlags.NONE, 2500, None)
        return reply.unpack()
    except Exception as error:
        print(f'GNOME display state is unavailable: {error}', file=sys.stderr)
        return None


def primary_monitor():
    state = display_state()
    if state is not None:
        for index, monitor in enumerate(state[2]):
            if monitor[4]:
                return str(index)
    return '0'

def settings_text(name, home, monitor='0'):
    content = (ROOT / 'config' / f'{name}.ini').read_text()
    if name == 'gnome-shell':
        content = content.replace('@PRIMARY_MONITOR@', monitor)
    return content.replace('@HOME_URI_PATH@', quote(str(home)))

def put(source, target, home, backup):
    relative = target.relative_to(home)
    parent = target.parent
    if not parent.resolve().is_relative_to(home):
        raise RuntimeError(f'Install path points outside home: {parent}')
    if source.is_symlink() and target.is_symlink() and target.readlink() == source.readlink():
        return
    substitute = not source.is_symlink() and (source.suffix == '.desktop' or source.name == 'trcc.json')
    if substitute:
        content = source.read_text().replace('@HOME@', str(home))
        if target.is_file() and not target.is_symlink() and target.read_text() == content:
            return
    elif target.is_file() and not target.is_symlink() and not source.is_symlink() and filecmp.cmp(source, target, shallow=False):
        return
    if target.is_symlink() or target.exists():
        saved = backup / 'home' / relative
        saved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, saved, follow_symlinks=False)
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.crimson-', dir=parent) as tmp:
        pending = Path(tmp) / target.name
        if source.is_symlink():
            pending.symlink_to(source.readlink())
        elif substitute:
            pending.write_text(content)
            shutil.copymode(source, pending)
        else:
            shutil.copy2(source, pending)
        pending.replace(target)

def apply_home(home, backup):
    source = ROOT / 'payload/home'
    for path in sorted(source.rglob('*')):
        if path.is_symlink() or path.is_file():
            put(path, home / path.relative_to(source), home, backup)
    umu = ROOT / 'local/umu-run'
    if umu.is_file():
        put(umu, home / '.local/bin/umu-run', home, backup)
    # Shared NTFS mounts can mask executable bits on the source files.
    for name in ('gnome-glass-theme', 'gnome-settings-with-fade', 'rice-task-manager',
                 'windows-app-loader', 'umu-run'):
        launcher = home / '.local/bin' / name
        if launcher.is_file() and not launcher.is_symlink():
            launcher.chmod(launcher.stat().st_mode | 0o100)
    archive = ROOT / 'local/tela-circle-red.tar.gz'
    if archive.exists():
        with tempfile.TemporaryDirectory(prefix='crimson-icons-') as tmp:
            icon_files = Path(tmp)
            with tarfile.open(archive, 'r:gz') as bundle:
                bundle.extractall(icon_files, filter='data')
            for path in sorted(icon_files.rglob('*')):
                if path.is_symlink() or path.is_file():
                    put(path, home / '.local/share/icons' / path.relative_to(icon_files), home, backup)
    for schema in (home / '.local/share/gnome-shell/extensions').glob('*/schemas'):
        if (source / schema.relative_to(home)).is_dir():
            run('glib-compile-schemas', '--strict', str(schema))
    library = home / '.local/lib/gnome-settings-dock-toggle'
    if shutil.which('pkg-config') and shutil.which('cc'):
        flags = subprocess.run(['pkg-config', '--cflags', '--libs', 'libadwaita-1'],
                               capture_output=True, text=True)
        if flags.returncode == 0:
            run('cc', '-fPIC', '-shared', '-o', str(library / 'dock-toggle.so'),
                str(library / 'dock-toggle.c'), *flags.stdout.split(), '-ldl')
            return
    print('Settings sidebar installed. Use --packages to build the optional Appearance dock toggle.')

def restore_machine(home, backup, usb):
    local = ROOT / 'local/machine'
    monitors = local / '.config/monitors.xml'
    luminance = local / 'output-luminance'
    display = full_profile.hdr_display_profile(
        monitors, display_state(), luminance.read_text() if luminance.is_file() else '')
    if display:
        from gi.repository import GLib
        xml, values = display
        with tempfile.TemporaryDirectory(prefix='crimson-display-') as directory:
            config = Path(directory) / 'monitors.xml'
            config.write_text(xml)
            put(config, home / '.config/monitors.xml', home, backup)
        if values:
            key = '/org/gnome/mutter/output-luminance'
            previous = subprocess.check_output(['dconf', 'read', key], text=True, check=False)
            if previous:
                backup.mkdir(parents=True, exist_ok=True)
                (backup / 'output-luminance').write_text(previous)
                original = GLib.Variant.parse(None, previous.strip(), None, None)
                changed = {tuple(v[:5]) for v in values}
                values = [v for v in original.unpack() if tuple(v[:5]) not in changed] + values
            run('dconf', 'write', key, GLib.Variant('a(ssssud)', values).print_(True))
    if full_profile.matching_board(ROOT):
        overlay = '.config/MangoHud/MangoHud.conf'
        if (local / overlay).is_file():
            put(local / overlay, home / overlay, home, backup)
        rgb = '.local/share/hypercolor'
        for relative in ('scenes.json', 'layouts.json', 'library.json', 'attachments/asus-case-fans-48.toml'):
            source = local / rgb / relative
            if source.is_file():
                put(source, home / rgb / relative, home, backup)
    if '87ad:70db' in usb:
        settings = local / '.trcc/trcc.json'
        if settings.is_file():
            put(settings, home / '.trcc/trcc.json', home, backup)
        for path in (local / '.trcc-user/data').rglob('*'):
            if path.is_file() and not path.is_symlink():
                relative = path.relative_to(local)
                put(path, home / relative, home, backup)


def apply_settings(home, backup):
    monitor = primary_monitor()
    for name, subtree in SETTINGS.items():
        key = f'/org/gnome/{subtree}/'
        old = subprocess.check_output(['dconf', 'dump', key], text=True)
        backup.joinpath('dconf').mkdir(parents=True, exist_ok=True)
        (backup / 'dconf' / f'{name}.ini').write_text(old)
        profile = settings_text(name, home, monitor)
        if name == 'desktop-interface' and not (home / '.local/share/icons/Tela-circle-red-dark/index.theme').exists():
            profile = profile.replace("icon-theme='Tela-circle-red-dark'", "icon-theme='Adwaita'")
        run('dconf', 'load', key, input=profile, text=True)
    mime_config = home / ".config/mimeapps.list"
    if mime_config.is_file():
        (backup / "home/.config").mkdir(parents=True, exist_ok=True)
        shutil.copy2(mime_config, backup / "home/.config/mimeapps.list")
    for mime in MIME_TYPES:
        run('xdg-mime', 'default', 'org.local.WindowsAppLoader.desktop', mime)
    run('systemctl', '--user', 'daemon-reload')
    run('systemctl', '--user', 'enable', '--now', 'gnome-glass-theme.service')
    run('systemctl', '--user', 'restart', 'gnome-glass-theme.service')

def install_system(files, backup):
    target_backup = Path('/var/backups/crimson-glass') / backup.name
    for relative in files:
        dest = Path('/') / relative
        source = ROOT / 'payload/system' / relative
        if dest.is_file() and filecmp.cmp(source, dest, shallow=False):
            continue
        if dest.exists():
            saved = target_backup / relative
            run('sudo', 'install', '-D', '-m', '0644', str(dest), str(saved))
        run('sudo', 'install', '-D', '-m', '0644', str(source), str(dest))

def apply_memory_profile(backup):
    zswap = Path('/sys/module/zswap/parameters/enabled')
    if zswap.is_file() and zswap.read_text().strip().upper() in {'Y', '1'}:
        print('Memory profile skipped because zswap is enabled.')
        return

    config = Path('/') / ZRAM_CONFIG
    directory = config.parent
    other_configs = [directory.parent / 'zram-generator.conf', *directory.glob('*.conf')]
    if (full_profile.installed('zram-tools') or
            (not config.is_file() and Path('/sys/block/zram0').is_dir()) or
            any(path != config and path.is_file() and
                re.search(r'^\s*\[zram0\]\s*$', path.read_text(), re.MULTILINE)
                for path in other_configs)):
        print('Memory profile skipped because an existing zram setup manages zram0.')
        return

    install_system((ZRAM_CONFIG,), backup)
    if not full_profile.installed('systemd-zram-generator'):
        run('sudo', 'apt-get', 'install', 'systemd-zram-generator')
    run('sudo', 'systemctl', 'daemon-reload')
    run('sudo', 'systemctl', 'start', 'dev-zram0.swap')
    install_system((MEMORY_SYSCTL,), backup)
    run('sudo', 'sysctl', '-p', '/' + MEMORY_SYSCTL)


def apply_data_volume(uuid, backup):
    device = Path('/dev/disk/by-uuid') / uuid
    probe = subprocess.check_output(['lsblk', '-ndo', 'FSTYPE', str(device)], text=True).strip()
    if probe != 'ntfs':
        raise RuntimeError(f'{device} must identify an NTFS volume')
    dest = Path('/etc/udisks2/mount_options.conf')
    old = dest.read_text() if dest.exists() else ''
    section = f'[{device}]'
    if section in old.splitlines():
        print(f'{section} already has mount options. Leaving the existing entry in place.')
        return
    with tempfile.TemporaryDirectory(prefix='crimson-ntfs-') as tmp:
        config = Path(tmp) / 'mount_options.conf'
        config.write_text(old.rstrip() + '\n\n' + section +
                          '\nntfs_drivers=ntfs\nntfs:ntfs_defaults=ro,uid=$UID,gid=$GID,windows_names\n')
        if dest.exists():
            saved = Path('/var/backups/crimson-glass') / backup.name / dest.relative_to('/')
            run('sudo', 'install', '-D', '-m', '0644', str(dest), str(saved))
        run('sudo', 'install', '-D', '-m', '0644', str(config), str(dest))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--all', action='store_true', help='restore the full profile and install feature dependencies')
    parser.add_argument('--packages', action='store_true', help='install Debian package dependencies')
    parser.add_argument('--apps', action='store_true', help='install the Bitwarden and Parsec Flatpaks')
    parser.add_argument('--memory', action='store_true', help='enable compressed swap and memory tuning')
    parser.add_argument('--hdr', action='store_true', help='install Mesa Vulkan from Debian backports')
    parser.add_argument('--deb', type=Path, action='append', default=[], help='install a local vendor .deb; repeat as needed')
    parser.add_argument('--boot', action='store_true', help='apply GRUB menu and kernel settings')
    parser.add_argument('--devices', action='store_true', help='install HyperX and Thermalright hardware rules')
    parser.add_argument('--data-uuid', help='add read-only fallback for the specified shared NTFS volume')
    parser.add_argument('--dry-run', action='store_true', help='show the actions without writing')
    parser.add_argument('--stage', type=Path, help='copy only user files into a staging directory')
    args = parser.parse_args()
    if os.geteuid() == 0:
        parser.error('Run as your desktop user. The installer invokes sudo for system changes.')
    if args.data_uuid and not re.fullmatch(r'[A-Za-z0-9-]{4,64}', args.data_uuid):
        parser.error('Invalid filesystem UUID')
    if args.all:
        args.packages = args.hdr = args.devices = args.memory = True
        args.boot = full_profile.boot_available()
    optional = {key: getattr(args, key) for key in ('all', 'packages', 'apps', 'boot', 'hdr', 'deb', 'devices', 'memory', 'data_uuid')}
    if args.stage and any(optional.values()):
        parser.error('--stage only supports user files')
    if args.dry_run:
        print('Install Crimson Glass GNOME theme, extensions, cursor, wallpaper, app helpers and settings.')
        if args.all:
            print('Includes hardware-matched presets, shared NTFS detection, Scarlett capture, and required vendor tools.')
        print('Enabled options:', ', '.join(k for k,v in optional.items() if v) or 'desktop only')
        return
    home = (args.stage or Path.home()).resolve()
    backup = home / '.local/state/crimson-glass/backups' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    if not args.stage and not os.environ.get('DBUS_SESSION_BUS_ADDRESS'):
        parser.error('Open a terminal inside the GNOME session before applying settings')
    if args.boot and (not Path('/usr/sbin/update-grub').is_file() or not Path('/boot/grub/grub.cfg').is_file()):
        parser.error('--boot requires an existing GRUB installation')
    if any(path.suffix != '.deb' or not path.is_file() for path in args.deb):
        parser.error('--deb requires a path to an existing .deb file')
    if args.all:
        release = Path('/etc/os-release').read_text()
        if 'ID=debian' not in release.splitlines() or 'VERSION_ID="13"' not in release.splitlines():
            parser.error('The full profile requires Debian 13.')
    usb = full_profile.usb_ids() if args.all else set()
    if args.packages:
        if args.all and 'i386' not in subprocess.check_output(
                ['dpkg', '--print-foreign-architectures'], text=True).splitlines():
            run('sudo', 'dpkg', '--add-architecture', 'i386')
        run('sudo', 'apt-get', 'update')
        extra = ('gnome-terminal', 'ntfs-3g', 'os-prober', 'pipewire-pulse',
                 'pulseaudio-utils', 'wine32:i386', 'wireplumber') if args.all else ()
        run('sudo', 'apt-get', 'install', *PACKAGES, *extra)
    if args.hdr:
        apt_source = 'etc/apt/sources.list.d/debian-trixie-backports-hdr.sources'
        if not Path('/' + apt_source).exists():
            install_system((apt_source,), backup)
        run('sudo', 'apt-get', 'update')
        driver = ['mesa-vulkan-drivers']
        if 'i386' in subprocess.check_output(['dpkg', '--print-foreign-architectures'], text=True).splitlines():
            driver.append('mesa-vulkan-drivers:i386')
        run('sudo', 'apt-get', 'install', '-t', 'trixie-backports', *driver)
    if args.deb:
        run('sudo', 'apt-get', 'install', *(str(path.resolve()) for path in args.deb))
    if args.apps:
        run('flatpak', 'remote-add', '--user', '--if-not-exists', 'flathub',
            'https://flathub.org/repo/flathub.flatpakrepo')
        run('flatpak', 'install', '--user', 'flathub', 'com.bitwarden.desktop', 'com.parsecgaming.parsec')
    if args.all:
        with tempfile.TemporaryDirectory(prefix='crimson-debs-') as directory:
            packages = full_profile.vendor_packages(ROOT, usb, Path(directory))
            if packages:
                # Let apt's sandbox account traverse the download directory.
                Path(directory).chmod(0o755)
                run('sudo', 'apt-get', 'install', *(str(path) for path in packages))
    apply_home(home, backup)
    if args.stage:
        print(f'Staged files in {home}')
        return
    apply_settings(home, backup)
    if args.boot:
        install_system(BOOT_FILES, backup)
        grub = Path('/boot/grub/grub.cfg')
        saved = Path('/var/backups/crimson-glass') / backup.name / 'boot/grub/grub.cfg'
        run('sudo', 'install', '-D', '-m', '0600', str(grub), str(saved))
        with tempfile.TemporaryDirectory(prefix='crimson-grub-') as directory:
            candidate = Path(directory) / 'grub.cfg'
            run('sudo', 'grub-mkconfig', '-o', str(candidate))
            run('sudo', 'grub-script-check', str(candidate))
            new = grub.with_name('grub.cfg.crimson-new')
            run('sudo', 'install', '-m', '0600', str(candidate), str(new))
            run('sudo', 'mv', '-T', str(new), str(grub))
    if args.all:
        restore_machine(home, backup, usb)
        run('systemctl', '--user', 'enable', '--now', 'crimson-audio.service')
        if full_profile.installed('lact'):
            run('sudo', 'systemctl', 'enable', '--now', 'lactd.service')
    if args.memory:
        apply_memory_profile(backup)
    if args.devices:
        install_system(DEVICE_FILES, backup)
        run('sudo', 'udevadm', 'control', '--reload-rules')
        if (not args.all or '87ad:70db' in usb) and (shutil.which('trcc') or Path('/usr/local/bin/trcc').is_file()):
            run('systemctl', '--user', 'enable', 'thermalright-lcd.service')
    data_uuid = args.data_uuid or (full_profile.data_volume() if args.all else None)
    if data_uuid:
        apply_data_volume(data_uuid, backup)
        if args.all:
            full_profile.set_data_automount(data_uuid, backup)
    if args.all:
        print('Sign out and back in to load Shell, Files, and device startup settings. Reboot for GRUB and driver changes.')
    print(f'Previous user settings and overwritten files: {backup}')

if __name__ == '__main__':
    main()
