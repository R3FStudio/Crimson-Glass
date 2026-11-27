import Clutter from 'gi://Clutter';
import Meta from 'gi://Meta';
import St from 'gi://St';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Extension, InjectionManager} from 'resource:///org/gnome/shell/extensions/extension.js';

export default class SmoothWindowResize extends Extension {
    enable() {
        this._injections = new InjectionManager();
        global.window_manager.connectObject('map', (_wm, actor) => {
            this._fitAboveDock(actor.meta_window);
        }, this);
        global.display.connectObject('workareas-changed', () => {
            for (const actor of global.get_window_actors())
                this._fitAboveDock(actor.meta_window);
        }, this);
        const extension = this;
        this._injections.overrideMethod(Main.wm, '_prepareAnimationInfo', original => {
            return function (shellwm, actor, oldRect, change) {
                original.call(this, shellwm, actor, oldRect, change);
                if (change !== Meta.SizeChange.MAXIMIZE && change !== Meta.SizeChange.UNMAXIMIZE)
                    return;
                const clone = actor.__animationInfo?.clone;
                if (!clone)
                    return;

                const originalCloneEase = clone.ease;
                clone.ease = function (params) {
                    delete this.ease;
                    const windowEase = actor.ease;
                    const ownEase = Object.getOwnPropertyDescriptor(actor, 'ease');
                    actor.ease = function (windowParams) {
                        if (ownEase)
                            Object.defineProperty(this, 'ease', ownEase);
                        else
                            delete this.ease;
                        return windowEase.call(this, extension._transition(windowParams));
                    };
                    return originalCloneEase.call(this, extension._transition(params));
                };
            };
        });
    }

    _fitAboveDock(window) {
        if (!window || window.minimized || window.is_fullscreen() ||
            window.get_window_type() !== Meta.WindowType.NORMAL)
            return;

        const monitor = window.get_monitor();
        const panel = global.dashToPanel?.panels?.find(item => item.monitor.index === monitor);
        if (!panel?.intellihide || panel.intellihide.enabled)
            return;

        const {vertical, position} = panel.geom;
        const atStart = position === St.Side.TOP || position === St.Side.LEFT;
        const axis = vertical ? 'x' : 'y';
        const dimension = vertical ? 'width' : 'height';
        const maximized = vertical ? Meta.MaximizeFlags.HORIZONTAL : Meta.MaximizeFlags.VERTICAL;
        if (window.get_maximized() & maximized)
            return;

        const area = window.get_work_area_current_monitor();
        const frame = window.get_frame_rect();
        const start = area[axis];
        const end = start + area[dimension];
        const overlapsDock = atStart ? frame[axis] < start : frame[axis] + frame[dimension] > end;
        if (!overlapsDock)
            return;

        const size = window.allows_resize()
            ? Math.min(frame[dimension], area[dimension]) : frame[dimension];
        const coordinate = atStart ? start : Math.max(start, end - size);
        if (size === frame[dimension] && coordinate === frame[axis])
            return;

        // Adjust only the axis occupied by the dock and preserve the window’s other dimension.
        frame[axis] = coordinate;
        frame[dimension] = size;
        window.move_resize_frame(false, frame.x, frame.y, frame.width, frame.height);
    }

    _transition(params) {
        if (!this._injections)
            return params;
        return {...params, duration: 340, mode: Clutter.AnimationMode.EASE_OUT_CUBIC};
    }

    disable() {
        global.window_manager.disconnectObject(this);
        global.display.disconnectObject(this);
        this._injections?.clear();
        this._injections = null;
    }
}
