import Clutter from 'gi://Clutter';
import St from 'gi://St';

import {PopupAnimation} from 'resource:///org/gnome/shell/ui/boxpointer.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

export class TrayOverflow {
    constructor(settings) {
        this._items = new Map();
        this._button = new PanelMenu.Button(0.5, 'Background apps');
        this._arrow = new St.Icon({
            icon_name: 'pan-up-symbolic',
            icon_size: 24,
            style_class: 'system-status-icon',
        });
        this._button.add_child(this._arrow);
        this._menu = this._button.menu;
        this._menu.actor.add_style_class_name('tray-overflow-popup');
        this._actions = new St.ScrollView({
            style_class: 'tray-overflow-action-scroll',
            hscrollbar_policy: St.PolicyType.NEVER,
            vscrollbar_policy: St.PolicyType.AUTOMATIC,
            overlay_scrollbars: true,
            x_expand: true,
        });
        this._actions.hide();
        this._menu.box.add_child(this._actions);

        this._gridLayout = new Clutter.GridLayout({
            column_spacing: 4,
            row_spacing: 4,
            column_homogeneous: true,
        });
        this._grid = new St.Widget({
            style_class: 'tray-overflow-icons',
            x_align: Clutter.ActorAlign.CENTER,
            layout_manager: this._gridLayout,
        });
        this._menu.box.add_child(this._grid);

        this._manager = new PopupMenu.PopupMenuManager(this._button);
        // Only an explicit click or keyboard action may switch tray menus.
        this._manager._changeMenu = () => {};
        const role = 'appindicator-overflow';
        const place = () => {
            if (Main.panel.statusArea[role] === this._button)
                delete Main.panel.statusArea[role];
            Main.panel.addToStatusArea(role, this._button, 1, settings.get_string('tray-pos'));
            Main.panel.menuManager.removeMenu(this._menu);
        };
        place();
        settings.connectObject('changed::tray-pos', place, this._button);
        this._manager.addMenu(this._menu);
        const openMenu = this._menu.open.bind(this._menu);
        this._menu.open = animate => {
            this._setArrowSide(this._menu);
            openMenu(animate);
        };
        this._menu.connect('open-state-changed', (_menu, open) => {
            this._arrow.icon_name = open ? 'pan-down-symbolic' : 'pan-up-symbolic';
            if (!open)
                this._closeActions();
        });
        this._button.connect('notify::mapped', () => {
            if (!this._button.mapped)
                this._manager.activeMenu?.close(PopupAnimation.NONE);
        });
        this._button.hide();
    }

    get icons() {
        return Array.from(this._items.values());
    }

    _setArrowSide(menu) {
        const dock = global.dashToPanel?.panels?.find(panel => panel.contains(this._button));
        const side = dock?.geom?.position ?? St.Side.TOP;
        const pointer = menu._boxPointer;
        if (pointer._userArrowSide !== side) {
            pointer._userArrowSide = side;
            pointer.updateArrowSide(side);
        }
    }

    add(icon) {
        const id = icon.uniqueId;
        const current = this._items.get(id);
        if (current === icon)
            return;
        current?.destroy();
        this._items.set(id, icon);
        icon.add_style_class_name('tray-overflow-icon');
        this._gridLayout.attach(icon.container, 0, 0, 1, 1);
        icon.connect('notify::visible', () => {
            if (!icon.visible)
                this._closeActions(icon.menu);
            this._syncVisibility();
        });
        icon.connect('destroy', () => {
            this._items.delete(id);
            this._syncVisibility();
        });

        const menu = icon.menu;
        if (menu instanceof PopupMenu.PopupMenu) {
            // The app's menu owns the DBus items and their signals. Only its
            // contents are shown in the tray, under the same modal grab.
            icon.disconnectObject(menu);
            const nativeClose = menu.close.bind(menu);
            menu.close = animate => {
                if (this._activeActions === menu)
                    this._closeActions();
                else
                    nativeClose(animate);
            };
            menu.connect('destroy', () => {
                if (this._activeActions === menu) {
                    this._activeActions = null;
                    this._actions.hide();
                }
            });
            icon.openTrayMenu = () => this._openActions(menu);
            icon.connect('key-press-event', (_actor, event) => {
                const key = event.get_key_symbol();
                const shift = event.get_state() & Clutter.ModifierType.SHIFT_MASK;
                if (key === Clutter.KEY_Menu || (key === Clutter.KEY_F10 && shift)) {
                    icon.openTrayMenu();
                    return Clutter.EVENT_STOP;
                }
                return Clutter.EVENT_PROPAGATE;
            });
        }
        this._syncVisibility();
    }

    _openActions(menu) {
        if (!this._menu.isOpen || menu.isEmpty())
            return;
        if (this._activeActions === menu) {
            this._closeActions();
            return;
        }

        this._closeActions();
        menu._boxPointer.bin.set_child(null);
        this._actions.set_child(menu.box);
        this._actions.vadjustment.value = 0;
        this._activeActions = menu;
        menu.isOpen = true;
        this._actions.show();
        menu.emit('open-state-changed', true);
    }

    _closeActions(menu = this._activeActions) {
        if (!menu || menu !== this._activeActions)
            return;
        this._activeActions = null;
        if (menu._activeMenuItem)
            menu._activeMenuItem.active = false;
        this._actions.hide();
        this._actions.set_child(null);
        menu._boxPointer.bin.set_child(menu.box);
        menu.isOpen = false;
        menu.emit('open-state-changed', false);
        menu.emit('menu-closed');
    }

    _syncVisibility() {
        const visible = this.icons.filter(icon => icon.visible);
        visible.forEach((icon, index) => {
            const cell = this._gridLayout.get_child_meta(this._grid, icon.container);
            cell.left_attach = index % 6;
            cell.top_attach = Math.floor(index / 6);
        });
        if (!visible.length)
            this._manager.activeMenu?.close(PopupAnimation.NONE);
        this._button.visible = visible.length > 0;
    }

    destroy() {
        this._closeActions();
        this._manager.activeMenu?.close(PopupAnimation.NONE);
        this.icons.forEach(icon => icon.destroy());
        this._button.destroy();
    }
}
