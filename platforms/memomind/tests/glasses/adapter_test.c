#include <stddef.h>

#include "agent_hud_theme.h"
#include "agent_hud_view.h"
#include "input_mapping.h"

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

static bool same(const char *left, const char *right)
{
    size_t offset = 0U;
    if (left == NULL || right == NULL) return false;
    while (left[offset] == right[offset]) {
        if (left[offset] == '\0') return true;
        ++offset;
    }
    return false;
}

#ifdef _WIN32
__declspec(dllexport)
#endif
int run_adapter_test(void)
{
    ah_model_t model;
    ah_view_t view;
    ah_event_type_t event;
    ah_theme_t theme;

    ah_model_init(&model, "adapter-test");
    if (!ah_view_build(&model, AH_MAPPING_B, AH_CONNECTIVITY_UNKNOWN, &view) ||
        view.kind != AH_VIEW_QUIET || view.title != NULL)
        return 1;
    if (!ah_view_build(&model, AH_MAPPING_B, AH_CONNECTIVITY_DISCONNECTED,
                       &view) ||
        view.kind != AH_VIEW_OFFLINE || !same(view.heading, "OFFLINE"))
        return 2;

    model.has_task = true;
    model.task.action_count = 2U;
    model.task.actions[0].label[0] = 'A';
    model.task.actions[0].label[1] = '\0';
    model.task.actions[1].label[0] = 'R';
    model.task.actions[1].label[1] = '\0';
    model.task.title[0] = 'T';
    model.task.title[1] = '\0';
    model.task.short_context[0] = 'C';
    model.task.short_context[1] = '\0';

    model.state = AH_STATE_ACTION_MENU;
    model.focused_action = 1U;
    if (!ah_view_build(&model, AH_MAPPING_B, AH_CONNECTIVITY_CONNECTED, &view) ||
        view.kind != AH_VIEW_ACTIONS || view.action_count != 2U ||
        view.focused_action != 1U || !same(view.actions[0], "A") ||
        !same(view.actions[1], "R") ||
        !same(view.guidance, "TAP: MOVE · DOUBLE: SELECT"))
        return 3;

    model.state = AH_STATE_CONFIRMATION;
    model.selected_action = 0U;
    model.task.revision = 7U;
    model.retry_review = true;
    if (!ah_view_build(&model, AH_MAPPING_A, AH_CONNECTIVITY_CONNECTED, &view) ||
        view.kind != AH_VIEW_CONFIRMATION ||
        !same(view.heading, "REVIEW RETRY") ||
        !same(view.selected_action, "A") || view.revision != 7U ||
        !same(view.guidance, "only this state may send"))
        return 4;
    model.retry_review = false;

    model.state = AH_STATE_ATTENTION;
    if (!ah_view_build(&model, AH_MAPPING_B, AH_CONNECTIVITY_CONNECTED, &view) ||
        view.kind != AH_VIEW_ATTENTION || !same(view.title, "1") ||
        !same(view.detail, "REQUEST"))
        return 11;
    model.state = AH_STATE_REQUEST;
    if (!ah_view_build(&model, AH_MAPPING_B, AH_CONNECTIVITY_CONNECTED, &view) ||
        view.kind != AH_VIEW_REQUEST || !same(view.heading, "NEEDS YOU · 1 OF 1") ||
        !same(view.title, "T") || !same(view.body, "C") ||
        !same(view.primary_label, "Open request") ||
        !same(view.guidance, "DOUBLE: OPEN · opening sends nothing"))
        return 12;
    model.state = AH_STATE_SEND;
    if (!ah_view_build(&model, AH_MAPPING_B, AH_CONNECTIVITY_CONNECTED, &view) ||
        view.kind != AH_VIEW_SENDING ||
        !same(view.body, "Waiting for gateway acceptance"))
        return 13;
    model.state = AH_STATE_ACK;
    if (!ah_view_build(&model, AH_MAPPING_B, AH_CONNECTIVITY_CONNECTED, &view) ||
        view.kind != AH_VIEW_SENT ||
        !same(view.body, "Gateway accepted this decision") ||
        !same(view.detail, "Task completion is not claimed"))
        return 14;
    model.state = AH_STATE_ERROR;
    model.retryable = true;
    if (!ah_view_build(&model, AH_MAPPING_B, AH_CONNECTIVITY_CONNECTED, &view) ||
        view.kind != AH_VIEW_DELIVERY_UNKNOWN ||
        !same(view.body, "Review before retry") ||
        !same(view.primary_label, "Review decision"))
        return 15;
    model.state = AH_STATE_REJECTED;
    if (!ah_view_build(&model, AH_MAPPING_B, AH_CONNECTIVITY_CONNECTED, &view) ||
        view.kind != AH_VIEW_REJECTED ||
        !same(view.heading, "ACTION REJECTED") ||
        !same(view.detail, "No decision was sent"))
        return 17;
    model.state = AH_STATE_STALE;
    if (!ah_view_build(&model, AH_MAPPING_B, AH_CONNECTIVITY_CONNECTED, &view) ||
        view.kind != AH_VIEW_STALE ||
        !same(view.heading, "REQUEST CHANGED") ||
        !same(view.primary_label, "Read current request") ||
        !same(view.detail, "No decision was sent"))
        return 16;

    if (!ah_map_input(AH_MAPPING_A, AH_STATE_ACTION_MENU,
                      AH_INPUT_PRIMARY_SINGLE, &event) ||
        event != AH_EVENT_ACTIVATE)
        return 5;
    if (!ah_map_input(AH_MAPPING_B, AH_STATE_ACTION_MENU,
                      AH_INPUT_PRIMARY_SINGLE, &event) ||
        event != AH_EVENT_NAVIGATE_NEXT)
        return 6;
    if (!ah_map_input(AH_MAPPING_B, AH_STATE_ACTION_MENU,
                      AH_INPUT_PRIMARY_DOUBLE, &event) ||
        event != AH_EVENT_ACTIVATE)
        return 7;
    if (!ah_map_input(AH_MAPPING_A, AH_STATE_CONFIRMATION,
                      AH_INPUT_PRIMARY_DOUBLE, &event) ||
        event != AH_EVENT_CONFIRM)
        return 8;
    if (!ah_map_input(AH_MAPPING_B, AH_STATE_CONFIRMATION,
                      AH_INPUT_HEAD_RIGHT, &event) ||
        event == AH_EVENT_CONFIRM)
        return 9;
    if (!ah_map_input(AH_MAPPING_A, AH_STATE_CONFIRMATION,
                      AH_INPUT_BACK, &event) || event != AH_EVENT_BACK)
        return 10;
    if (!ah_map_input(AH_MAPPING_B, AH_STATE_ERROR,
                      AH_INPUT_PRIMARY_DOUBLE, &event) ||
        event != AH_EVENT_REVIEW_RETRY)
        return 18;
    theme = ah_theme_for_state(AH_STATE_QUIET);
    if (theme.layout != AH_LAYOUT_BLANK || theme.border_width != 0U)
        return 19;
    theme = ah_theme_for_state(AH_STATE_ATTENTION);
    if (theme.layout != AH_LAYOUT_INDICATOR || theme.focus_border_width != 4U)
        return 20;
    theme = ah_theme_for_state(AH_STATE_CONFIRMATION);
    if (theme.layout != AH_LAYOUT_CONFIRMATION ||
        theme.focus_border_width <= theme.border_width)
        return 21;
    theme = ah_theme_for_state(AH_STATE_ERROR);
    if (theme.layout != AH_LAYOUT_WARNING || theme.border_gray == 0U)
        return 22;
    return 0;
}

#ifndef _WIN32
int main(void)
{
    return run_adapter_test();
}
#endif
