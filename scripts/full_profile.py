"""Hardware discovery and dependency installation for Crimson Glass."""
import hashlib
import json
import os
import tempfile
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET


def checked(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def installed(package):
    result = subprocess.run(['dpkg-query', '-W', '-f=${db:Status-Status}', package],
                            text=True, capture_output=True)
    return result.returncode == 0 and result.stdout == 'installed'


def vendor_packages(root, connected_usb, temporary):
    architecture = subprocess.check_output(['dpkg', '--print-architecture'], text=True).strip()
    if architecture != 'amd64':
        raise RuntimeError('The full profile targets Debian 13 on amd64.')
    names = {'lact', 'hypercolor'}
    if (Path.home() / ".local/bin/hypercolor-app").is_file() or shutil.which("hypercolor-app"):
        names.remove("hypercolor")
    # Install both Debian packages together when a local umu launcher is unavailable.
    if not (root / 'local/umu-run').is_file() and not shutil.which('umu-run'):
        names.update(('umu-launcher', 'python3-umu-launcher'))
    if connected_usb & {'87ad:70db', '87cd:70db', '0402:3922'}:
        names.add('trcc-linux')
    files = []
    for entry in json.loads((root / 'config/vendor-packages.json').read_text()):
        if entry['package'] not in names or installed(entry['package']):
            continue
        local = root / 'local' / entry['file']
        if entry['package'] == 'trcc-linux' and not local.is_file():
            local = root / 'local/trcc-linux.deb'
        artifact = local if local.is_file() else temporary / entry['file']
        if not artifact.is_file():
            checked('curl', '--fail', '--location', '--silent', '--show-error', '--retry', '2',
                    '--proto', '=https', '--proto-redir', '=https', '--output',
                    str(artifact), entry['url'])
        with artifact.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if digest != entry['sha256']:
            raise RuntimeError(f'Unexpected checksum for {artifact.name}')
        if artifact == local:
            cached = temporary / entry['file']
            shutil.copyfile(artifact, cached)
            artifact = cached
        files.append(artifact)
    terlox = root / 'local/terlox.deb'
    if not installed('terlox'):
        if terlox.is_file():
            package = subprocess.check_output(['dpkg-deb', '-f', str(terlox), 'Package'], text=True).strip()
            if package != 'terlox':
                raise RuntimeError(f'Expected a Terlox package in {terlox}')
            cached = temporary / 'terlox.deb'
            shutil.copyfile(terlox, cached)
            files.append(cached)
        else:
            print('Files will use GNOME Terminal. The local Terlox package is unavailable.')
    return files


def usb_ids():
    ids = set()
    for vendor in Path('/sys/bus/usb/devices').glob('*/idVendor'):
        product = vendor.with_name('idProduct')
        try:
            ids.add(f'{vendor.read_text().strip()}:{product.read_text().strip()}')
        except OSError:
            continue
    return ids


def data_volume():
    state = json.loads(subprocess.check_output(
        ['lsblk', '--json', '--list', '--output', 'UUID,LABEL,FSTYPE'], text=True))
    candidates = [item['uuid'] for item in state['blockdevices']
                  if item['label'] == 'Data' and item['fstype'] == 'ntfs' and item['uuid']]
    if len(candidates) == 1:
        return candidates[0]
    print('Shared drive setup skipped because a unique NTFS volume labeled Data was not found.')
    return None


def hdr_display_profile(file, display_state, luminance):
    if not file.is_file() or display_state is None:
        return None
    from gi.repository import GLib
    root = ET.parse(file).getroot()
    connected = {tuple(monitor[0]): monitor[2] for monitor in display_state[1]}
    panel_keys = ('connector', 'vendor', 'product', 'serial')

    def spec(monitor):
        return tuple(monitor.findtext(f'monitorspec/{key}', '') for key in panel_keys)

    hdr_modes = {}
    for monitor in root.findall('.//logicalmonitor/monitor'):
        if monitor.findtext('colormode') == 'bt2100':
            hdr_modes[spec(monitor)[1:]] = 'bt2100'
    destinations = {}
    for config in root.findall('configuration'):
        monitors = config.findall('.//logicalmonitor/monitor')
        if {spec(monitor) for monitor in monitors} != connected.keys():
            continue
        for monitor in monitors:
            identity = spec(monitor)
            panel = identity[1:]
            if (panel in hdr_modes and 1 in connected[identity].get('supported-color-modes', [])
                    and sum(other[1:] == panel for other in connected) == 1):
                mode = monitor.find('colormode')
                if mode is None:
                    mode = ET.SubElement(monitor, 'colormode')
                mode.text = hdr_modes[panel]
                destinations[panel] = identity[0]
        if destinations:
            break
    if not destinations:
        return None
    values = []
    if luminance:
        saved = GLib.Variant.parse(None, luminance.strip(), None, None)
        for _, vendor, product, serial, mode, brightness in saved.unpack():
            identity = (vendor, product, serial)
            if identity in destinations:
                values.append((destinations[identity], *identity, mode, brightness))
    ET.indent(root, space='  ')
    return ET.tostring(root, encoding='unicode') + '\n', values


def matching_board(root):
    saved = root / 'local/board-id'
    if not saved.is_file():
        return False
    board = Path('/sys/class/dmi/id')
    try:
        identity = b''.join((board / key).read_bytes() for key in ('board_vendor', 'board_name'))
    except OSError:
        return False
    return hashlib.sha256(identity).hexdigest() == saved.read_text().strip()


def boot_available():
    return Path('/usr/sbin/update-grub').is_file() and Path('/boot/grub/grub.cfg').is_file()


def set_data_automount(uuid, backup):
    fstab = Path('/etc/fstab')
    text = fstab.read_text()
    source = f'UUID={uuid}'
    for line in text.splitlines():
        entries = line.split('#', 1)[0].split()
        if len(entries) < 2:
            continue
        if entries[0] in {source, f'/dev/disk/by-uuid/{uuid}'}:
            return
        if entries[1] == '/mnt/data':
            print('Shared drive automount skipped because /mnt/data already belongs to another entry.')
            return
    target = Path('/mnt/data')
    if target.is_symlink() or (target.is_dir() and any(target.iterdir())):
        print('Shared drive automount skipped because /mnt/data already contains files.')
        return
    options = (f'rw,norecover,uid={os.getuid()},gid={os.getgid()},'
               'fmask=0177,dmask=0077,windows_names,nosuid,nodev,nofail,x-systemd.automount')
    with tempfile.TemporaryDirectory(prefix='crimson-fstab-') as directory:
        candidate = Path(directory) / 'fstab'
        candidate.write_text(text.rstrip() + f'\n{source} /mnt/data ntfs-3g {options} 0 0\n')
        saved = Path('/var/backups/crimson-glass') / backup.name / 'etc/fstab'
        checked('sudo', 'install', '-D', '-m', '0644', str(fstab), str(saved))
        checked('sudo', 'mkdir', '-p', '/mnt/data')
        checked('sudo', 'install', '-m', '0644', str(candidate), str(fstab))
        checked('sudo', 'systemctl', 'daemon-reload')
