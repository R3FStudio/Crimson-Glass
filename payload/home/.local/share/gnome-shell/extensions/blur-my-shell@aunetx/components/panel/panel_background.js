import Clutter from 'gi://Clutter';
import Meta from 'gi://Meta';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import { ANIMATION_TIME } from 'resource:///org/gnome/shell/ui/overview.js';

import { Pipeline } from '../../pipelines/pipeline.js';
import { DynamicPipeline } from '../../render/dynamic_surface.js';
import { RoundedPipeline } from '../../render/rounded_pipeline.js';
import { get_pipeline_id } from '../../conveniences/style.js';

/// Creates the blur behind a panel, inserted at the bottom of its panel box.
export function create_panel_background(panel_box, monitor, settings, effects_manager) {
    const background_group = new Meta.BackgroundGroup(
        { name: 'bms-panel-backgroundgroup', width: 0, height: 0 }
    );

    let background, bg_manager, pipeline;
    let rounded_pipeline = null;
    const static_blur = settings.panel.STATIC_BLUR;

    if (static_blur) {
        const bg_manager_list = [];
        pipeline = new Pipeline(
            effects_manager,
            global.blur_my_shell._pipelines_manager,
            get_pipeline_id(settings.panel),
        );
        background = pipeline.create_background_with_effects(
            monitor.index, bg_manager_list,
            background_group, 'bms-panel-blurred-widget'
        );
        bg_manager = bg_manager_list[0];
        rounded_pipeline = new RoundedPipeline(
            effects_manager,
            () => settings.panel.CORNER_RADIUS,
            () => settings.panel.ROUNDED_CORNERS
        );
        rounded_pipeline.bind(pipeline, background);
    } else {
        pipeline = new DynamicPipeline(
            effects_manager,
            global.blur_my_shell._pipelines_manager,
            get_pipeline_id(settings.panel),
            {
                corner_radius: settings.panel.CORNER_RADIUS,
                get_corners: () => settings.panel.ROUNDED_CORNERS,
            }
        );
        [background, bg_manager] = pipeline.create_background_with_effect(
            background_group, 'bms-panel-blurred-widget'
        );
    }

    panel_box.insert_child_at_index(background_group, 0);
    return { background, background_group, bg_manager, pipeline, rounded_pipeline, static_blur };
}

/// Moves the blur under the panel, returning false if the panel isn't allocated yet.
export function place_panel_background(actors) {
    const { panel, panel_box, wrapper, background, background_group } = actors.widgets;
    // Dash to Panel paints the tint on its outer wrapper. The background group
    // is a sibling and already inherits the panel box’s padding.
    const geometry_actor = actors.is_dtp_panel ? wrapper : panel;
    panel_box.get_allocation_box();
    geometry_actor.get_allocation_box();
    background_group.get_allocation_box();
    const [geometry_width, geometry_height] = geometry_actor.get_size();
    const [actor_x, actor_y] = geometry_actor.get_position();
    const [group_x, group_y] = background_group.get_position();
    const x = actor_x - group_x;
    const y = actor_y - group_y;

    if (![x, y, geometry_width, geometry_height].every(Number.isFinite) ||
        geometry_width <= 0 || geometry_height <= 0)
        return false;

    if (actors.static_blur) {
        // The static pipeline samples the monitor wallpaper, then clips to the dock.
        const monitor = Main.layoutManager.findMonitorForActor(geometry_actor);
        if (!monitor)
            return false;
        const [stage_x, stage_y] = geometry_actor.get_transformed_position();
        if (![stage_x, stage_y].every(Number.isFinite))
            return false;
        const monitor_x = stage_x - monitor.x;
        const monitor_y = stage_y - monitor.y;
        const left = Math.floor(monitor_x);
        const top = Math.floor(monitor_y);
        background.set_clip(left, top,
            Math.ceil(monitor_x + geometry_width) - left,
            Math.ceil(monitor_y + geometry_height) - top);
        background.set_position(x - monitor_x, y - monitor_y);
    } else {
        background.set_position(x, y);
        background.set_size(geometry_width, geometry_height);
    }

    return true;
}

/// Fades the blur in step with the overview, which fades the panel's own background.
export function fade_panel_background(actors, opacity, onComplete) {
    actors.widgets.background_group.ease({
        opacity,
        duration: ANIMATION_TIME,
        mode: Clutter.AnimationMode.EASE_OUT_QUAD,
        onComplete,
    });
}

export function reset_panel_background_fade(actors) {
    const { background_group } = actors.widgets;
    background_group.remove_all_transitions();
    background_group.opacity = 255;
}
