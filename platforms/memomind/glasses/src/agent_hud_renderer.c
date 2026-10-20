#include "agent_hud_renderer.h"

#include <stddef.h>

#define SAFE_X 28
#define SAFE_W 544
#define PRIMARY_GRAY 15U
#define SECONDARY_GRAY 11U

static gm_plugin_lvgl_style_value_t font_value(
    const gm_plugin_lvgl_font_t *font)
{
    gm_plugin_lvgl_style_value_t value = {0};
    value.ptr = font;
    return value;
}

static uint8_t gray(uint8_t level)
{
    return (uint8_t)((level << 4U) | level);
}

static void set_style(ah_renderer_t *self, gm_plugin_lvgl_obj_t *object,
                      gm_plugin_lvgl_style_prop_t property,
                      gm_plugin_lvgl_style_value_t value)
{
    self->ui->style_set(object, property, value,
                        GM_PLUGIN_LVGL_SELECTOR_MAIN);
}

static void style_box(ah_renderer_t *self, gm_plugin_lvgl_obj_t *object,
                      uint8_t fill, bool opaque, uint8_t border_gray,
                      uint8_t border_width, uint8_t radius)
{
    set_style(self, object, GM_PLUGIN_LVGL_STYLE_BG_COLOR,
              gm_plugin_lvgl_style_color(gray(fill)));
    set_style(self, object, GM_PLUGIN_LVGL_STYLE_BG_OPA,
              gm_plugin_lvgl_style_number(opaque
                  ? GM_PLUGIN_LVGL_OPA_COVER
                  : GM_PLUGIN_LVGL_OPA_TRANSPARENT));
    set_style(self, object, GM_PLUGIN_LVGL_STYLE_BORDER_COLOR,
              gm_plugin_lvgl_style_color(gray(border_gray)));
    set_style(self, object, GM_PLUGIN_LVGL_STYLE_BORDER_OPA,
              gm_plugin_lvgl_style_number(border_width == 0U
                  ? GM_PLUGIN_LVGL_OPA_TRANSPARENT
                  : GM_PLUGIN_LVGL_OPA_COVER));
    set_style(self, object, GM_PLUGIN_LVGL_STYLE_BORDER_WIDTH,
              gm_plugin_lvgl_style_number(border_width));
    set_style(self, object, GM_PLUGIN_LVGL_STYLE_RADIUS,
              gm_plugin_lvgl_style_number(radius));
    set_style(self, object, GM_PLUGIN_LVGL_STYLE_PAD_TOP,
              gm_plugin_lvgl_style_number(0));
    set_style(self, object, GM_PLUGIN_LVGL_STYLE_PAD_BOTTOM,
              gm_plugin_lvgl_style_number(0));
    set_style(self, object, GM_PLUGIN_LVGL_STYLE_PAD_LEFT,
              gm_plugin_lvgl_style_number(0));
    set_style(self, object, GM_PLUGIN_LVGL_STYLE_PAD_RIGHT,
              gm_plugin_lvgl_style_number(0));
    self->ui->obj_clear_flag(object, GM_PLUGIN_LVGL_FLAG_SCROLLABLE);
}

static gm_plugin_lvgl_obj_t *box(ah_renderer_t *self, int16_t x, int16_t y,
                                 int16_t width, int16_t height,
                                 uint8_t fill, bool opaque,
                                 uint8_t border_gray, uint8_t border_width,
                                 uint8_t radius)
{
    gm_plugin_lvgl_obj_t *object = self->ui->obj_create(self->canvas);
    if (object == NULL) return NULL;
    self->ui->obj_set_pos(object, x, y);
    self->ui->obj_set_size(object, width, height);
    style_box(self, object, fill, opaque, border_gray, border_width, radius);
    return object;
}

static gm_plugin_lvgl_obj_t *label(ah_renderer_t *self, const char *text,
                                   int16_t x, int16_t y,
                                   int16_t width, int16_t height,
                                   bool large, uint8_t shade,
                                   gm_plugin_lvgl_label_mode_t mode,
                                   uint8_t alignment)
{
    gm_plugin_lvgl_obj_t *object;
    if (text == NULL) return NULL;
    object = self->ui->label_create(self->canvas);
    if (object == NULL) return NULL;
    self->ui->obj_set_pos(object, x, y);
    self->ui->obj_set_size(object, width, height);
    self->ui->label_set_long_mode(object, mode);
    self->ui->label_set_text(object, text);
    set_style(self, object, GM_PLUGIN_LVGL_STYLE_TEXT_COLOR,
              gm_plugin_lvgl_style_color(gray(shade)));
    set_style(self, object, GM_PLUGIN_LVGL_STYLE_TEXT_OPA,
              gm_plugin_lvgl_style_number(GM_PLUGIN_LVGL_OPA_COVER));
    set_style(self, object, GM_PLUGIN_LVGL_STYLE_TEXT_FONT,
              font_value(large ? self->ui->font_large
                               : self->ui->font_default));
    set_style(self, object, GM_PLUGIN_LVGL_STYLE_TEXT_ALIGN,
              gm_plugin_lvgl_style_number(alignment));
    set_style(self, object, GM_PLUGIN_LVGL_STYLE_TEXT_LINE_SPACE,
              gm_plugin_lvgl_style_number(large ? 6 : 4));
    return object;
}

static bool focus_box(ah_renderer_t *self, int16_t x, int16_t y,
                      int16_t width, int16_t height, const char *text,
                      ah_theme_t theme, bool focused)
{
    gm_plugin_lvgl_obj_t *outer;
    uint8_t width_px = focused ? theme.focus_border_width : theme.border_width;
    outer = box(self, x, y, width, height, theme.fill_gray, focused,
                theme.border_gray, width_px, theme.control_radius);
    if (outer == NULL) return false;
    if (focused && box(self, (int16_t)(x + 7), (int16_t)(y + 7),
                       (int16_t)(width - 14), (int16_t)(height - 14), 0U,
                       false, theme.border_gray, 1U,
                       (uint8_t)(theme.control_radius - 3U)) == NULL)
        return false;
    /* The large font's visible glyphs sit four pixels below its LVGL box. */
    return label(self, text, (int16_t)(x + 24),
                 (int16_t)(y + (height - 34) / 2 - 4),
                 (int16_t)(width - 48), 34, true, theme.primary_gray,
                 GM_PLUGIN_LVGL_LABEL_DOT,
                 GM_PLUGIN_LVGL_TEXT_ALIGN_CENTER) != NULL;
}

static bool footer(ah_renderer_t *self, const char *text,
                   uint8_t shade, uint8_t alignment)
{
    return label(self, text, SAFE_X, 308, SAFE_W, 26, false, shade,
                 GM_PLUGIN_LVGL_LABEL_DOT, alignment) != NULL;
}

static bool render_indicator(ah_renderer_t *self, const ah_view_t *view,
                             ah_theme_t theme)
{
    if (box(self, 404, 24, 168, 50, theme.fill_gray, false,
            theme.border_gray, theme.border_width, 12U) == NULL)
        return false;
    return label(self, view->title, 416, 34, 28, 28, true,
                 theme.primary_gray, GM_PLUGIN_LVGL_LABEL_CLIP,
                 GM_PLUGIN_LVGL_TEXT_ALIGN_CENTER) != NULL &&
           label(self, view->detail, 452, 39, 108, 22, false,
                 theme.secondary_gray, GM_PLUGIN_LVGL_LABEL_CLIP,
                 GM_PLUGIN_LVGL_TEXT_ALIGN_LEFT) != NULL;
}

static bool render_offline(ah_renderer_t *self, const ah_view_t *view,
                           ah_theme_t theme)
{
    if (box(self, 464, 24, 108, 42, 0U, false, theme.border_gray,
            theme.border_width, 10U) == NULL)
        return false;
    return label(self, view->heading, 476, 34, 84, 22, false,
                 theme.secondary_gray, GM_PLUGIN_LVGL_LABEL_CLIP,
                 GM_PLUGIN_LVGL_TEXT_ALIGN_CENTER) != NULL;
}

static bool render_request(ah_renderer_t *self, const ah_view_t *view,
                           ah_theme_t theme)
{
    return label(self, view->heading, SAFE_X, 32, SAFE_W, 24, false,
                 theme.primary_gray, GM_PLUGIN_LVGL_LABEL_DOT,
                 GM_PLUGIN_LVGL_TEXT_ALIGN_LEFT) != NULL &&
           label(self, view->title, SAFE_X, 72, SAFE_W, 44, true,
                 theme.primary_gray, GM_PLUGIN_LVGL_LABEL_DOT,
                 GM_PLUGIN_LVGL_TEXT_ALIGN_LEFT) != NULL &&
           label(self, view->body, SAFE_X, 124, SAFE_W, 74, false,
                 theme.secondary_gray, GM_PLUGIN_LVGL_LABEL_WRAP,
                 GM_PLUGIN_LVGL_TEXT_ALIGN_LEFT) != NULL &&
           focus_box(self, SAFE_X, 220, SAFE_W, 68, view->primary_label,
                     theme, true) &&
           footer(self, view->guidance, theme.secondary_gray,
                  GM_PLUGIN_LVGL_TEXT_ALIGN_RIGHT);
}

static bool render_actions(ah_renderer_t *self, const ah_view_t *view,
                           ah_theme_t theme)
{
    int16_t back_x = view->action_count == 1U ? 310 : 28;
    int16_t back_y = view->action_count == 1U ? 67 : 163;
    uint8_t index;
    if (label(self, view->heading, SAFE_X, 32, SAFE_W, 24, false,
              theme.primary_gray, GM_PLUGIN_LVGL_LABEL_DOT,
              GM_PLUGIN_LVGL_TEXT_ALIGN_LEFT) == NULL)
        return false;
    for (index = 0U; index < view->action_count; ++index) {
        int16_t x = index == 0U ? 28 : 310;
        if (!focus_box(self, x, 67, 262, 76, view->actions[index], theme,
                       index == view->focused_action))
            return false;
    }
    if (!focus_box(self, back_x, back_y, 262, 76, "Back", theme, false))
        return false;
    return footer(self, view->guidance, theme.secondary_gray,
                  GM_PLUGIN_LVGL_TEXT_ALIGN_RIGHT);
}

static bool append_text(char *output, size_t capacity, size_t *offset,
                        const char *text)
{
    size_t index = 0U;
    if (text == NULL) return true;
    while (text[index] != '\0') {
        if (*offset + 1U >= capacity) return false;
        output[(*offset)++] = text[index++];
    }
    output[*offset] = '\0';
    return true;
}

static bool append_uint64(char *output, size_t capacity, size_t *offset,
                          uint64_t value)
{
    uint8_t digits[20] = {0U};
    uint8_t bit;
    uint8_t digit;
    bool started = false;
    for (bit = 0U; bit < 64U; ++bit) {
        uint8_t carry =
            (value & UINT64_C(0x8000000000000000)) != 0U ? 1U : 0U;
        for (digit = 0U; digit < 20U; ++digit)
            if (digits[digit] >= 5U) digits[digit] += 3U;
        value <<= 1U;
        digit = 20U;
        while (digit != 0U) {
            uint8_t next_carry;
            --digit;
            next_carry = (digits[digit] & 0x08U) != 0U ? 1U : 0U;
            digits[digit] =
                (uint8_t)(((digits[digit] << 1U) & 0x0FU) | carry);
            carry = next_carry;
        }
    }
    for (digit = 0U; digit < 20U; ++digit) {
        if (!started && digits[digit] == 0U && digit != 19U) continue;
        started = true;
        if (*offset + 1U >= capacity) return false;
        output[(*offset)++] = (char)('0' + digits[digit]);
    }
    output[*offset] = '\0';
    return true;
}

static bool build_identity(ah_renderer_t *self, const ah_view_t *view)
{
    size_t offset = 0U;
    self->identity[0] = '\0';
    return append_text(self->identity, sizeof(self->identity), &offset,
                       "Task ") &&
           append_text(self->identity, sizeof(self->identity), &offset,
                       view->task_id) &&
           append_text(self->identity, sizeof(self->identity), &offset,
                       " · revision ") &&
           append_uint64(self->identity, sizeof(self->identity), &offset,
                         view->revision);
}

static bool render_confirmation(ah_renderer_t *self, const ah_view_t *view,
                                ah_theme_t theme)
{
    if (!build_identity(self, view) ||
        box(self, 20, 20, 560, 310, 0U, false, theme.border_gray,
            theme.focus_border_width, theme.panel_radius) == NULL ||
        box(self, 28, 28, 544, 294, 0U, false, theme.border_gray, 1U,
            (uint8_t)(theme.panel_radius - 4U)) == NULL)
        return false;
    return label(self, view->heading, 48, 50, 484, 26, false,
                 theme.primary_gray, GM_PLUGIN_LVGL_LABEL_DOT,
                 GM_PLUGIN_LVGL_TEXT_ALIGN_LEFT) != NULL &&
           label(self, view->selected_action, 48, 88, 484, 44, true,
                 theme.primary_gray, GM_PLUGIN_LVGL_LABEL_DOT,
                 GM_PLUGIN_LVGL_TEXT_ALIGN_LEFT) != NULL &&
           label(self, self->identity, 48, 136, 484, 28, false,
                 theme.secondary_gray, GM_PLUGIN_LVGL_LABEL_DOT,
                 GM_PLUGIN_LVGL_TEXT_ALIGN_LEFT) != NULL &&
           focus_box(self, 48, 190, 318, 78, view->primary_label,
                     theme, true) &&
           focus_box(self, 386, 190, 146, 78, "Back", theme, false) &&
           label(self, view->guidance, 48, 286, 484, 24, false,
                 theme.secondary_gray, GM_PLUGIN_LVGL_LABEL_DOT,
                 GM_PLUGIN_LVGL_TEXT_ALIGN_LEFT) != NULL;
}

static bool render_sending(ah_renderer_t *self, const ah_view_t *view,
                           ah_theme_t theme)
{
    if (box(self, 110, 92, 380, 158, 0U, false, theme.border_gray,
            theme.border_width, theme.panel_radius) == NULL)
        return false;
    return label(self, view->heading, 134, 126, 332, 38, true,
                 theme.primary_gray, GM_PLUGIN_LVGL_LABEL_DOT,
                 GM_PLUGIN_LVGL_TEXT_ALIGN_CENTER) != NULL &&
           label(self, view->body, 134, 178, 332, 48, false,
                 theme.secondary_gray, GM_PLUGIN_LVGL_LABEL_WRAP,
                 GM_PLUGIN_LVGL_TEXT_ALIGN_CENTER) != NULL;
}

static bool render_check(ah_renderer_t *self, ah_theme_t theme)
{
    gm_plugin_lvgl_obj_t *circle;
    gm_plugin_lvgl_obj_t *check;
    circle = box(self, 254, 54, 92, 92, 0U, false, theme.border_gray,
                 theme.focus_border_width, 46U);
    if (circle == NULL) return false;
    self->check_points[0].x = 276;
    self->check_points[0].y = 104;
    self->check_points[1].x = 294;
    self->check_points[1].y = 122;
    self->check_points[2].x = 327;
    self->check_points[2].y = 84;
    check = self->ui->line_create(self->canvas);
    if (check == NULL) return false;
    self->ui->line_set_points(check, self->check_points, 3U);
    set_style(self, check, GM_PLUGIN_LVGL_STYLE_LINE_COLOR,
              gm_plugin_lvgl_style_color(gray(theme.primary_gray)));
    set_style(self, check, GM_PLUGIN_LVGL_STYLE_LINE_OPA,
              gm_plugin_lvgl_style_number(GM_PLUGIN_LVGL_OPA_COVER));
    set_style(self, check, GM_PLUGIN_LVGL_STYLE_LINE_WIDTH,
              gm_plugin_lvgl_style_number(7));
    set_style(self, check, GM_PLUGIN_LVGL_STYLE_LINE_ROUNDED,
              gm_plugin_lvgl_style_number(1));
    return true;
}

static bool render_sent(ah_renderer_t *self, const ah_view_t *view,
                        ah_theme_t theme)
{
    return render_check(self, theme) &&
           label(self, view->heading, SAFE_X, 166, SAFE_W, 44, true,
                 theme.primary_gray, GM_PLUGIN_LVGL_LABEL_DOT,
                 GM_PLUGIN_LVGL_TEXT_ALIGN_CENTER) != NULL &&
           label(self, view->body, SAFE_X, 218, SAFE_W, 28, false,
                 theme.secondary_gray, GM_PLUGIN_LVGL_LABEL_DOT,
                 GM_PLUGIN_LVGL_TEXT_ALIGN_CENTER) != NULL &&
           label(self, view->detail, SAFE_X, 252, SAFE_W, 26, false,
                 theme.primary_gray, GM_PLUGIN_LVGL_LABEL_DOT,
                 GM_PLUGIN_LVGL_TEXT_ALIGN_CENTER) != NULL &&
           footer(self, view->guidance, theme.secondary_gray,
                  GM_PLUGIN_LVGL_TEXT_ALIGN_RIGHT);
}

static bool render_warning_icon(ah_renderer_t *self, ah_theme_t theme)
{
    gm_plugin_lvgl_obj_t *line;
    self->warning_points[0].x = 52;
    self->warning_points[0].y = 36;
    self->warning_points[1].x = 78;
    self->warning_points[1].y = 80;
    self->warning_points[2].x = 26;
    self->warning_points[2].y = 80;
    self->warning_points[3].x = 52;
    self->warning_points[3].y = 36;
    line = self->ui->line_create(self->canvas);
    if (line == NULL) return false;
    self->ui->line_set_points(line, self->warning_points, 4U);
    set_style(self, line, GM_PLUGIN_LVGL_STYLE_LINE_COLOR,
              gm_plugin_lvgl_style_color(gray(theme.primary_gray)));
    set_style(self, line, GM_PLUGIN_LVGL_STYLE_LINE_OPA,
              gm_plugin_lvgl_style_number(GM_PLUGIN_LVGL_OPA_COVER));
    set_style(self, line, GM_PLUGIN_LVGL_STYLE_LINE_WIDTH,
              gm_plugin_lvgl_style_number(4));
    set_style(self, line, GM_PLUGIN_LVGL_STYLE_LINE_ROUNDED,
              gm_plugin_lvgl_style_number(1));
    return box(self, 50, 52, 4, 14, theme.primary_gray, true,
               0U, 0U, 1U) != NULL &&
           box(self, 50, 70, 4, 4, theme.primary_gray, true,
               0U, 0U, 1U) != NULL;
}

static bool render_warning(ah_renderer_t *self, const ah_view_t *view,
                           ah_theme_t theme)
{
    bool has_primary = view->primary_label != NULL;
    if (!render_warning_icon(self, theme) ||
        label(self, view->heading, 100, 48, 472, 28, false,
              theme.primary_gray, GM_PLUGIN_LVGL_LABEL_DOT,
              GM_PLUGIN_LVGL_TEXT_ALIGN_LEFT) == NULL ||
        (view->title != NULL &&
         label(self, view->title, SAFE_X, 112, SAFE_W, 42, true,
               theme.primary_gray, GM_PLUGIN_LVGL_LABEL_DOT,
               GM_PLUGIN_LVGL_TEXT_ALIGN_LEFT) == NULL) ||
        label(self, view->body, SAFE_X, view->title == NULL ? 118 : 160,
              SAFE_W, 42, false, theme.secondary_gray,
              GM_PLUGIN_LVGL_LABEL_WRAP,
              GM_PLUGIN_LVGL_TEXT_ALIGN_LEFT) == NULL ||
        label(self, view->detail, SAFE_X, view->title == NULL ? 166 : 202,
              SAFE_W, 30, false, theme.primary_gray,
              GM_PLUGIN_LVGL_LABEL_DOT,
              GM_PLUGIN_LVGL_TEXT_ALIGN_LEFT) == NULL)
        return false;
    if (has_primary) {
        if (!focus_box(self, 28, 238, 336, 66, view->primary_label,
                       theme, true) ||
            !focus_box(self, 384, 238, 188, 66, "Back", theme, false))
            return false;
    } else if (!focus_box(self, 384, 238, 188, 66, "Back", theme, true)) {
        return false;
    }
    return footer(self, view->guidance, theme.secondary_gray,
                  GM_PLUGIN_LVGL_TEXT_ALIGN_RIGHT);
}

bool ah_renderer_start(ah_renderer_t *self,
                       const gm_plugin_lvgl_api_t *ui,
                       gm_plugin_lvgl_obj_t *host_root,
                       int16_t display_width, int16_t display_height)
{
    if (self == NULL || ui == NULL || host_root == NULL ||
        display_width < AH_RENDERER_WIDTH ||
        display_height < AH_RENDERER_HEIGHT)
        return false;
    self->ui = ui;
    ui->obj_clean(host_root);
    self->canvas = ui->obj_create(host_root);
    if (self->canvas == NULL) return false;
    ui->obj_set_size(self->canvas, AH_RENDERER_WIDTH, AH_RENDERER_HEIGHT);
    ui->obj_align(self->canvas, GM_PLUGIN_LVGL_ALIGN_CENTER, 0, 0);
    style_box(self, self->canvas, 0U, true, 0U, 0U, 0U);
    return true;
}

bool ah_renderer_render(ah_renderer_t *self, const ah_view_t *view,
                        ah_theme_t theme)
{
    if (self == NULL || self->ui == NULL || self->canvas == NULL ||
        view == NULL)
        return false;
    self->ui->obj_clean(self->canvas);
    switch (view->kind) {
    case AH_VIEW_QUIET:
        return true;
    case AH_VIEW_OFFLINE:
        return render_offline(self, view, theme);
    case AH_VIEW_ATTENTION:
        return render_indicator(self, view, theme);
    case AH_VIEW_REQUEST:
        return render_request(self, view, theme);
    case AH_VIEW_ACTIONS:
        return render_actions(self, view, theme);
    case AH_VIEW_CONFIRMATION:
        return render_confirmation(self, view, theme);
    case AH_VIEW_SENDING:
        return render_sending(self, view, theme);
    case AH_VIEW_SENT:
        return render_sent(self, view, theme);
    case AH_VIEW_DELIVERY_UNKNOWN:
    case AH_VIEW_STALE:
    case AH_VIEW_REJECTED:
        return render_warning(self, view, theme);
    default:
        return false;
    }
}

bool ah_renderer_message(ah_renderer_t *self, const char *heading,
                         const char *body)
{
    ah_view_t view = {
        .kind = AH_VIEW_REJECTED,
        .heading = heading,
        .title = "Display unavailable",
        .body = body,
        .detail = "No decision was sent",
        .primary_label = NULL,
        .guidance = "BACK: DISMISS",
        .task_id = NULL,
        .revision = 0U,
        .action_count = 0U,
        .actions = {NULL, NULL},
        .focused_action = 0U,
        .selected_action = NULL,
        .retryable = false
    };
    return ah_renderer_render(self, &view,
                              ah_theme_for_state(AH_STATE_REJECTED));
}

void ah_renderer_stop(ah_renderer_t *self)
{
    if (self == NULL) return;
    self->canvas = NULL;
    self->ui = NULL;
}
