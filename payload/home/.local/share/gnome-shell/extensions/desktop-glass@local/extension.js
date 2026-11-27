import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import St from 'gi://St';
import Gio from 'gi://Gio';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import * as Drawing from './drawing.js';
import {GlassPopupMenus} from './popupMenus.js';
import {SystemStats} from './system.js';

const GLASS_UUID = 'blur-my-shell@aunetx';
const DOCK_UUID = 'dash-to-panel@jderose9.github.com';
const DOCK_SCHEMA = 'org.gnome.shell.extensions.dash-to-panel';
const CARDS = [
    {key: 'clock', width: 228, height: 228, radius: 114, grip: [190, 190], title: 'Desktop clock'},
    {key: 'system', width: 330, height: 228, radius: 30, grip: [312, 211], title: 'System stats and specs'},
];
const EDGE = 12;

function clamp(value, min, max) {
    return Math.min(Math.max(value, min), Math.max(min, max));
}

class Card {
    constructor(def, settings, dockSettings, paint) {
        this.def = def;
        this.settings = settings;
        this.dockSettings = dockSettings;
        this.paint = paint;
        this.values = settings.get_value(def.key).deep_unpack();
        this.actor = new St.Widget({
            name: `desktop-glass-${def.key}`,
            accessible_name: def.title,
            reactive: true,
            track_hover: true,
            layout_manager: new Clutter.BinLayout(),
        });
        this.canvas = new St.DrawingArea({
            x_expand: true,
            y_expand: true,
            x_align: Clutter.ActorAlign.FILL,
            y_align: Clutter.ActorAlign.FILL,
        });
        this.actor.add_child(this.canvas);
        this.canvas.connect('repaint', () => this.draw());
        this.actor.connect('notify::hover', () => this.canvas.queue_repaint());
        this.actor.connect('button-press-event', (_actor, event) => this.start(event));
        this.actor.connect('motion-event', (_actor, event) => this.motion(event));
        this.actor.connect('button-release-event', (_actor, event) => this.finish(event));
        this.actor.connect('notify::mapped', () => {
            if (!this.actor.mapped)
                this.end();
        });
    }

    place(monitor, values = this.values) {
        if (!monitor)
            return;
        this.monitor = monitor;
        const [left, top, scale] = values;
        const {width, height} = this.def;
        const maxScale = Math.min(1.85, (monitor.width - 2 * EDGE) / width,
            (monitor.height - 2 * EDGE) / height);
        const size = clamp(scale, Math.min(0.66, maxScale), maxScale);
        const w = Math.round(width * size);
        const h = Math.round(height * size);
        const x = Math.round(clamp(left, EDGE, monitor.width - w - EDGE));
        const y = Math.round(clamp(top, EDGE, monitor.height - h - EDGE));
        this.values = [x, y, size];
        this.actor.set_position(monitor.x + x, monitor.y + y);
        this.actor.set_size(w, h);
        this.placeGlass();
        this.canvas.queue_repaint();
    }

    draw() {
        const [w, h] = this.canvas.get_surface_size();
        if (w <= 1 || h <= 1)
            return;
        const cr = this.canvas.get_context();
        try {
            const {width, height, radius, grip} = this.def;
            cr.scale(w / width, h / height);
            const dockOpacity = this.dockSettings?.get_boolean('trans-use-custom-opacity')
                ? this.dockSettings.get_double('trans-panel-opacity') : 0.28;
            Drawing.surface(cr, width, height, radius, Boolean(this.glass?.wallpaper.source),
                Math.min(dockOpacity * 0.3, 0.084));
            this.paint(cr);
            if (this.actor.hover || this.drag)
                Drawing.resizeGrip(cr, ...grip);
        } finally {
            cr.$dispose();
        }
    }

    start(event) {
        if (event.get_button() !== 1 || this.drag || !this.monitor)
            return Clutter.EVENT_PROPAGATE;
        const [x, y] = event.get_coords();
        const [, localX, localY] = this.actor.transform_stage_point(x, y);
        const [left, top, scale] = this.values;
        const [gx, gy] = this.def.grip;
        const resize = Math.abs(localX / scale - gx + 3) < 18 &&
            Math.abs(localY / scale - gy + 3) < 18;
        this.actor.get_parent().set_child_above_sibling(this.actor, null);
        const grab = global.stage.grab(this.actor);
        this.drag = {x, y, left, top, scale, resize, grab};
        this.canvas.queue_repaint();
        return Clutter.EVENT_STOP;
    }

    motion(event) {
        if (!this.drag)
            return Clutter.EVENT_PROPAGATE;
        const [x, y] = event.get_coords();
        const drag = this.drag;
        const dx = x - drag.x;
        const dy = y - drag.y;
        const [gx, gy] = this.def.grip;
        const values = drag.resize
            ? [drag.left, drag.top, drag.scale + (dx * gx + dy * gy) / (gx ** 2 + gy ** 2)]
            : [drag.left + dx, drag.top + dy, drag.scale];
        this.place(this.monitor, values);
        return Clutter.EVENT_STOP;
    }

    finish(event) {
        if (!this.drag || event.get_button() !== 1)
            return Clutter.EVENT_PROPAGATE;
        this.end();
        this.settings.set_value(this.def.key, new GLib.Variant('(iid)', this.values));
        return Clutter.EVENT_STOP;
    }

    end() {
        const drag = this.drag;
        this.drag = null;
        drag?.grab.dismiss();
        if (drag)
            this.canvas.queue_repaint();
    }

    placeGlass() {
        if (!this.glass || !this.monitor)
            return;
        const {layer, wallpaper, rounded} = this.glass;
        const [x, y, scale] = this.values;
        layer.set_size(Math.round(this.def.width * scale), Math.round(this.def.height * scale));
        wallpaper.set_position(-x, -y);
        wallpaper.set_size(this.monitor.width, this.monitor.height);
        rounded.update();

        const manager = Main.layoutManager._bgManagers[this.monitor.index];
        if (manager !== this.backgroundManager) {
            this.backgroundManager?.disconnect(this.backgroundChangedId);
            this.backgroundManager = manager;
            this.backgroundChangedId = manager?.connect('changed', () => this.syncWallpaper());
        }
        this.syncWallpaper();
    }

    syncWallpaper() {
        this.glass.wallpaper.source = this.backgroundManager?.backgroundActor ?? null;
        this.canvas.queue_repaint();
    }

    clearGlass() {
        if (!this.glass)
            return;
        this.backgroundManager?.disconnect(this.backgroundChangedId);
        this.backgroundManager = null;
        this.backgroundChangedId = null;
        this.glass.rounded.destroy();
        this.glass.pipeline.destroy();
        this.glass.layer.destroy();
        this.glass = null;
    }

    setGlass(provider, Pipeline, RoundedPipeline) {
        this.clearGlass();
        if (provider) {
            // These widgets sit with the wallpaper. Cloning it avoids framebuffer
            // capture and keeps the blur working when the display uses HDR.
            const layer = new Clutter.Actor({clip_to_allocation: true});
            const wallpaper = new Clutter.Clone();
            layer.add_child(wallpaper);
            this.actor.insert_child_at_index(layer, 0);

            const pipeline = new Pipeline(provider._effects_manager, provider._pipelines_manager,
                'pipeline_dock_clear_glass', layer);
            const rounded = new RoundedPipeline(provider._effects_manager,
                () => this.def.radius * this.values[2]);
            rounded.bind(pipeline, layer);
            this.glass = {layer, wallpaper, pipeline, rounded};
            this.placeGlass();
        }
        this.canvas.queue_repaint();
    }

    destroy() {
        this.end();
        this.clearGlass();
        this.actor.destroy();
    }
}

export default class DesktopGlass extends Extension {
    enable() {
        this._settings = this.getSettings();
        this._interface = new Gio.Settings({schema_id: 'org.gnome.desktop.interface'});
        this._popupMenus = new GlassPopupMenus(this._interface);
        const syncTheme = () => {
            const dark = this._interface.get_string('color-scheme') === 'prefer-dark';
            const theme = dark ? 'Crimson-dark' : 'Crimson';
            const icons = dark ? 'Tela-circle-red-dark' : 'Tela-circle-red-light';
            if (this._interface.get_string('gtk-theme') !== theme)
                this._interface.set_string('gtk-theme', theme);
            if (this._interface.get_string('icon-theme') !== icons)
                this._interface.set_string('icon-theme', icons);
        };
        this._interface.connectObject('changed::color-scheme', syncTheme, this);
        syncTheme();
        this._stats = new SystemStats();
        this._stats.sample();
        const dock = Main.extensionManager.lookup(DOCK_UUID);
        const dockSchemaDir = dock?.dir.get_child('schemas');
        const dockSchema = dockSchemaDir?.query_exists(null)
            ? Gio.SettingsSchemaSource.new_from_directory(
                dockSchemaDir.get_path(), Gio.SettingsSchemaSource.get_default(), false)
                .lookup(DOCK_SCHEMA, true)
            : null;
        const dockSettings = dockSchema ? new Gio.Settings({settings_schema: dockSchema}) : null;
        this._cards = [
            new Card(CARDS[0], this._settings, dockSettings, cr => Drawing.clock(cr,
                GLib.DateTime.new_now_local(), this._interface.get_string('clock-format') === '12h')),
            new Card(CARDS[1], this._settings, dockSettings, cr => Drawing.system(cr, this._stats)),
        ];

        this._layer = new Clutter.Actor({name: 'desktop-glass-widgets'});
        // Mutter restacks siblings in the window group. Keep widgets with the wallpaper.
        Main.layoutManager._backgroundGroup.add_child(this._layer);
        this._cards.forEach(card => this._layer.add_child(card.actor));
        const place = () => {
            const monitor = Main.layoutManager.primaryMonitor;
            this._cards.forEach(card => card.place(monitor));
        };
        this._monitorId = Main.layoutManager.connect('monitors-changed', place);
        this._startupId = Main.layoutManager.connect('startup-complete', place);
        place();

        this._extensionsId = Main.extensionManager.connect('extension-state-changed', (_manager, extension) => {
            if (extension.uuid === GLASS_UUID)
                this._syncGlass();
        });
        this._syncGlass();

        let tick = 0;
        this._timer = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 1, () => {
            if (this._layer.mapped) {
                this._cards[0].canvas.queue_repaint();
                if (++tick % 2 === 0) {
                    this._stats.sample();
                    this._cards[1].canvas.queue_repaint();
                }
            }
            return GLib.SOURCE_CONTINUE;
        });
    }

    async _syncGlass() {
        const cards = this._cards;
        const provider = global.blur_my_shell;
        if (!cards || this._glassProvider === provider)
            return;
        this._glassProvider = provider;
        if (!provider?._effects_manager || !provider?._pipelines_manager) {
            cards.forEach(card => card.setGlass(null));
            return;
        }
        try {
            const [{Pipeline}, {RoundedPipeline}] = await Promise.all([
                import(provider.dir.resolve_relative_path('pipelines/pipeline.js').get_uri()),
                import(provider.dir.resolve_relative_path('render/rounded_pipeline.js').get_uri()),
            ]);
            if (this._cards === cards && this._glassProvider === provider)
                cards.forEach(card => card.setGlass(provider, Pipeline, RoundedPipeline));
        } catch (error) {
            console.warn(`Desktop Glass is using its built-in surface: ${error.message}`);
        }
    }

    disable() {
        this._popupMenus.destroy();
        this._popupMenus = null;
        this._interface.disconnectObject(this);
        GLib.source_remove(this._timer);
        Main.layoutManager.disconnect(this._monitorId);
        Main.layoutManager.disconnect(this._startupId);
        Main.extensionManager.disconnect(this._extensionsId);
        this._cards.forEach(card => card.destroy());
        this._layer.destroy();
        this._layer = null;
        this._cards = null;
        this._stats = null;
        this._settings = null;
        this._interface = null;
        this._glassProvider = null;
    }
}
