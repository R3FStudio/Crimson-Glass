"""Read-only Linux hardware telemetry; unavailable sensors stay unavailable."""
import collections, json, os, shutil, socket, subprocess, time
from pathlib import Path

def read(path,default=''):
    try: return Path(path).read_text().strip()
    except (OSError,UnicodeError): return default

def number(path,scale=1):
    try: return float(read(path))/scale
    except ValueError: return None

def duration(seconds):
    seconds=int(seconds); days,seconds=divmod(seconds,86400); hours,seconds=divmod(seconds,3600); minutes,seconds=divmod(seconds,60)
    return (f'{days}d ' if days else '')+f'{hours}h {minutes}m'

class HardwareSampler:
    def __init__(self):
        self.last=time.monotonic(); self.net_last=None; self.disk_last={}; self.net_rx=0.; self.net_tx=0.; self.disk_read=0.; self.disk_write=0.; self.disk_busy=0.; self.disk_name='No physical disk found'; self.net_name='No active interface'; self.gpu={}; self.gpu_last=0
        self.histories={k:collections.deque(maxlen=60) for k in ('cpu','memory','disk','rx','tx','gpu')}
        self.cpu_name=next((line.split(':',1)[1].strip() for line in read('/proc/cpuinfo').splitlines() if line.startswith('model name')),os.uname().machine)
        self.addresses={}
        try:
            result=subprocess.run(['ip','-j','address','show','up'],capture_output=True,text=True,timeout=2)
            for interface in json.loads(result.stdout):
                self.addresses[interface['ifname']]=[a['local'] for a in interface.get('addr_info',[]) if a.get('scope')=='global']
        except (OSError,ValueError,subprocess.SubprocessError): pass
        self.nvidia=shutil.which('nvidia-smi')
    def sample(self,sampler):
        now=time.monotonic(); dt=max(.01,now-self.last); self.last=now
        self.mem=dict((k,int(v.split()[0])*1024) for k,v in (line.split(':',1) for line in read('/proc/meminfo').splitlines()))
        self.uptime=float(read('/proc/uptime','0').split()[0]); self.hostname=socket.gethostname()
        frequencies=[float(line.split(':')[1]) for line in read('/proc/cpuinfo').splitlines() if line.startswith('cpu MHz')]
        self.frequency=sum(frequencies)/len(frequencies)/1000 if frequencies else 0
        nets=[]
        for line in read('/proc/net/dev').splitlines()[2:]:
            name,fields=line.split(':',1); name=name.strip(); fields=fields.split()
            if name!='lo' and read(f'/sys/class/net/{name}/operstate') in ('up','unknown'): nets.append((name,int(fields[0]),int(fields[8])))
        current={n:(rx,tx) for n,rx,tx in nets}; rates=[]
        if self.net_last is not None:
            for name,(rx,tx) in current.items():
                old=self.net_last.get(name,(rx,tx)); rates.append((name,max(0,rx-old[0])/dt,max(0,tx-old[1])/dt))
        self.net_last=current; self.net_rx=sum(r[1] for r in rates); self.net_tx=sum(r[2] for r in rates)
        if nets: self.net_name=max(nets,key=lambda r:r[1]+r[2])[0]
        self.link_speed=number(f'/sys/class/net/{self.net_name}/speed')
        disk_rates=[]; fresh={}
        for line in read('/proc/diskstats').splitlines():
            fields=line.split(); name=fields[2]; base=Path('/sys/class/block')/name
            if len(fields)<14 or (base/'partition').exists() or name.startswith(('loop','ram','dm-','zram','sr','md')): continue
            sectors_read,sectors_written,busy=int(fields[5]),int(fields[9]),int(fields[12]); fresh[name]=(sectors_read,sectors_written,busy)
            old=self.disk_last.get(name,(sectors_read,sectors_written,busy)); disk_rates.append((name,max(0,sectors_read-old[0])*512/dt,max(0,sectors_written-old[1])*512/dt,min(100,max(0,busy-old[2])/dt/10)))
        self.disk_last=fresh
        if disk_rates:
            active=max(disk_rates,key=lambda r:r[1]+r[2]); self.disk_name=active[0]; self.disk_read=active[1]; self.disk_write=active[2]; self.disk_busy=active[3]
        if now-self.gpu_last>=4:
            self.gpu_last=now; self.gpu=self.read_gpu()
        for key,value in [('cpu',sampler.cpu),('memory',sampler.memory/sampler.total*100),('disk',self.disk_busy),('rx',self.net_rx),('tx',self.net_tx),('gpu',self.gpu.get('usage',0) or 0)]: self.histories[key].append(value)
    def read_gpu(self):
        if self.nvidia:
            try:
                result=subprocess.run([self.nvidia,'--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=1)
                values=result.stdout.splitlines()[0].split(', ')
                def num(i):
                    try: return float(values[i])
                    except ValueError: return None
                return dict(name=values[0],usage=num(1),used=num(2),total=num(3),temperature=num(4),power=num(5))
            except (OSError,IndexError,subprocess.SubprocessError): pass
        for card in sorted(Path('/sys/class/drm').glob('card[0-9]*/device')):
            busy=number(card/'gpu_busy_percent')
            if busy is None: continue
            used=number(card/'mem_info_vram_used',1024*1024); total=number(card/'mem_info_vram_total',1024*1024)
            temps=list(card.glob('hwmon/hwmon*/temp1_input')); temperature=number(temps[0],1000) if temps else None
            return dict(name=read(card/'product_name') or 'GPU · '+card.parent.name,usage=busy,used=used,total=total,temperature=temperature,power=None)
        return dict(name='No supported GPU telemetry',usage=None,used=None,total=None,temperature=None,power=None)
