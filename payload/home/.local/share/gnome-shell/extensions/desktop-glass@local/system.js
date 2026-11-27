import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

const decoder = new TextDecoder();

function read(path) {
    try {
        const [, bytes] = Gio.File.new_for_path(path).load_contents(null);
        return decoder.decode(bytes).trim();
    } catch {
        return '';
    }
}

function fields(text, separator = '=') {
    return Object.fromEntries(text.split('\n').filter(line => line.includes(separator))
        .map(line => {
            const index = line.indexOf(separator);
            return [line.slice(0, index).trim(), line.slice(index + 1).trim()];
        }));
}

function directories(path) {
    try {
        return Gio.File.new_for_path(path).enumerate_children(
            'standard::name', Gio.FileQueryInfoFlags.NONE, null);
    } catch {
        return null;
    }
}

function names(path, pattern) {
    const enumerator = directories(path);
    if (!enumerator)
        return [];
    const result = [];
    try {
        for (let entry; (entry = enumerator.next_file(null));) {
            const name = entry.get_name();
            if (pattern.test(name))
                result.push(name);
        }
    } finally {
        enumerator.close(null);
    }
    return result.sort();
}

export class SystemStats {
    constructor() {
        this.cpu = read('/proc/cpuinfo').match(/^model name\s*:\s*(.+)$/m)?.[1]
            .replace(/\bProcessor\b|\b\d+-Core\b/g, '').replace(/\s+/g, ' ').trim() ?? 'Processor';
        const gpuDevices = names('/sys/class/drm', /^card\d+$/).map(name => {
            const path = `/sys/class/drm/${name}/device`;
            return {path, vram: Number(read(`${path}/mem_info_vram_total`))};
        });
        const gpu = gpuDevices.sort((a, b) => b.vram - a.vram)[0];
        this.gpuPath = gpu?.path;
        this.vram = gpu?.vram ? `${Math.round(gpu.vram / 1024 ** 3)} GB` : '';
        this.gpu = 'Graphics';
        const pci = gpu && fields(read(`${gpu.path}/uevent`)).PCI_SLOT_NAME;
        if (pci)
            this._readGpuName(pci);

        const nvme = names('/sys/class/nvme', /^nvme\d+$/)[0];
        this.storage = nvme ? read(`/sys/class/nvme/${nvme}/model`).replace(/\s+NVMe\b/i, '') : 'Storage';
        this.os = fields(read('/etc/os-release')).PRETTY_NAME?.replace(/^"|"$/g, '')
            .replace(' GNU/Linux', '').replace(/\s*\(.+\)/, '') ?? 'Linux';
        this.memory = '';
        this.previousCpu = null;
        this.metrics = [null, null, null];
    }

    _readGpuName(pci) {
        try {
            const process = Gio.Subprocess.new(['lspci', '-s', pci],
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE);
            process.communicate_utf8_async(null, null, (_process, result) => {
                try {
                    const [, output] = process.communicate_utf8_finish(result);
                    const name = output.match(/\[((?:RX|RTX|GTX|Arc) [^\]]+)\]/i)?.[1]
                        ?? output.split(' controller: ')[1]?.replace(/\s*\(rev.*\)/, '').trim();
                    if (name)
                        this.gpu = name;
                } catch {
                    // The monitor still works if the PCI database is unavailable.
                }
            });
        } catch {
            // Keep the generic graphics label.
        }
    }

    sample() {
        const cpu = read('/proc/stat').match(/^cpu\s+(.+)$/m)?.[1].split(/\s+/).slice(0, 8).map(Number);
        let cpuUsage = this.metrics[0];
        if (cpu?.length >= 5) {
            const total = cpu.reduce((sum, value) => sum + value, 0);
            const idle = cpu[3] + cpu[4];
            if (this.previousCpu && total > this.previousCpu.total)
                cpuUsage = 100 * (1 - (idle - this.previousCpu.idle) / (total - this.previousCpu.total));
            this.previousCpu = {total, idle};
        }

        const mem = fields(read('/proc/meminfo'), ':');
        const total = parseInt(mem.MemTotal, 10);
        const available = parseInt(mem.MemAvailable, 10);
        const memoryUsage = total && Number.isFinite(available) ? 100 * (1 - available / total) : null;
        if (total)
            this.memory = `${(total / 1024 ** 2).toFixed(1)} GiB`;

        const gpuUsage = this.gpuPath ? read(`${this.gpuPath}/gpu_busy_percent`) : '';
        this.metrics = [cpuUsage, memoryUsage, gpuUsage ? Number(gpuUsage) : null]
            .map(value => Number.isFinite(value) ? Math.round(Math.min(100, Math.max(0, value))) : null);
    }
}
