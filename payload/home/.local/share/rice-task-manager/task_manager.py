#!/usr/bin/env python3
"""Rice Task Manager — native GTK4 process monitor for Linux."""
import os, time, signal, pwd, platform, subprocess, collections, json, argparse, re, sys
from pathlib import Path
from system_metrics import HardwareSampler, duration
from views import DashboardViews, read_appearance
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Graphene', '1.0')
from gi.repository import Gtk, Gdk, GLib, Gio, GObject, Graphene
from gtk_palette import GtkPalette

class Row(GObject.Object):
    def __init__(self,data): super().__init__(); self.data=data

HOME = Path.home()
DEFAULT_COLORS = {"background":"#11111b", "sidebar":"#0c0c14", "surface":"#1e1e2e", "border":"#313244", "foreground":"#cdd6f4", "muted":"#9aa6bd", "accent":"#89b4fa", "metric":"#89dceb", "selection":"#313c53"}
CONFIG = Path(os.environ.get('XDG_CONFIG_HOME', str(HOME/'.config'))) / 'rice-task-manager/colors.json'


def load_css(path=None, gtk_palette=None):
    overrides = read_appearance(path if path is not None else CONFIG)
    colors = DEFAULT_COLORS.copy()
    for key, value in overrides.items():
        if key in colors and isinstance(value, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', value):
            colors[key] = value

    theme_mode = overrides.get('theme_mode')
    desktop_colors = None
    if gtk_palette is not None and theme_mode != 'palette':
        desktop_colors = gtk_palette.colors(force=theme_mode == 'gtk')
    if desktop_colors:
        colors = desktop_colors

    font_size = overrides.get('font_size', 16)
    font_size = max(14, min(22, font_size)) if type(font_size) is int else 16
    row_padding = overrides.get('row_padding', 8)
    row_padding = max(4, min(16, row_padding)) if type(row_padding) is int else 8
    css=CSS.replace("FONT_SIZE",str(font_size)).replace("ROW_PADDING",str(row_padding))
    mapping={'#10171e':'background','#10161c':'sidebar','#111b23':'sidebar','#1b2732':'surface','#192733':'surface','#1c2630':'surface','#16222d':'surface','#20303e':'selection','#213d55':'selection','#389cff':'accent','#79c0ff':'metric','#edf2f7':'foreground','#e4eaf1':'foreground','#c5d1dd':'foreground','#9aa9b7':'muted','#303943':'border','#2a3540':'border','#34404b':'border','#303b46':'border','#2d3b48':'border'}
    css = re.sub(r'#[0-9a-f]{6}', lambda match: colors[mapping[match[0]]], css)
    if desktop_colors:
        css += GTK_CSS.format(**desktop_colors)
    css=re.sub(r'([^{}]+)\{', lambda m: ', '.join('window.rice-task-manager' if v.strip()=='window' else '.rice-task-manager '+v.strip() for v in m[1].split(','))+' {', css)
    return css,colors
CSS = '''
window, * { color: #edf2f7; transition-property: none; animation-name: none; opacity: 1; background-image: none; text-shadow: none; -gtk-icon-shadow: none; }
label, text, image { color: #edf2f7; }
placeholder { color: #9aa9b7; }
button:disabled label, button:disabled image { color: #9aa9b7; }
entry, entry text, searchentry, searchentry entry, searchentry text { background-color: #1c2630; background-image: none; color: #edf2f7; caret-color: #edf2f7; }
entry selection, text selection { background-color: #20303e; color: #edf2f7; }
scrolledwindow, viewport, columnview listview { background-color: #10171e; }
scrolledwindow overshoot, scrolledwindow undershoot { background: none; border: none; box-shadow: none; }
scrollbar, scrollbar trough { background-color: #10171e; border: none; box-shadow: none; }
scrollbar slider { background-color: #34404b; border: none; border-radius: 8px; min-width: 6px; min-height: 6px; }
scrollbar slider:hover { background-color: #9aa9b7; }
button, dropdown button, spinbutton { color: #edf2f7; background-color: #1c2630; border: 1px solid #34404b; box-shadow: none; }
columnview row label { color: #edf2f7; }
columnview row label.metric { color: #79c0ff; }
window { background: #10171e; color: #edf2f7; font-family: "Segoe UI", "Inter", sans-serif; font-size: FONT_SIZEpx; }
headerbar { background: #10161c; border-bottom: 1px solid #303943; box-shadow: none; min-height: 46px; }
headerbar title { font-weight: 500; }
.sidebar { background: #10171e; border-right: 1px solid #303943; padding: 16px 8px; }
.sidebar button { background: transparent; border: 0; box-shadow: none; padding: 14px 16px; margin: 3px 0; border-radius: 6px; color: #e4eaf1; }
.sidebar button:hover { background: #1b2732; }
.sidebar button.active { background: #20303e; border-left: 3px solid #389cff; }
.brand { color: #389cff; font-size: 27px; font-weight: 900; }
.muted { color: #9aa9b7; font-size: 12px; }
.toolbar { padding: 16px 24px; border-bottom: 1px solid #2a3540; }
.heading { font-size: 24px; font-weight: 600; }
searchentry, .toolbar button { background: #1c2630; border: 1px solid #34404b; border-radius: 7px; padding: 7px 10px; box-shadow: none; }
columnview { background: #10171e; }
columnview header button { background: #111b23; color: #c5d1dd; padding: 11px 8px; border-bottom: 1px solid #303b46; box-shadow: none; }
columnview row { min-height: 36px; }
columnview row:selected { background: #213d55; }
columnview row:hover { background: #192733; }
.cell { padding: ROW_PADDINGpx 16px; }
.metric { color: #79c0ff; }
.footer { padding: 14px 24px; border-top: 1px solid #303943; }
.card { background: #16222d; border: 1px solid #2d3b48; border-radius: 9px; padding: 20px; }
.big { font-size: 28px; color: #79c0ff; }
columnview row { background: #10171e; box-shadow: inset 0 -1px rgba(140,160,185,0.10); }
label, entry { font-family: "Inter", "Segoe UI", sans-serif; font-size: FONT_SIZEpx; }
label.heading { font-size: 24px; }
label.brand { font-size: 27px; }
label.muted { font-size: 13px; }
label.big { font-size: 28px; }
columnview header button { border: 0; border-bottom: 1px solid #303943; }
searchentry, searchentry text { background: #1c2630; color: #edf2f7; }

.toolbar, .footer { background: #10171e; }
 .sidebar button { min-height: 20px; padding-top: 11px; padding-bottom: 11px; }
.process-menu contents { background: #16222d; color: #edf2f7; border: 1px solid #303943; border-radius: 8px; padding: 12px; }
.process-menu button { background: #1c2630; color: #edf2f7; border: 0; box-shadow: none; padding: 10px 16px; }
.context { padding: 10px 24px; background: #10171e; }
.context button, .context dropdown, .context dropdown button { background: #1c2630; border: 1px solid #34404b; border-radius: 6px; padding: 5px 10px; box-shadow: none; }
.card { padding: 10px 12px; }
label.card-title { font-size: 15px; font-weight: 600; }
label.small { font-size: 14px; }
label.big { font-size: 28px; font-weight: 600; }
.user-card { background: #16222d; border: 1px solid #2d3b48; border-radius: 8px; padding: 16px; }
.user-process { padding: 9px 8px; border-bottom: 1px solid #303943; }
label.avatar { font-size: 34px; color: #389cff; }
.startup-row { background: #16222d; border-bottom: 1px solid #303943; padding: 14px; }
switch:checked { background: #389cff; }
spinbutton, dropdown, .card button { background: #1c2630; color: #edf2f7; }

'''

GTK_CSS = '''
headerbar {{ background-color: {header}; }}
.sidebar {{ background-color: {sidebar}; }}
.process-menu contents, dropdown popover contents {{ background-color: {popover}; border-color: {border}; }}
dropdown popover listview, dropdown popover row {{ background-color: {popover}; }}
dropdown popover row:hover {{ background-color: {surface}; }}
entry selection, text selection {{ color: {selection_foreground}; }}
.sidebar button.active, .sidebar button.active:hover,
columnview row:selected, columnview row:selected:hover,
dropdown row:selected, dropdown row:selected:hover {{ background-color: {selection}; }}
.sidebar button.active {{ border-left-color: {metric}; }}
.sidebar button.active label, .sidebar button.active image,
columnview row:selected label, columnview row:selected label.metric, columnview row:selected image,
dropdown row:selected label, dropdown row:selected image {{ color: {selection_foreground}; }}
'''

def read(path, default=''):
    try: return Path(path).read_text()
    except (OSError, UnicodeError): return default

def human(n):
    for unit in ('B','KB','MB','GB','TB'):
        if abs(n) < 1024: return f'{n:.1f} {unit}'
        n /= 1024
    return f'{n:.1f} PB'

class Sampler:
    def __init__(self):
        self.previous = {}; self.last = time.monotonic(); self.cpu_last = None
        self.history = collections.deque([0.] * 60, maxlen=60)
        self.app_totals={}; self.totals = {}; self.rows = []; self.cpu = 0; self.memory = 0; self.total = 1
    def sample(self):
        now = time.monotonic(); dt = max(now-self.last, .01); self.last = now
        mem = dict((k, int(v.split()[0])*1024) for k,v in (line.split(':',1) for line in read('/proc/meminfo').splitlines()))
        self.total = mem.get('MemTotal',1); self.memory = self.total-mem.get('MemAvailable',0)
        ticks = list(map(int,read('/proc/stat').splitlines()[0].split()[1:9])); total=sum(ticks); idle=ticks[3]+ticks[4]
        if self.cpu_last:
            self.cpu = 100*(1-(idle-self.cpu_last[1])/max(1,total-self.cpu_last[0]))
        self.cpu_last=(total,idle); self.history.append(self.cpu)
        rows=[]; fresh={}; hz=os.sysconf('SC_CLK_TCK')
        for directory in Path('/proc').iterdir():
            if not directory.name.isdigit(): continue
            try:
                stat=(directory/'stat').read_text(); end=stat.rindex(')'); fields=stat[end+2:].split()
                pid=int(directory.name); name=stat[stat.index('(')+1:end]; start=int(fields[19]); key=(pid,start)
                ticks=int(fields[11])+int(fields[12]); rss=int(fields[21])*os.sysconf('SC_PAGE_SIZE')
                io=dict(line.split(': ',1) for line in read(directory/'io').splitlines()); disk=int(io.get('read_bytes',0))+int(io.get('write_bytes',0))
                old=self.previous.get(key,(ticks,disk)); cpu=max(0,(ticks-old[0])/hz/dt*100); rate=max(0,(disk-old[1])/dt)
                uid=directory.stat().st_uid; user=pwd.getpwuid(uid).pw_name
                fresh[key]=(ticks,disk); self.totals[key]=self.totals.get(key,0)+max(0,ticks-old[0])/hz
                history=self.app_totals.setdefault(name,dict(name=name,time=0.,io=0.,memory=0,processes=0))
                history['time']+=max(0,ticks-old[0])/hz; history['io']+=max(0,disk-old[1]); history['memory']=max(history['memory'],rss)
                command=read(directory/'cmdline').replace(chr(0),' ').strip() or '['+name+']'
                rows.append(dict(command=command,pid=pid,start=start,name=name,status={'R':'Running','S':'Running','I':'Running','D':'Waiting for I/O','T':'Stopped','t':'Stopped','Z':'Zombie'}.get(fields[0],fields[0]),scheduler={'R':'Executing','S':'Sleeping · waiting','I':'Idle kernel thread','D':'Uninterruptible I/O','T':'Stopped','t':'Tracing stop','Z':'Zombie'}.get(fields[0],fields[0]),cpu=cpu,memory=rss,disk=rate,user=user,time=self.totals[key]))
            except (OSError,ValueError,KeyError,IndexError): continue
        self.previous=fresh; self.totals={k:self.totals[k] for k in fresh}; self.rows=rows

class TaskManager(DashboardViews, Gtk.Application):
    def __init__(self):
        super().__init__(application_id='local.rice.TaskManager'+('.Test' if os.environ.get('RICE_TASK_MANAGER_UI_TEST') else ('.Preview' if os.environ.get('RICE_TASK_MANAGER_PREVIEW') else ''))); self.sampler=Sampler(); self.hardware=HardwareSampler(); self.graph_samples=30; self.expanded_users=set(); self.services_cache=[]; self.all_services=[]; self.service_scope='User services'; self.brand_icons=[]; self.config_path=CONFIG; self.default_colors=DEFAULT_COLORS; self.human=human; self.page='Processes'; self.query=''; self.buttons={}; self.paused=False
    def do_activate(self):
        if hasattr(self,'window'): self.window.present(); return
        settings=Gtk.Settings.get_default()
        if settings is None:
            print('Rice Task Manager requires a graphical GTK session.', file=sys.stderr)
            self.quit()
            return
        settings.set_property('gtk-enable-animations',False)
        self.gtk_palette = GtkPalette(settings)
        self.charts = []
        self.app_icons={}
        for app in Gio.AppInfo.get_all():
            executable=app.get_executable()
            if executable and app.get_icon(): self.app_icons[Path(executable).name.casefold()]=app.get_icon()
        provider=Gtk.CssProvider(); self.css,self.colors=load_css(self.config_path, self.gtk_palette); self.provider=provider; provider.load_from_data(self.css.encode()); Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),provider,Gtk.STYLE_PROVIDER_PRIORITY_USER+1)
        self.window=Gtk.ApplicationWindow(application=self,title='Task Manager'); self.window.add_css_class("rice-task-manager"); self.window.set_default_size(1280,820)
        header=Gtk.HeaderBar(); title=Gtk.Box(spacing=10); a=self.brand_mark(27); title.append(a); title.append(Gtk.Label(label='Task Manager')); header.pack_start(title); header.set_title_widget(Gtk.Label(label='')); self.window.set_titlebar(header)
        root=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL); self.window.set_child(root)
        side=Gtk.Box(orientation=Gtk.Orientation.VERTICAL); side.set_size_request(220,-1); side.add_css_class('sidebar'); root.append(side)
        branding=Gtk.Box(spacing=10); branding.set_margin_start(14); branding.set_margin_bottom(20)
        logo=self.brand_mark(30); branding.append(logo)
        branding.append(Gtk.Label(label='Linux Task Manager',xalign=0)); side.append(branding)
        for icon,name in [('view-grid-symbolic','Processes'),('utilities-system-monitor-symbolic','Performance'),('document-open-recent-symbolic','App history'),('system-run-symbolic','Startup apps'),('system-users-symbolic','Users'),('view-list-symbolic','Details'),('emblem-system-symbolic','Services'),('preferences-system-symbolic','Settings')]:
            button=Gtk.Button(); content=Gtk.Box(spacing=17); content.append(Gtk.Image.new_from_icon_name(icon)); content.append(Gtk.Label(label=name)); button.set_child(content); button.connect('clicked',lambda _,n=name:self.navigate(n)); side.append(button); self.buttons[name]=button
        spacer=Gtk.Box(); spacer.set_vexpand(True); side.append(spacer)
        distro=read('/etc/os-release').splitlines(); self.distro=next((v.split('=',1)[1].strip(chr(34)) for v in distro if v.startswith('NAME=')),'Linux')
        self.info=Gtk.Label(xalign=0); self.info.add_css_class('muted'); self.info.set_margin_start(16); side.append(self.info)
        main=Gtk.Box(orientation=Gtk.Orientation.VERTICAL); main.set_hexpand(True); root.append(main)
        toolbar=Gtk.Box(spacing=12); toolbar.add_css_class('toolbar'); main.append(toolbar)
        self.heading=Gtk.Label(label='Processes',xalign=0); self.heading.add_css_class('heading'); self.heading.set_hexpand(True); toolbar.append(self.heading)
        self.search=Gtk.SearchEntry(placeholder_text='Search processes'); self.search.set_size_request(240,-1); self.search.connect('search-changed',self.search_changed); toolbar.append(self.search)
        self.pause=Gtk.Button(label='Pause'); self.pause.connect('clicked',self.toggle_pause); toolbar.append(self.pause)
        self.end=Gtk.Button(label='End task'); self.end.connect('clicked',self.confirm_end); toolbar.append(self.end)
        self.context=Gtk.Box(spacing=12); self.context.add_css_class('context'); main.append(self.context)
        self.body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL); self.body.set_vexpand(True); main.append(self.body)
        self.footer=Gtk.Label(xalign=0); self.footer.add_css_class('footer'); main.append(self.footer)
        self.sampler.sample(); self.hardware.sample(self.sampler)
        self.navigate(os.environ.get('RICE_TASK_MANAGER_PAGE','Processes')); GLib.timeout_add(2000,self.tick); self.window.present()
        if os.environ.get('RICE_TASK_MANAGER_UI_TEST'):
            self.test_pages=iter(['Performance','App history','Startup apps','Users','Details','Services','Settings','Processes'])
            GLib.timeout_add(350,self.smoke_page)
    def brand_mark(self,size):
        data=json.loads((Path(__file__).parent/'arch-mark.json').read_text())
        area=Gtk.DrawingArea(); area.set_content_width(size); area.set_content_height(size); area.set_valign(Gtk.Align.CENTER)
        def draw(_,cr,width,height):
            x1,y1,x2,y2=data['bounds']; scale=min(width/(x2-x1),height/(y2-y1))
            cr.translate((width-(x2-x1)*scale)/2,(height-(y2-y1)*scale)/2); cr.scale(scale,scale); cr.translate(-x1,-y1)
            for kind,points in data['path']:
                if kind==0: cr.move_to(*points)
                elif kind==1: cr.line_to(*points)
                elif kind==2: cr.curve_to(*points)
                elif kind==3: cr.close_path()
            color=self.colors['metric']; cr.set_source_rgb(*(int(color[i:i+2],16)/255 for i in (1,3,5))); cr.fill()
        area.set_draw_func(draw); self.brand_icons.append(area); return area
    def smoke_page(self):
        try:
            page=next(self.test_pages); self.navigate(page); print('UI PASS:',page,flush=True)
            return True
        except StopIteration:
            self.search.set_text('python'); self.query='python'; self.render()
            assert self.table_store.get_n_items()>0
            print('UI PASS: search and refresh',flush=True)
            self.query=''; self.search.set_text('')
            fixtures=[dict(name=f'test{v}',pid=90000+v,start=0,status='Sleeping',cpu=float(v),memory=v*1024,disk=float(v),user='test') for v in (2,100,10)]
            for key in ('cpu','memory','disk'):
                for direction in (Gtk.SortType.ASCENDING,Gtk.SortType.DESCENDING):
                    self.table_store.splice(0,self.table_store.get_n_items(),[Row(r) for r in fixtures])
                    self.table_view.sort_by_column(self.sort_columns[key],direction)
                    model=self.selection.get_model(); values=[model.get_item(i).data[key] for i in range(model.get_n_items())]
                    assert values==sorted(values,reverse=direction==Gtk.SortType.DESCENDING),(key,values)
                    self.tick(); model=self.selection.get_model(); values=[model.get_item(i).data[key] for i in range(model.get_n_items())]
                    assert values==sorted(values,reverse=direction==Gtk.SortType.DESCENDING),(key,'refresh reset sort')
                print('UI PASS: numeric sort both directions and refresh:',key,flush=True)
            original=self.confirm_end; captured=[]; self.confirm_end=lambda _,row=None:captured.append(row)
            target=dict(name='context-target',pid=987654,start=123)
            menu,button=self.process_menu(target,self.table_view,40,50)
            target['pid']=111111
            self.tick(); button.emit('clicked')
            assert captured[0]['pid']==987654 and captured[0]['start']==123
            self.confirm_end=original
            print('UI PASS: context menu retains right-clicked process through refresh',flush=True)
            self.quit(); return False
    def search_changed(self,entry):
        self.query=entry.get_text().casefold()
        if self.page=='Services': self.services_cache=[r for r in self.all_services if self.query in (r['name']+' '+r['description']).casefold()]
        self.render()
    def toggle_pause(self,_):
        self.paused=not self.paused; self.pause.set_label('Resume' if self.paused else 'Pause'); self.update_footer()
    def navigate(self,page):
        if getattr(self,'process_popover',None): self.process_popover.popdown()
        self.charts.clear()
        self.page=page; self.heading.set_text(page)
        self.query=''; self.search.set_text(''); self.search.set_placeholder_text('Search '+page.lower())
        for name,button in self.buttons.items():
            (button.add_css_class if name==page else button.remove_css_class)('active')
        self.end.set_visible(page in ('Processes','Details')); self.search.set_visible(page not in ('Performance','Settings'))
        child=self.context.get_first_child()
        while child:
            nxt=child.get_next_sibling(); self.context.remove(child); child=nxt
        self.context.set_visible(page in ('Performance','App history','Startup apps','Users','Services','Details'))
        if page=='Performance':
            note=Gtk.Label(label='Live hardware telemetry'); note.add_css_class('muted'); note.set_hexpand(True); note.set_xalign(0); self.context.append(note)
            period=Gtk.DropDown.new_from_strings(['60 seconds','120 seconds']); period.set_selected(0 if self.graph_samples==30 else 1)
            def change(widget,_): self.graph_samples=30 if widget.get_selected()==0 else 60; self.render()
            period.connect('notify::selected',change); self.context.append(period)
        elif page=='App history':
            note=Gtk.Label(label='Observed CPU and disk I/O · since this window opened'); note.add_css_class('muted'); note.set_hexpand(True); note.set_xalign(0); self.context.append(note)
            reset=Gtk.Button(label='Reset history'); reset.connect('clicked',lambda _:self.ask('Reset observed app history?','This clears only the in-memory history for this run.',self.reset_history)); self.context.append(reset)
        elif page=='Services':
            scope=Gtk.DropDown.new_from_strings(['User services','System services']); self.context.append(scope)
            def change(widget,_):
                self.service_scope='User services' if widget.get_selected()==0 else 'System services'
                for button in self.service_buttons: button.set_sensitive(self.service_scope=='User services')
                self.service_note.set_text('Controls apply to user services.' if self.service_scope=='User services' else 'System services · read-only'); self.refresh_services()
            self.service_buttons=[]
            for action in ('start','stop','restart'):
                button=Gtk.Button(label=action.capitalize()); button.connect('clicked',self.service_action,action); self.context.append(button); self.service_buttons.append(button)
            self.service_note=Gtk.Label(label='Controls apply to user services.'); self.service_note.add_css_class('muted'); self.context.append(self.service_note); scope.set_selected(0 if self.service_scope=='User services' else 1); scope.connect('notify::selected',change)
            for button in self.service_buttons: button.set_sensitive(self.service_scope=='User services')
            self.refresh_services()
        elif page in ('Startup apps','Users','Details'):
            text={'Startup apps':'Desktop login entries · toggle to enable or disable','Users':'Expand an account to inspect its processes','Details':'All processes · click a header to sort'}[page]
            note=Gtk.Label(label=text,xalign=0); note.add_css_class('muted'); self.context.append(note)
        self.render()
    def reset_history(self): self.sampler.app_totals.clear(); self.render()
    def update_footer(self):
        s=self.sampler
        self.footer.set_text(f'{len(s.rows)} processes     •     CPU {s.cpu:.1f}%     •     Memory {human(s.memory)} / {human(s.total)}'+('     •     Updates paused' if self.paused else ''))
    def tick(self):
        css,colors=load_css(self.config_path, self.gtk_palette)
        if css!=self.css:
            self.css,self.colors=css,colors; self.provider.load_from_data(css.encode())
            for drawing in self.brand_icons + self.charts: drawing.queue_draw()
        if not self.paused:
            self.sampler.sample(); self.hardware.sample(self.sampler)
            if self.page=='Services': self.refresh_services()
            if self.page not in ('Settings','Startup apps'): self.render()
        self.update_footer()
        return True
    def clear(self):
        child=self.body.get_first_child()
        while child:
            nxt=child.get_next_sibling(); self.body.remove(child); child=nxt
    def table(self,columns,rows):
        signature=tuple(c[0] for c in columns)
        old_selection=getattr(self,'selection',None); old_item=old_selection.get_selected_item() if old_selection else None
        old_key=(old_item.data.get('pid'),old_item.data.get('name')) if old_item else None
        if getattr(self,'table_signature',None)==signature and getattr(self,'table_scroll',None) is not None:
            if self.table_scroll.get_parent() is None: self.body.append(self.table_scroll)
            self.table_store.splice(0,self.table_store.get_n_items(),[Row(r) for r in rows])
            if old_key:
                model=self.selection.get_model()
                for i in range(model.get_n_items()):
                    row=model.get_item(i).data
                    if (row.get('pid'),row.get('name'))==old_key: self.selection.set_selected(i); break
            return
        self.table_signature=signature
        store=Gio.ListStore.new(Row)
        self.table_store=store
        for row in rows: store.append(Row(row))
        selection=Gtk.SingleSelection.new(store); selection.set_autoselect(False); self.selection=selection
        view=Gtk.ColumnView.new(selection); self.table_view=view; self.sort_columns={}; view.set_show_row_separators(False); view.set_vexpand(True)
        for index,(title,key,fmt) in enumerate(columns):
            factory=Gtk.SignalListItemFactory()
            def setup(_,item,i=index):
                text=Gtk.Label(xalign=0); text.set_ellipsize(3); item.text_label=text
                if columns[i][1] in ('cpu','memory','disk','io','time'): text.add_css_class('metric')
                if i==0 and columns[i][1]=='name':
                    cell=Gtk.Box(spacing=12); cell.add_css_class('cell'); icon=Gtk.Image(); icon.set_pixel_size(21); cell.append(icon); cell.append(text); item.app_icon=icon; item.set_child(cell)
                else: text.add_css_class('cell'); item.app_icon=None; item.set_child(text)
                if self.page in ('Processes','Details'):
                    click=Gtk.GestureClick.new(); click.set_button(Gdk.BUTTON_SECONDARY)
                    click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
                    click.connect('pressed',lambda gesture,n,x,y,entry=item:self.process_right_click(gesture,entry,x,y))
                    item.get_child().add_controller(click)
            def bind(_,item,k=key,f=fmt):
                row=item.get_item().data; item.text_label.set_text(f(row.get(k,''))); item.get_child().set_tooltip_text(row.get('command') or str(row.get(k,'')))
                if item.app_icon is not None: item.app_icon.set_from_gicon(self.app_icons.get(row.get('name','').casefold(),Gio.ThemedIcon.new('application-x-executable-symbolic')))
            factory.connect('setup',setup); factory.connect('bind',bind)
            column=Gtk.ColumnViewColumn.new(title,factory); column.set_expand(index==0 or key=='description'); column.set_resizable(True); column.set_fixed_width(260 if index==0 else (360 if key=='description' else (200 if title in ('Observed CPU time','Scheduler state') else (125 if key=='pid' else (100 if key=='cpu' else 145)))))
            sorter=Gtk.CustomSorter.new(lambda a,b,_,k=key: (a.data.get(k,'')>b.data.get(k,''))-(a.data.get(k,'')<b.data.get(k,'')),None); column.set_sorter(sorter); view.append_column(column); self.sort_columns[key]=column
        sorted_model=Gtk.SortListModel.new(store,view.get_sorter()); selection.set_model(sorted_model)
        if 'cpu' in self.sort_columns: view.sort_by_column(self.sort_columns['cpu'],Gtk.SortType.DESCENDING)
        elif 'time' in self.sort_columns: view.sort_by_column(self.sort_columns['time'],Gtk.SortType.DESCENDING)
        scroll=Gtk.ScrolledWindow(); scroll.set_vexpand(True); scroll.set_child(view); self.body.append(scroll); self.table_scroll=scroll
    def render(self):
        if not hasattr(self,'body') or getattr(self,'process_popover',None): return
        # Keep selected PID across live updates.
        selected=getattr(self,'selection',None); item=selected.get_selected_item() if selected else None; selected_pid=item.data.get('pid') if item else None
        table_page=self.page in ('Processes','Details','App history','Services')
        if not (table_page and getattr(self,'rendered_page',None)==self.page): self.clear()
        self.rendered_page=self.page
        s=self.sampler; rows=[r for r in s.rows if self.query in f"{r['name']} {r['pid']} {r['user']}".casefold()]
        rows.sort(key=lambda r:r['cpu'],reverse=True)
        distro=read('/etc/os-release').splitlines(); distro=next((v.split('=',1)[1].strip(chr(34)) for v in distro if v.startswith('NAME=')),'Linux')
        self.info.set_text(f'{distro}   A\nKernel {platform.release()}\nUptime: {int(float(read("/proc/uptime","0").split()[0])//3600)}h {int(float(read("/proc/uptime","0").split()[0])%3600//60)}m')
        self.footer.set_text(f'{len(s.rows)} processes     •     CPU {s.cpu:.1f}%     •     Memory {human(s.memory)} / {human(s.total)}'+('     •     Updates paused' if self.paused else ''))
        if self.page in ('Processes','Details','App history'):
            columns=[('Name','name',str),('Status','status',str),('CPU','cpu',lambda v:f'{v:.1f}%'),('Memory','memory',human),('Disk','disk',lambda v:human(v)+'/s'),('PID','pid',str),('User','user',str)]
            if self.page=='Processes': columns=columns[:5]
            if self.page=='Details': columns=[('Name','name',str),('PID','pid',str),('Scheduler state','scheduler',str),('CPU','cpu',lambda v:f'{v:.1f}%'),('Memory','memory',human),('Owner','user',str)]
            if self.page=='App history':
                columns=[('Application','name',str),('Observed CPU time','time',lambda v:f'{int(v)//3600}h {int(v)%3600//60}m {int(v)%60}s'),('Disk I/O','io',human),('Peak RAM','memory',human)]
                rows=[r for r in s.app_totals.values() if self.query in r['name'].casefold()]
                rows.sort(key=lambda r:r['time'],reverse=True)
            self.table(columns,rows)
            if selected_pid:
                model=self.selection.get_model()
                for i in range(model.get_n_items()):
                    if model.get_item(i).data.get('pid')==selected_pid: self.selection.set_selected(i); break
        elif self.page=='Performance': self.render_performance()
        elif self.page=='Users': self.render_users(rows)
        elif self.page=='Startup apps': self.render_startup()
        elif self.page=='Settings': self.render_settings()
        elif self.page=='Services': self.render_services()
    def process_right_click(self,gesture,item,x,y):
        target=item.get_item()
        if target is None or self.page not in ('Processes','Details'): return
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        self.selection.set_selected(item.get_position())
        self.process_menu(target.data,gesture.get_widget(),x,y)
    def process_menu(self,row,anchor,x,y):
        # Freeze identity now: live sorting may move/recycle this row before activation.
        target=row.copy()
        point=Graphene.Point(); point.init(x,y)
        ok,point=anchor.compute_point(self.table_view,point)
        if not ok: return
        rectangle=Gdk.Rectangle(); rectangle.x=int(point.x); rectangle.y=int(point.y); rectangle.width=1; rectangle.height=1
        menu=Gtk.Popover(); menu.add_css_class('process-menu'); menu.set_parent(self.table_view); menu.set_pointing_to(rectangle); menu.set_has_arrow(False)
        content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6)
        title=Gtk.Label(label=f'{target["name"]} · {target["pid"]}',xalign=0); title.add_css_class('muted'); content.append(title)
        end=Gtk.Button(label='End task'); end.set_sensitive(target['pid'] not in (1,os.getpid())); content.append(end)
        def activate(_):
            menu.popdown(); self.confirm_end(None,target)
        end.connect('clicked',activate); menu.set_child(content)
        self.process_popover=menu
        def closed(widget):
            if self.process_popover is widget: self.process_popover=None
            widget.unparent()
        menu.connect('closed',closed); menu.popup()
        return menu,end
    def confirm_end(self,_,row=None):
        if row is None:
            item=self.selection.get_selected_item()
            if not item: return
            row=item.data.copy()
        else: row=row.copy()
        dialog=Gtk.MessageDialog(transient_for=self.window,modal=True,text=f'End {row["name"]} ({row["pid"]})?',secondary_text='The process will receive SIGTERM. Unsaved work in this process may be lost.',buttons=Gtk.ButtonsType.OK_CANCEL)
        def response(d,answer):
            d.destroy()
            if answer!=Gtk.ResponseType.OK: return
            try:
                stat=read(f'/proc/{row["pid"]}/stat'); fields=stat[stat.rindex(')')+2:].split()
                if int(fields[19])!=row['start']: raise ProcessLookupError('Process has changed')
                if row['pid'] in (1,os.getpid()): raise PermissionError('This process is protected')
                os.kill(row['pid'],signal.SIGTERM); self.tick()
            except (OSError,ValueError) as error:
                msg=Gtk.MessageDialog(transient_for=self.window,modal=True,text='Could not end task',secondary_text=str(error),buttons=Gtk.ButtonsType.CLOSE); msg.add_css_class('rice-task-manager'); msg.connect('response',lambda d,_:d.destroy()); msg.present()
        dialog.add_css_class('rice-task-manager'); dialog.connect('response',response); dialog.present()

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test',action='store_true')
    args=parser.parse_args()
    if args.self_test:
        sampler=Sampler(); sampler.sample(); time.sleep(.15); sampler.sample()
        assert sampler.rows and sampler.total>0 and 0<=sampler.cpu<=100
        assert any(r['pid']==os.getpid() for r in sampler.rows)
        css,colors=load_css(); assert colors['accent'] in css
        print(f"PASS: {len(sampler.rows)} processes, CPU {sampler.cpu:.1f}%, RAM {human(sampler.memory)} / {human(sampler.total)}")
    else: TaskManager().run(argv=[__file__])
