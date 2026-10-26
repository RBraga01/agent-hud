#ifndef AGENT_HUD_MEMOMIND_RENDERER_H
#define AGENT_HUD_MEMOMIND_RENDERER_H

#include "gm_plugin_lvgl_api.h"

#include "agent_hud_theme.h"
#include "agent_hud_view.h"

#define AH_RENDERER_WIDTH 600
#define AH_RENDERER_HEIGHT 350
#define AH_RENDERER_IDENTITY_BYTES 176U

typedef struct {
    const gm_plugin_lvgl_api_t *ui;
    gm_plugin_lvgl_obj_t *canvas;
    gm_plugin_lvgl_point_t check_points[3];
    gm_plugin_lvgl_point_t warning_points[4];
    char identity[AH_RENDERER_IDENTITY_BYTES];
} ah_renderer_t;

bool ah_renderer_start(ah_renderer_t *renderer,
                       const gm_plugin_lvgl_api_t *ui,
                       gm_plugin_lvgl_obj_t *host_root,
                       int16_t display_width, int16_t display_height);
bool ah_renderer_render(ah_renderer_t *renderer, const ah_view_t *view,
                        ah_theme_t theme);
bool ah_renderer_message(ah_renderer_t *renderer, const char *heading,
                         const char *body);
void ah_renderer_stop(ah_renderer_t *renderer);

#endif
