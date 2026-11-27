import Clutter from 'gi://Clutter';
import St from 'gi://St';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import {InjectionManager} from 'resource:///org/gnome/shell/extensions/extension.js';
import {BoxPointer, PopupAnimation} from 'resource:///org/gnome/shell/ui/boxpointer.js';

const EDGE_INSET = 3;
const OPEN_DISTANCE = 12;
const CLOSE_DISTANCE = 8;
const ROOT_CLASS = 'desktop-glass-popup';
const BODY_CLASS = 'desktop-glass-popup-body';

function dockFor(source) {
    if (!source)
        return null;

    return global.dashToPanel?.panels?.find(panel =>
        panel.geom?.position === St.Side.BOTTOM && panel.contains(source)) ?? null;
}

function motion(side, distance) {
    switch (side) {
    case St.Side.TOP: return [0, -distance];
    case St.Side.BOTTOM: return [0, distance];
    case St.Side.LEFT: return [-distance, 0];
    case St.Side.RIGHT: return [distance, 0];
    default: return [0, 0];
    }
}

function animateOpen(pointer, complete) {
    pointer.remove_all_transitions();
    const [x, y] = motion(pointer.arrowSide, OPEN_DISTANCE);
    pointer.opacity = 0;
    pointer.translation_x = x;
    pointer.translation_y = y;
    pointer._muteInput = true;
    pointer._muteKeys = false;
    pointer.show();
    pointer.ease({
        opacity: 255,
        translation_x: 0,
        translation_y: 0,
        duration: 175,
        mode: Clutter.AnimationMode.EASE_OUT_CUBIC,
        onComplete: () => {
            pointer._muteInput = false;
            complete?.();
        },
    });
}

function animateClose(pointer, complete) {
    pointer._muteInput = true;
    pointer._muteKeys = true;
    pointer.remove_all_transitions();
    const [x, y] = motion(pointer.arrowSide, CLOSE_DISTANCE);
    pointer.ease({
        opacity: 0,
        translation_x: x,
        translation_y: y,
        duration: 115,
        mode: Clutter.AnimationMode.EASE_IN_QUAD,
        onComplete: () => {
            pointer.hide();
            pointer.translation_x = 0;
            pointer.translation_y = 0;
            complete?.();
        },
    });
}

function alignWithDock(pointer, box, dock) {
    let parent = pointer.get_parent();
    if (!parent)
        return;

    const bounds = dock.get_transformed_extents();
    const top = bounds.get_top_left();
    const bottom = bounds.get_bottom_right();
    const work = pointer._workArea;
    const width = box.get_width();
    const source = pointer._sourceExtents;
    if (!work || !source || width <= 0 || work.width <= 0 ||
        ![top.x, top.y, bottom.x, work.x, work.width, width, box.x1, box.y1].every(Number.isFinite))
        return;

    const stageLeft = Math.max(top.x + EDGE_INSET, work.x);
    const stageRight = Math.min(bottom.x - EDGE_INSET, work.x + work.width);
    if (stageLeft >= stageRight)
        return;

    // Quick Settings can wrap its box pointer in a zero-sized actor.
    let left, right, monitorLeft;
    for (; parent; parent = parent.get_parent()) {
        const [offsetOk, offset] = parent.transform_stage_point(work.x, top.y);
        const [leftOk, localLeft] = parent.transform_stage_point(stageLeft, top.y);
        const [rightOk, localRight] = parent.transform_stage_point(stageRight, top.y);
        if (!offsetOk || !leftOk || !rightOk ||
            ![offset, localLeft, localRight].every(Number.isFinite) || localLeft >= localRight)
            continue;
        [left, right, monitorLeft] = [localLeft, localRight, offset];
        break;
    }
    if (!parent)
        return;

    const furthestRight = right - width;
    const sourceCenter = source.get_top_left().x + source.get_width() / 2;
    if (!Number.isFinite(sourceCenter))
        return;
    const status = Object.values(dock.statusArea ?? {}).some(item =>
        item?.menu?._boxPointer === pointer);
    const rightAligned = status && !pointer.has_style_class_name('tray-overflow-popup') &&
        sourceCenter >= (top.x + bottom.x) / 2;

    const x = width > right - left
        ? Math.max(monitorLeft, furthestRight)
        : rightAligned ? furthestRight : Math.clamp(box.x1, left, furthestRight);
    box.set_origin(Math.round(x), box.y1);
}

export class GlassPopupMenus {
    constructor(interfaceSettings) {
        this._interface = interfaceSettings;
        this._injections = new InjectionManager();
        this._popups = new Map();

        const manager = this;
        this._injections.overrideMethod(BoxPointer.prototype, 'open', original =>
            function (animate, complete) {
                if (!manager._prepare(this) || animate === PopupAnimation.NONE)
                    return original.call(this, animate, complete);
                animateOpen(this, complete);
            });

        this._injections.overrideMethod(BoxPointer.prototype, 'close', original =>
            function (animate, complete) {
                if (!this.visible || !manager._popups.has(this) || animate === PopupAnimation.NONE)
                    return original.call(this, animate, complete);
                animateClose(this, complete);
            });

        this._injections.overrideMethod(BoxPointer.prototype, '_reposition', original =>
            function (box) {
                original.call(this, box);
                const dock = manager._popups.get(this)?.dock;
                if (dock && (this.arrowSide === St.Side.BOTTOM || this.arrowSide === St.Side.TOP))
                    alignWithDock(this, box, dock);
            });

        this._interface.connectObject('changed::color-scheme', () => {
            this._popups.forEach((_entry, pointer) => this._setTint(pointer));
        }, this);
    }

    _prepare(pointer) {
        if (pointer.has_style_class_name('arcmenu-menu'))
            return false;

        const dock = dockFor(pointer._sourceActor);
        if (!dock && !pointer.has_style_class_name('background-menu')) {
            this._forget(pointer);
            return false;
        }

        const entry = this._popups.get(pointer);
        if (entry?.dock === dock)
            return true;
        if (entry)
            this._forget(pointer);

        const body = pointer.bin.get_child();
        pointer.add_style_class_name(ROOT_CLASS);
        body?.add_style_class_name(BODY_CLASS);
        this._setTint(pointer);

        const relayout = () => {
            if (pointer.visible)
                pointer.queue_relayout();
        };
        const destroyId = pointer.connect('destroy', () => this._forget(pointer, true));
        const state = {dock, body, destroyId};
        dock?.connectObject(
            'notify::allocation', relayout,
            'destroy', () => (state.dock = null), pointer);
        this._popups.set(pointer, state);
        if (pointer.has_style_class_name('background-menu')) {
            const actor = Main.layoutManager._bgManagers
                .map(bgManager => bgManager.backgroundActor)
                .find(background => background._backgroundMenu?.actor === pointer);
            if (actor) {
                const { _backgroundManager: manager, _backgroundMenu: menu } = actor;
                // GNOME's modal grab starts event dispatch at the popup. Put
                // our handler before the manager's default outside-click close.
                manager.removeMenu(menu);
                state.backgroundClickId = pointer.connect('captured-event', (_pointer, event) =>
                    this._repeatBackgroundClick(menu, event));
                manager.addMenu(menu);
            }
        }
        return true;
    }

    _repeatBackgroundClick(menu, event) {
        const type = event.type();
        if (type !== Clutter.EventType.BUTTON_PRESS &&
            type !== Clutter.EventType.BUTTON_RELEASE)
            return Clutter.EVENT_PROPAGATE;
        if (event.get_button() !== Clutter.BUTTON_SECONDARY)
            return Clutter.EVENT_PROPAGATE;
        if (type === Clutter.EventType.BUTTON_RELEASE) {
            if (!this._consumeBackgroundRelease)
                return Clutter.EVENT_PROPAGATE;
            this._consumeBackgroundRelease = false;
            return Clutter.EVENT_STOP;
        }
        this._consumeBackgroundRelease = false;

        const closing = this._backgroundReopen;
        const current = closing?.menu ?? menu;
        if (!closing && !current.isOpen)
            return Clutter.EVENT_PROPAGATE;

        const [x, y] = event.get_coords();
        let target = global.stage.get_actor_at_pos(Clutter.PickMode.REACTIVE, x, y);
        if (target && current.actor.contains(target))
            return Clutter.EVENT_PROPAGATE;
        while (target && !target._backgroundMenu)
            target = target.get_parent();
        if (!target)
            return Clutter.EVENT_PROPAGATE;

        this._consumeBackgroundRelease = true;
        if (closing) {
            Object.assign(closing, {target, x, y});
        } else {
            const state = {menu: current, target, x, y};
            state.closedId = current.connect('menu-closed', () => {
                this._cancelBackgroundReopen();
                if (state.target._backgroundMenu) {
                    Main.layoutManager.setDummyCursorGeometry(state.x, state.y, 0, 0);
                    state.target._backgroundMenu.open(PopupAnimation.FULL);
                }
            });
            state.destroyId = current.connect('destroy', () => this._cancelBackgroundReopen());
            this._backgroundReopen = state;
            current.close(PopupAnimation.FULL);
        }
        return Clutter.EVENT_STOP;
    }

    _cancelBackgroundReopen() {
        const state = this._backgroundReopen;
        this._backgroundReopen = null;
        if (state) {
            state.menu.disconnect(state.closedId);
            state.menu.disconnect(state.destroyId);
        }
    }

    _setTint(pointer) {
        const light = this._interface.get_string('color-scheme') !== 'prefer-dark';
        if (light)
            pointer.add_style_class_name('desktop-glass-popup-light');
        else
            pointer.remove_style_class_name('desktop-glass-popup-light');
    }

    _forget(pointer, destroyed = false) {
        const entry = this._popups.get(pointer);
        if (!entry)
            return;
        this._popups.delete(pointer);
        if (!destroyed) {
            entry.dock?.disconnectObject(pointer);
            pointer.disconnect(entry.destroyId);
            if (entry.backgroundClickId)
                pointer.disconnect(entry.backgroundClickId);
            pointer.remove_style_class_name(ROOT_CLASS);
            pointer.remove_style_class_name('desktop-glass-popup-light');
            entry.body?.remove_style_class_name(BODY_CLASS);
        }
    }

    destroy() {
        this._cancelBackgroundReopen();
        this._injections.clear();
        this._interface.disconnectObject(this);
        this._popups.forEach((_entry, pointer) => this._forget(pointer));
    }
}
