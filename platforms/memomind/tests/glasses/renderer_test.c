#include <stddef.h>
#include <stdint.h>

#include "agent_hud_renderer.h"

#ifdef _WIN32
void *memcpy(void *destination, const void *source, size_t count)
{
    unsigned char *output = (unsigned char *)destination;
    const unsigned char *input = (const unsigned char *)source;
    size_t index;
    for (index = 0U; index < count; ++index) output[index] = input[index];
    return destination;
}

void *memset(void *destination, int value, size_t count)
{
    unsigned char *output = (unsigned char *)destination;
    size_t index;
    for (index = 0U; index < count; ++index)
        output[index] = (unsigned char)value;
    return destination;
}

void __chkstk(void)
{
}
#endif

typedef struct {
    uint16_t objects;
    uint16_t labels;
    uint16_t lines;
    uint16_t centered_texts;
    uint8_t widest_border;
    bool saw_primary;
    bool saw_back;
    bool saw_action_a;
    bool saw_action_b;
    bool saw_identity;
    bool saw_warning_mark_label;
} render_probe_t;

static render_probe_t probe;
static uintptr_t next_object = 2U;

static bool same(const char *left, const char *right)
{
    size_t offset = 0U;
    while (left[offset] == right[offset]) {
        if (left[offset] == '\0') return true;
        ++offset;
    }
    return false;
}

static bool contains(const char *text, const char *needle)
{
    size_t start;
    size_t offset;
    for (start = 0U; text[start] != '\0'; ++start) {
        offset = 0U;
        while (needle[offset] != '\0' &&
               text[start + offset] == needle[offset])
            ++offset;
        if (needle[offset] == '\0') return true;
    }
    return false;
}

static gm_plugin_lvgl_obj_t *new_object(void)
{
    return (gm_plugin_lvgl_obj_t *)next_object++;
}

static gm_plugin_lvgl_obj_t *fake_obj_create(gm_plugin_lvgl_obj_t *parent)
{
    (void)parent;
    ++probe.objects;
    return new_object();
}

static gm_plugin_lvgl_obj_t *fake_label_create(gm_plugin_lvgl_obj_t *parent)
{
    (void)parent;
    ++probe.labels;
    return new_object();
}

static gm_plugin_lvgl_obj_t *fake_line_create(gm_plugin_lvgl_obj_t *parent)
{
    (void)parent;
    ++probe.lines;
    return new_object();
}

static void fake_noop_object(gm_plugin_lvgl_obj_t *object)
{
    (void)object;
}

static void fake_set_pos(gm_plugin_lvgl_obj_t *object,
                         gm_plugin_lvgl_coord_t x,
                         gm_plugin_lvgl_coord_t y)
{
    (void)object;
    (void)x;
    (void)y;
}

static void fake_set_size(gm_plugin_lvgl_obj_t *object,
                          gm_plugin_lvgl_coord_t width,
                          gm_plugin_lvgl_coord_t height)
{
    (void)object;
    (void)width;
    (void)height;
}

static void fake_align(gm_plugin_lvgl_obj_t *object,
                       gm_plugin_lvgl_align_t alignment,
                       gm_plugin_lvgl_coord_t x,
                       gm_plugin_lvgl_coord_t y)
{
    (void)object;
    (void)alignment;
    (void)x;
    (void)y;
}

static void fake_flag(gm_plugin_lvgl_obj_t *object,
                      gm_plugin_lvgl_flag_t flag)
{
    (void)object;
    (void)flag;
}

static void fake_style(gm_plugin_lvgl_obj_t *object,
                       gm_plugin_lvgl_style_prop_t property,
                       gm_plugin_lvgl_style_value_t value,
                       gm_plugin_lvgl_selector_t selector)
{
    (void)object;
    (void)selector;
    if (property == GM_PLUGIN_LVGL_STYLE_BORDER_WIDTH &&
        value.num > probe.widest_border)
        probe.widest_border = (uint8_t)value.num;
    if (property == GM_PLUGIN_LVGL_STYLE_TEXT_ALIGN &&
        value.num == GM_PLUGIN_LVGL_TEXT_ALIGN_CENTER)
        ++probe.centered_texts;
}

static void fake_label_text(gm_plugin_lvgl_obj_t *label, const char *text)
{
    (void)label;
    if (same(text, "Open request") || same(text, "Confirm & send"))
        probe.saw_primary = true;
    if (same(text, "Back")) probe.saw_back = true;
    if (same(text, "Approve")) probe.saw_action_a = true;
    if (same(text, "Revise")) probe.saw_action_b = true;
    if (contains(text, "Task task-42") && contains(text, "revision 7"))
        probe.saw_identity = true;
    if (same(text, "!")) probe.saw_warning_mark_label = true;
}

static void fake_label_mode(gm_plugin_lvgl_obj_t *label,
                            gm_plugin_lvgl_label_mode_t mode)
{
    (void)label;
    (void)mode;
}

static void fake_line_points(gm_plugin_lvgl_obj_t *line,
                             const gm_plugin_lvgl_point_t *points,
                             uint16_t point_count)
{
    (void)line;
    (void)points;
    (void)point_count;
}

static void clear_probe(void)
{
    probe.objects = 0U;
    probe.labels = 0U;
    probe.lines = 0U;
    probe.centered_texts = 0U;
    probe.widest_border = 0U;
    probe.saw_primary = false;
    probe.saw_back = false;
    probe.saw_action_a = false;
    probe.saw_action_b = false;
    probe.saw_identity = false;
    probe.saw_warning_mark_label = false;
}

#ifdef _WIN32
__declspec(dllexport)
#endif
int run_renderer_test(void)
{
    gm_plugin_lvgl_api_t ui = {
        .obj_create = fake_obj_create,
        .obj_clean = fake_noop_object,
        .obj_set_pos = fake_set_pos,
        .obj_set_size = fake_set_size,
        .obj_align = fake_align,
        .obj_clear_flag = fake_flag,
        .style_set = fake_style,
        .label_create = fake_label_create,
        .label_set_text = fake_label_text,
        .label_set_long_mode = fake_label_mode,
        .line_create = fake_line_create,
        .line_set_points = fake_line_points,
        .font_default = (const gm_plugin_lvgl_font_t *)(uintptr_t)1U,
        .font_large = (const gm_plugin_lvgl_font_t *)(uintptr_t)2U
    };
    ah_renderer_t renderer;
    ah_theme_t theme = ah_theme_for_state(AH_STATE_REQUEST);
    ah_view_t request = {
        .kind = AH_VIEW_REQUEST,
        .heading = "NEEDS YOU · 1 OF 1",
        .title = "Choose the next step",
        .body = "The agent can continue or return for revision.",
        .primary_label = "Open request",
        .guidance = "DOUBLE: OPEN · opening sends nothing"
    };
    ah_view_t actions = {
        .kind = AH_VIEW_ACTIONS,
        .heading = "CHOOSE AN ACTION",
        .action_count = 2U,
        .actions = {"Approve", "Revise"},
        .focused_action = 0U,
        .guidance = "TAP: MOVE · DOUBLE: SELECT"
    };
    ah_view_t confirmation = {
        .kind = AH_VIEW_CONFIRMATION,
        .heading = "CONFIRM?",
        .selected_action = "Approve",
        .primary_label = "Confirm & send",
        .guidance = "only this state may send",
        .task_id = "task-42",
        .revision = 7U
    };
    ah_view_t sent = {
        .kind = AH_VIEW_SENT,
        .heading = "SENT",
        .body = "Gateway accepted this decision",
        .detail = "Task completion is not claimed",
        .guidance = "BACK TO QUIET"
    };
    ah_view_t stale = {
        .kind = AH_VIEW_STALE,
        .heading = "REQUEST CHANGED",
        .title = "Read it again",
        .body = "The revision you reviewed is no longer current.",
        .detail = "No decision was sent",
        .primary_label = "Read current request",
        .guidance = "DOUBLE: READ · BACK: DISMISS"
    };

    clear_probe();
    if (!ah_renderer_start(&renderer, &ui,
                           (gm_plugin_lvgl_obj_t *)(uintptr_t)1U,
                           600, 350))
        return 1;
    clear_probe();
    if (!ah_renderer_render(&renderer, &request, theme) ||
        probe.objects < 2U || probe.labels < 4U ||
        probe.widest_border != 4U || !probe.saw_primary ||
        probe.centered_texts != 1U)
        return 2;
    clear_probe();
    if (!ah_renderer_render(&renderer, &actions,
                            ah_theme_for_state(AH_STATE_ACTION_MENU)) ||
        probe.objects < 4U || !probe.saw_action_a || !probe.saw_action_b ||
        !probe.saw_back || probe.widest_border != 4U ||
        probe.centered_texts != 3U)
        return 3;
    clear_probe();
    if (!ah_renderer_render(&renderer, &confirmation,
                            ah_theme_for_state(AH_STATE_CONFIRMATION)) ||
        probe.objects < 5U || !probe.saw_primary || !probe.saw_back ||
        !probe.saw_identity || probe.widest_border != 4U ||
        probe.centered_texts != 2U)
        return 4;
    clear_probe();
    if (!ah_renderer_render(&renderer, &stale,
                            ah_theme_for_state(AH_STATE_STALE)) ||
        probe.lines != 1U || probe.saw_warning_mark_label ||
        probe.centered_texts != 2U)
        return 6;
    clear_probe();
    if (!ah_renderer_render(&renderer, &sent,
                            ah_theme_for_state(AH_STATE_ACK)) ||
        probe.lines != 1U || probe.objects < 1U)
        return 5;
    return 0;
}

#ifndef _WIN32
int main(void)
{
    return run_renderer_test();
}
#endif
