"""Dashboard and management views for Rice Task Manager."""
import configparser, json, os, platform, socket, subprocess, time
from pathlib import Path
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk, Gio, GLib
from system_metrics import read, duration


def label(text,style=None):
    widget=Gtk.Label(label=str(text),xalign=0)
    if style: widget.add_css_class(style)
    widget.set_ellipsize(3)
    return widget

def box(vertical=True,spacing=8):
    return Gtk.Box(orientation=Gtk.Orientation.VERTICAL if vertical else Gtk.Orientation.HORIZONTAL,spacing=spacing)

def padded(widget,amount=20):
    for edge in ('top','bottom','start','end'): getattr(widget,'set_margin_'+edge)(amount)
    return widget


def read_appearance(path):
    try:
        values = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return values if isinstance(values, dict) else {}


class DashboardViews:
    def scroll_content(self,widget):
        previous=getattr(self,'page_scroll',None); value=previous.get_vadjustment().get_value() if previous is not None and getattr(self,'scroll_page',None)==self.page else 0
        scroll=Gtk.ScrolledWindow(); scroll.set_vexpand(True); scroll.set_child(widget); self.body.append(scroll); self.page_scroll=scroll; self.scroll_page=self.page
        if value: GLib.idle_add(lambda: (scroll.get_vadjustment().set_value(value),False)[1])
    def chart(self,keys,percent=True):
        area=Gtk.DrawingArea(); area.set_content_height(46); area.set_hexpand(True)
        self.charts.append(area)
        def draw(_,cr,w,h):
            color=self.colors['accent']; rgb=tuple(int(color[i:i+2],16)/255 for i in (1,3,5))
            cr.set_source_rgba(*rgb,.12); cr.set_line_width(1)
            for y in (1,h/2,h-1): cr.move_to(0,y); cr.line_to(w,y)
            cr.stroke()
            points=[list(self.hardware.histories[k])[-self.graph_samples:] for k in keys]
            scale=100 if percent else max(1024,max((max(p) for p in points),default=1)*1.1)
            for index,values in enumerate(points):
                cr.set_source_rgba(*rgb,1 if index==0 else .45); cr.set_line_width(1.6)
                for i,value in enumerate(values):
                    x=(self.graph_samples-len(values)+i)*w/max(1,self.graph_samples-1); y=h-min(scale,value)*h/scale
                    (cr.move_to if i==0 else cr.line_to)(x,y)
                cr.stroke()
                if index==0 and values:
                    cr.move_to((self.graph_samples-len(values))*w/max(1,self.graph_samples-1),h)
                    for i,value in enumerate(values): cr.line_to((self.graph_samples-len(values)+i)*w/max(1,self.graph_samples-1),h-min(scale,value)*h/scale)
                    cr.line_to(w,h); cr.close_path(); cr.set_source_rgba(*rgb,.12); cr.fill()
        area.set_draw_func(draw); return area
    def render_performance(self):
        s=self.sampler; h=self.hardware
        self.charts.clear()
        grid=Gtk.Grid(column_spacing=12,row_spacing=10,column_homogeneous=True,row_homogeneous=True); padded(grid,14)
        def card(title,value,subtitle,keys,detail,col,row,percent=True):
            content=box(spacing=4); content.add_css_class('card'); content.append(label(title,'card-title')); content.append(label(value,'big')); content.append(label(subtitle,'muted'))
            content.append(self.chart(keys,percent)); content.append(label(detail,'muted')); content.set_hexpand(True); grid.attach(content,col,row,1,1)
        card('●  CPU',f'{s.cpu:.0f}%',h.cpu_name,['cpu'],f'{h.frequency:.2f} GHz  ·  {os.cpu_count()} logical CPUs  ·  {len(s.rows)} processes',0,0)
        card('●  Memory',self.human(s.memory),f'{self.human(s.memory)} / {self.human(s.total)}  ·  {s.memory/s.total*100:.0f}% used',['memory'],f'Available {self.human(h.mem.get("MemAvailable",0))}  ·  Cached {self.human(h.mem.get("Cached",0))}',1,0)
        card('▣  Disk · '+h.disk_name,f'{h.disk_busy:.0f}%','Active time · busiest physical device',['disk'],f'Read {self.human(h.disk_read)}/s  ·  Write {self.human(h.disk_write)}/s',0,1)
        card('⇄  Network',f'{(h.net_rx+h.net_tx)*8/1e6:.2f} Mbps',h.net_name+'  ·  '+(', '.join(h.addresses.get(h.net_name,[])) or 'No global IP address'),['rx','tx'],f'↓ {self.human(h.net_rx)}/s  ·  ↑ {self.human(h.net_tx)}/s',1,1,False)
        gpu=h.gpu; value=f'{gpu["usage"]:.0f}%' if gpu.get('usage') is not None else 'Unavailable'
        details=[]
        if gpu.get('used') is not None and gpu.get('total'): details.append(f'VRAM {gpu["used"]/1024:.1f} / {gpu["total"]/1024:.1f} GB')
        if gpu.get('temperature') is not None: details.append(f'{gpu["temperature"]:.0f} °C')
        if gpu.get('power') is not None: details.append(f'{gpu["power"]:.0f} W')
        card('▣  GPU',value,gpu.get('name','Detecting sensors…'),['gpu'],'  ·  '.join(details) or 'Sensor access depends on your GPU driver',0,2)
        system=box(spacing=4); system.add_css_class('card'); system.append(label('System information','card-title'))
        boot=time.strftime('%b %d, %Y · %H:%M',time.localtime(time.time()-h.uptime))
        for title,value in [('Hostname',h.hostname),('OS',self.distro),('Kernel',platform.release()),('Architecture',platform.machine()),('Uptime',duration(h.uptime)),('Last boot',boot)]:
            line=box(False,12); a=label(title,'muted'); a.set_size_request(95,-1); line.append(a); line.append(label(value,'small')); system.append(line)
        grid.attach(system,1,2,1,1); self.scroll_content(grid)
    def render_users(self,rows):
        content=padded(box(spacing=10)); users={}
        for row in rows:
            try: uid=__import__('pwd').getpwnam(row['user']).pw_uid
            except KeyError: continue
            if uid>=60000 or (uid<1000 and uid!=os.getuid()): continue
            users.setdefault(row['user'],[]).append(row)
        content.append(label(f'{len(users)} desktop account(s) with running processes','muted'))
        for user,processes in sorted(users.items()):
            cpu=sum(r['cpu'] for r in processes); memory=sum(r['memory'] for r in processes)
            expander=Gtk.Expander(); expander.add_css_class('user-card'); header=box(False,14); avatar=label('●','avatar'); header.append(avatar)
            name=label(user); name.set_hexpand(True); header.append(name); header.append(label(f'{len(processes)} processes','muted')); header.append(label(f'{cpu:.1f}%  ·  {self.human(memory)}','metric')); expander.set_label_widget(header)
            children=box(spacing=0); padded(children,12)
            for row in sorted(processes,key=lambda r:r['cpu'],reverse=True)[:50]:
                line=box(False,12); line.add_css_class('user-process'); name=label(row['name']); name.set_hexpand(True); line.append(name); line.append(label(str(row['pid']),'muted')); line.append(label(f'{row["cpu"]:.1f}%  ·  {self.human(row["memory"])}','small')); children.append(line)
            if len(processes)>50: children.append(label(f'First 50 of {len(processes)} processes · see Details for all','muted'))
            expander.set_child(children); expander.set_expanded(user in self.expanded_users)
            def expanded(widget,_,name=user):
                if widget.get_expanded(): self.expanded_users.add(name)
                else: self.expanded_users.discard(name)
            expander.connect('notify::expanded',expanded); content.append(expander)
        self.scroll_content(content)
    def startup_entries(self):
        apps={}; config_root=Path(os.environ.get('XDG_CONFIG_HOME',str(Path.home()/'.config')))
        for folder in (Path('/etc/xdg/autostart'),config_root/'autostart'):
            for path in folder.glob('*.desktop'):
                c=configparser.ConfigParser(interpolation=None,strict=False); c.optionxform=str
                try:
                    c.read(path); d=c['Desktop Entry']; hidden=d.get('Hidden','false').lower()=='true' or d.get('X-GNOME-Autostart-enabled','true').lower()=='false'
                    apps[path.name]=dict(name=d.get('Name',path.stem),enabled=not hidden,command=d.get('Exec',''),filename=path.name,path=str(path),icon=d.get('Icon','application-x-executable-symbolic'))
                except (configparser.Error,KeyError,OSError): continue
        return sorted(apps.values(),key=lambda r:r['name'].casefold())
    def set_startup(self,entry,enabled):
        destination=Path(os.environ.get('XDG_CONFIG_HOME',str(Path.home()/'.config')))/'autostart'/entry['filename']
        c=configparser.ConfigParser(interpolation=None,strict=False); c.optionxform=str; c.read(entry['path']); c['Desktop Entry']['Hidden']='false' if enabled else 'true'; c['Desktop Entry']['X-GNOME-Autostart-enabled']='true' if enabled else 'false'
        destination.parent.mkdir(parents=True,exist_ok=True)
        import io
        data=io.StringIO(); c.write(data,space_around_delimiters=False)
        temp=destination.with_suffix('.desktop.tmp'); temp.write_text(data.getvalue()); temp.replace(destination)
    def render_startup(self):
        content=padded(box(spacing=6)); content.append(label('Desktop autostart · changes apply at your next login','muted'))
        entries=[r for r in self.startup_entries() if self.query in (r['name']+' '+r['command']).casefold()]
        if not entries: content.append(label('No matching desktop autostart entries.','muted'))
        for entry in entries:
            row=box(False,14); row.add_css_class('startup-row'); icon=Gtk.Image.new_from_icon_name(entry['icon']); icon.set_pixel_size(28); row.append(icon)
            text=box(spacing=3); text.set_hexpand(True); text.append(label(entry['name'])); text.append(label(entry['command'],'muted')); row.append(text)
            row.append(label('Enabled' if entry['enabled'] else 'Disabled','muted')); toggle=Gtk.Switch(); toggle.set_valign(Gtk.Align.CENTER); toggle.set_active(entry['enabled']); row.append(toggle)
            def change(widget,active,item=entry):
                def apply():
                    try: self.set_startup(item,active); self.render()
                    except (OSError,configparser.Error) as error: self.show_error('Could not update autostart',str(error))
                self.ask(f'{"Enable" if active else "Disable"} {item["name"]} at login?','This changes only your user desktop autostart entry. It does not stop a running application.',apply)
                return True
            toggle.connect('state-set',change); content.append(row)
        self.scroll_content(content)
    def render_services(self):
        self.table([('Service','name',str),('State','status',str),('Load','load',str),('Description','description',str)],self.services_cache)
    def refresh_services(self):
        if getattr(self,'services_busy',False): return
        self.services_busy=True; command=['systemctl']+(['--user'] if self.service_scope=='User services' else [])+['list-units','--all','--type=service','--no-legend','--plain','--no-pager']
        try:
            process=Gio.Subprocess.new(command,Gio.SubprocessFlags.STDOUT_PIPE|Gio.SubprocessFlags.STDERR_PIPE)
            def complete(proc,result):
                try:
                    ok,out,err=proc.communicate_utf8_finish(result)
                    services=[]
                    for line in out.splitlines():
                        parts=line.split(None,4)
                        if len(parts)==5: services.append(dict(name=parts[0],load=parts[1],status=parts[3],description=parts[4]))
                    self.all_services=services
                    self.services_cache=[r for r in services if self.query in (r['name']+' '+r['description']).casefold()]
                    if not proc.get_successful(): self.service_note.set_text(err.strip() or 'Service manager unavailable')
                    if self.page=='Services': self.render()
                except GLib.Error as error: self.show_error('Could not read services',str(error))
                finally: self.services_busy=False
            process.communicate_utf8_async(None,None,complete)
        except GLib.Error as error: self.services_busy=False; self.show_error('Service manager unavailable',str(error))
    def service_action(self,_,action):
        item=self.selection.get_selected_item()
        if not item or self.service_scope!='User services': return
        name=item.data['name']
        def apply():
            try:
                process=Gio.Subprocess.new(['systemctl','--user',action,'--',name],Gio.SubprocessFlags.STDOUT_PIPE|Gio.SubprocessFlags.STDERR_PIPE)
                def complete(proc,result):
                    try:
                        _,out,err=proc.communicate_utf8_finish(result)
                        if not proc.get_successful(): self.show_error('Service action failed',err.strip() or out.strip())
                        self.refresh_services()
                    except GLib.Error as error: self.show_error('Service action failed',str(error))
                process.communicate_utf8_async(None,None,complete)
            except GLib.Error as error: self.show_error('Service action failed',str(error))
        self.ask(f'{action.capitalize()} {name}?','This changes the selected user service immediately.',apply)
    def render_settings(self):
        config = self.config_path
        settings = read_appearance(config)
        content = padded(box(spacing=18))
        content.append(label('Appearance', 'heading'))
        presets = {'Lumina': 'lumina.json', 'Black Raptor': 'black-raptor.json',
                   'Mockup Blue': 'mockup-blue.json'}
        modes = ['auto', 'gtk', 'palette']
        themes = ['Automatic', 'Follow GTK theme', 'Saved app palette', *presets]
        row = box(False, 12)
        row.append(label('Theme'))
        choice = Gtk.DropDown.new_from_strings(themes)
        mode = settings.get('theme_mode')
        choice.set_selected(modes.index(mode) if mode in modes else 0)
        row.append(choice)
        apply = Gtk.Button(label='Apply theme')
        row.append(apply)
        content.append(row)

        def save(values):
            try:
                config.parent.mkdir(parents=True, exist_ok=True)
                config.write_text(json.dumps(values, indent=2) + '\n')
            except OSError as error:
                self.show_error('Could not save settings', str(error))
                return False
            self.tick()
            return True

        def apply_theme(_):
            index = choice.get_selected()
            values = read_appearance(config)
            values['theme_mode'] = modes[min(index, len(modes) - 1)]
            if index >= len(modes):
                values.update(read_appearance(Path(__file__).parent / 'palettes' / presets[themes[index]]))
                values.update(font_size=int(font.get_value()), row_padding=int(spacing.get_value()))
            save(values)

        apply.connect('clicked', apply_theme)
        for title,key,minimum,maximum,default in [('Text size','font_size',14,22,16),('Row padding','row_padding',4,16,8)]:
            row=box(False,12); row.append(label(title)); spin=Gtk.SpinButton.new_with_range(minimum,maximum,1); spin.set_value(settings.get(key,default) if isinstance(settings.get(key,default),(int,float)) else default); row.append(spin); content.append(row)
            if key=='font_size': font=spin
            else: spacing=spin
        button=Gtk.Button(label='Save text and spacing'); button.set_halign(Gtk.Align.START)
        def save_spacing(_):
            values = read_appearance(config)
            values.update(font_size=int(font.get_value()),row_padding=int(spacing.get_value())); save(values)
        button.connect('clicked',save_spacing); content.append(button)
        path=label(str(config),'muted'); path.set_selectable(True); content.append(path)
        button=Gtk.Button(label='Open color file'); button.set_halign(Gtk.Align.START)
        def open_colors(_):
            if not config.exists() and not save({'theme_mode': 'auto', **self.default_colors}):
                return
            try:
                Gio.AppInfo.launch_default_for_uri(config.as_uri(), None)
            except GLib.Error as error:
                self.show_error('Could not open color file', str(error))
        button.connect('clicked', open_colors); content.append(button)
        content.append(label('History is kept in memory for this run only. No background recorder or network access.','muted'))
        self.scroll_content(content)
    def ask(self,title,description,callback):
        dialog=Gtk.MessageDialog(transient_for=self.window,modal=True,text=title,secondary_text=description,buttons=Gtk.ButtonsType.OK_CANCEL)
        def response(widget,answer):
            widget.destroy()
            if answer==Gtk.ResponseType.OK: callback()
        dialog.add_css_class('rice-task-manager'); dialog.connect('response',response); dialog.present()
    def show_error(self,title,message):
        dialog=Gtk.MessageDialog(transient_for=self.window,modal=True,text=title,secondary_text=message,buttons=Gtk.ButtonsType.CLOSE); dialog.add_css_class('rice-task-manager'); dialog.connect('response',lambda d,_:d.destroy()); dialog.present()
