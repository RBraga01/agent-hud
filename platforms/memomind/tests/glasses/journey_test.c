#include <stddef.h>

#include "agent_hud_state.h"
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

static ah_core_task_t request(void)
{
    ah_core_task_t task = {.task_id = "task-42"};
    task.revision = 3U;
    task.title = "Review deploy?";
    task.short_context = "Tests passed.";
    task.action_count = 2U;
    task.actions[0].action_id = "approve";
    task.actions[0].label = "Approve";
    task.actions[1].action_id = "inspect";
    task.actions[1].label = "Inspect";
    return task;
}

static ah_effect_t physical(ah_model_t *model, ah_input_mapping_t mapping,
                            ah_physical_input_t input)
{
    ah_event_type_t type;
    ah_event_t event = {.type = AH_EVENT_NONE};
    if (!ah_map_input(mapping, model->state, input, &type)) {
        ah_effect_t none = {.type = AH_EFFECT_NONE};
        return none;
    }
    event.type = type;
    return ah_transition(model, &event);
}

static int start(ah_model_t *model)
{
    ah_core_task_t task = request();
    ah_event_t event = {.type = AH_EVENT_REQUEST_ARRIVED, .task = &task};
    ah_effect_t effect;
    ah_model_init(model, "journey-session");
    effect = ah_transition(model, &event);
    return model->state == AH_STATE_ATTENTION &&
           effect.type == AH_EFFECT_NONE ? 0 : 1;
}

static ah_effect_t connection_lost(ah_model_t *model)
{
    ah_event_t event = {.type = AH_EVENT_CONNECTION_LOST};
    return ah_transition(model, &event);
}

static int ends_in(const char *text, char value)
{
    size_t length = 0U;
    while (text[length] != '\0') ++length;
    return length != 0U && text[length - 1U] == value;
}

#ifdef _WIN32
__declspec(dllexport)
#endif
int run_journey_test(void)
{
    ah_model_t model;
    ah_effect_t effect;

    if (start(&model) != 0) return 1;
    effect = physical(&model, AH_MAPPING_A, AH_INPUT_PRIMARY_SINGLE);
    if (model.state != AH_STATE_REQUEST || effect.type != AH_EFFECT_NONE)
        return 2;
    effect = physical(&model, AH_MAPPING_A, AH_INPUT_PRIMARY_SINGLE);
    if (model.state != AH_STATE_ACTION_MENU || effect.type != AH_EFFECT_NONE)
        return 3;
    effect = physical(&model, AH_MAPPING_A, AH_INPUT_HEAD_RIGHT);
    if (model.focused_action != 1U || effect.type != AH_EFFECT_NONE) return 4;
    effect = physical(&model, AH_MAPPING_A, AH_INPUT_PRIMARY_SINGLE);
    if (model.state != AH_STATE_CONFIRMATION ||
        effect.type != AH_EFFECT_NONE)
        return 5;
    effect = physical(&model, AH_MAPPING_A, AH_INPUT_HEAD_LEFT);
    if (model.state != AH_STATE_CONFIRMATION ||
        effect.type != AH_EFFECT_NONE)
        return 6;
    effect = physical(&model, AH_MAPPING_A, AH_INPUT_PRIMARY_DOUBLE);
    if (model.state != AH_STATE_SEND ||
        effect.type != AH_EFFECT_SEND_DECISION)
        return 7;

    if (start(&model) != 0) return 8;
    (void)physical(&model, AH_MAPPING_B, AH_INPUT_PRIMARY_SINGLE);
    (void)physical(&model, AH_MAPPING_B, AH_INPUT_PRIMARY_DOUBLE);
    effect = physical(&model, AH_MAPPING_B, AH_INPUT_PRIMARY_SINGLE);
    if (model.state != AH_STATE_ACTION_MENU || model.focused_action != 1U ||
        effect.type != AH_EFFECT_NONE)
        return 9;
    effect = physical(&model, AH_MAPPING_B, AH_INPUT_PRIMARY_DOUBLE);
    if (model.state != AH_STATE_CONFIRMATION ||
        effect.type != AH_EFFECT_NONE)
        return 10;
    effect = physical(&model, AH_MAPPING_B, AH_INPUT_HEAD_RIGHT);
    if (model.state != AH_STATE_CONFIRMATION ||
        effect.type != AH_EFFECT_NONE)
        return 11;

    ah_model_init(&model, "after-restart");
    if (model.state != AH_STATE_QUIET || model.has_task ||
        model.has_in_flight || model.retry_review)
        return 12;
    effect = physical(&model, AH_MAPPING_B, AH_INPUT_PRIMARY_DOUBLE);
    if (model.state != AH_STATE_QUIET || effect.type != AH_EFFECT_NONE)
        return 13;

    if (start(&model) != 0) return 14;
    (void)physical(&model, AH_MAPPING_B, AH_INPUT_PRIMARY_SINGLE);
    (void)physical(&model, AH_MAPPING_B, AH_INPUT_PRIMARY_DOUBLE);
    (void)physical(&model, AH_MAPPING_B, AH_INPUT_PRIMARY_DOUBLE);
    if (model.state != AH_STATE_CONFIRMATION) return 15;
    effect = connection_lost(&model);
    if (model.state != AH_STATE_QUIET || model.has_task || model.has_in_flight ||
        effect.type != AH_EFFECT_NONE)
        return 16;
    effect = physical(&model, AH_MAPPING_B, AH_INPUT_PRIMARY_DOUBLE);
    if (model.state != AH_STATE_QUIET || effect.type != AH_EFFECT_NONE)
        return 17;

    {
        ah_core_task_t task = request();
        ah_event_t arrived = {.type = AH_EVENT_REQUEST_ARRIVED, .task = &task};
        (void)ah_transition(&model, &arrived);
    }
    (void)physical(&model, AH_MAPPING_B, AH_INPUT_PRIMARY_SINGLE);
    (void)physical(&model, AH_MAPPING_B, AH_INPUT_PRIMARY_DOUBLE);
    (void)physical(&model, AH_MAPPING_B, AH_INPUT_PRIMARY_DOUBLE);
    effect = physical(&model, AH_MAPPING_B, AH_INPUT_PRIMARY_DOUBLE);
    if (effect.type != AH_EFFECT_SEND_DECISION ||
        !ends_in(effect.decision.decision_id, '1'))
        return 18;
    effect = connection_lost(&model);
    if (model.state != AH_STATE_QUIET || model.has_in_flight ||
        effect.type != AH_EFFECT_NONE)
        return 19;

    {
        ah_core_task_t task = request();
        ah_event_t arrived = {.type = AH_EVENT_REQUEST_ARRIVED, .task = &task};
        (void)ah_transition(&model, &arrived);
    }
    (void)physical(&model, AH_MAPPING_B, AH_INPUT_PRIMARY_SINGLE);
    (void)physical(&model, AH_MAPPING_B, AH_INPUT_PRIMARY_DOUBLE);
    (void)physical(&model, AH_MAPPING_B, AH_INPUT_PRIMARY_DOUBLE);
    effect = physical(&model, AH_MAPPING_B, AH_INPUT_PRIMARY_DOUBLE);
    if (effect.type != AH_EFFECT_SEND_DECISION ||
        !ends_in(effect.decision.decision_id, '2'))
        return 20;
    return 0;
}

#ifndef _WIN32
int main(void)
{
    return run_journey_test();
}
#endif
