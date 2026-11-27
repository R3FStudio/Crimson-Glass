#define _POSIX_C_SOURCE 200809L
#include <adwaita.h>
#include <dlfcn.h>
#include <stdlib.h>

#define DOCK_SCHEMA "org.gnome.shell.extensions.dash-to-panel"
#define DOCK_SCHEMA_DIR "gnome-shell/extensions/dash-to-panel@jderose9.github.com/schemas"
#define RESTORE_PRELOAD "GNOME_SETTINGS_DOCK_ORIGINAL_PRELOAD"

/* Limit the launcher’s preload to this process. */
__attribute__((constructor))
static void restore_preload_environment(void)
{
    const char *saved = getenv(RESTORE_PRELOAD);

    if (!saved)
        return;
    if (*saved)
        setenv("LD_PRELOAD", saved, 1);
    else
        unsetenv("LD_PRELOAD");
    unsetenv(RESTORE_PRELOAD);
}

static void add_dock_switch(GtkWidget *panel)
{
    GObject *preview = gtk_widget_get_template_child(panel, G_OBJECT_TYPE(panel), "default_toggle");
    if (!GTK_IS_WIDGET(preview))
        return;

    GtkWidget *group = gtk_widget_get_ancestor(GTK_WIDGET(preview), ADW_TYPE_PREFERENCES_GROUP);
    if (!group)
        return;

    g_autofree char *path = g_build_filename(g_get_user_data_dir(), DOCK_SCHEMA_DIR, NULL);
    g_autoptr(GSettingsSchemaSource) source =
        g_settings_schema_source_new_from_directory(path, g_settings_schema_source_get_default(),
                                                    FALSE, NULL);
    g_autoptr(GSettingsSchema) schema = source
        ? g_settings_schema_source_lookup(source, DOCK_SCHEMA, TRUE)
        : NULL;
    if (!schema || !g_settings_schema_has_key(schema, "intellihide"))
        return;

    GtkWidget *row = adw_switch_row_new();
    gtk_widget_set_name(row, "always-show-dock-row");
    adw_preferences_row_set_title(ADW_PREFERENCES_ROW(row), "Always show dock");
    adw_action_row_set_subtitle(ADW_ACTION_ROW(row), "Keep the dock visible on the desktop.");
    adw_preferences_group_add(ADW_PREFERENCES_GROUP(group), row);

    g_autoptr(GSettings) settings = g_settings_new_full(schema, NULL, NULL);
    g_settings_bind(settings, "intellihide", row, "active",
                    G_SETTINGS_BIND_DEFAULT | G_SETTINGS_BIND_INVERT_BOOLEAN);
#ifdef TEST_BINDING
    g_assert_true(g_settings_set_boolean(settings, "intellihide", TRUE));
    g_assert_false(adw_switch_row_get_active(ADW_SWITCH_ROW(row)));
    adw_switch_row_set_active(ADW_SWITCH_ROW(row), TRUE);
    g_assert_false(g_settings_get_boolean(settings, "intellihide"));
    g_assert_true(g_settings_set_boolean(settings, "intellihide", TRUE));
    g_assert_false(adw_switch_row_get_active(ADW_SWITCH_ROW(row)));
    g_printerr("DOCK_TOGGLE_SYNC_OK\n");
#endif
}

void gtk_widget_init_template(GtkWidget *widget)
{
    static void (*real_init_template)(GtkWidget *);
    if (!real_init_template)
        real_init_template = dlsym(RTLD_NEXT, "gtk_widget_init_template");

    real_init_template(widget);

    if (g_str_equal(G_OBJECT_TYPE_NAME(widget), "CcBackgroundPanel"))
        add_dock_switch(widget);
}
