#include <stddef.h>

#include "agent_hud_state.h"

#ifdef _WIN32
/* The Windows CI path links this tiny test DLL without the platform CRT. */
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

static ah_core_task_t task(uint32_t revision)
{
    ah_core_task_t value = {.task_id = NULL};
    value.task_id = "task-1";
    value.revision = revision;
    value.title = "Deploy preview";
    value.short_context = "Agent needs a decision";
    value.action_count = 2U;
    value.actions[0].action_id = "approve";
    value.actions[0].label = "Approve";
    value.actions[1].action_id = "reject";
    value.actions[1].label = "Reject";
    return value;
}

static ah_event_t event(ah_event_type_t type)
{
    ah_event_t value = {.type = AH_EVENT_NONE};
    value.type = type;
    return value;
}

static int reach_confirmation(ah_model_t *model)
{
    ah_event_t input;
    ah_effect_t effect;
    ah_core_task_t request = task(3U);

    ah_model_init(model, "m2-session");
    input = event(AH_EVENT_REQUEST_ARRIVED);
    input.task = &request;
    effect = ah_transition(model, &input);
    if (model->state != AH_STATE_ATTENTION || effect.type != AH_EFFECT_NONE)
        return 1;
    input = event(AH_EVENT_OPEN);
    effect = ah_transition(model, &input);
    if (model->state != AH_STATE_REQUEST || effect.type != AH_EFFECT_NONE)
        return 2;
    input = event(AH_EVENT_ACTIVATE);
    effect = ah_transition(model, &input);
    if (model->state != AH_STATE_ACTION_MENU || effect.type != AH_EFFECT_NONE)
        return 3;
    input = event(AH_EVENT_ACTIVATE);
    effect = ah_transition(model, &input);
    if (model->state != AH_STATE_CONFIRMATION || effect.type != AH_EFFECT_NONE)
        return 4;
    return 0;
}

#ifdef _WIN32
__declspec(dllexport)
#endif
int run_state_test(void)
{
    ah_model_t model;
    ah_event_t input;
    ah_effect_t effect;
    ah_core_task_t updated;
    ah_result_t result = {.decision_id = NULL};
    ah_core_task_t zero_revision_task = {.task_id = NULL};
    char maximum_task_id[129];
    size_t index;
    int status;

    status = reach_confirmation(&model);
    if (status != 0) return status;

    input = event(AH_EVENT_NAVIGATE_NEXT);
    effect = ah_transition(&model, &input);
    if (model.state != AH_STATE_CONFIRMATION ||
        effect.type != AH_EFFECT_NONE)
        return 10;

    input = event(AH_EVENT_BACK);
    effect = ah_transition(&model, &input);
    if (model.state != AH_STATE_ACTION_MENU ||
        effect.type != AH_EFFECT_NONE)
        return 11;

    input = event(AH_EVENT_NAVIGATE_NEXT);
    effect = ah_transition(&model, &input);
    if (model.focused_action != 1U || effect.type != AH_EFFECT_NONE)
        return 12;

    input = event(AH_EVENT_ACTIVATE);
    effect = ah_transition(&model, &input);
    if (model.state != AH_STATE_CONFIRMATION ||
        effect.type != AH_EFFECT_NONE)
        return 13;

    input = event(AH_EVENT_CONFIRM);
    effect = ah_transition(&model, &input);
    if (model.state != AH_STATE_SEND || effect.type != AH_EFFECT_SEND_DECISION)
        return 14;
    if (effect.decision.revision != 3U ||
        effect.decision.action_id[0] != 'r')
        return 15;

    input = event(AH_EVENT_CONFIRM);
    effect = ah_transition(&model, &input);
    if (model.state != AH_STATE_SEND || effect.type != AH_EFFECT_NONE)
        return 16;

    result.decision_id = effect.decision.decision_id;
    result.task_id = "task-1";
    result.revision = 3U;
    result.status = AH_RESULT_ACCEPTED;
    input = event(AH_EVENT_RESULT_RECEIVED);
    input.result = &result;
    effect = ah_transition(&model, &input);
    if (model.state != AH_STATE_SEND || effect.type != AH_EFFECT_NONE)
        return 17;

    result.decision_id = model.in_flight.decision_id;
    input.result = &result;
    effect = ah_transition(&model, &input);
    if (model.state != AH_STATE_ACK || effect.type != AH_EFFECT_NONE)
        return 18;

    status = reach_confirmation(&model);
    if (status != 0) return 19 + status;
    input = event(AH_EVENT_CONFIRM);
    effect = ah_transition(&model, &input);
    if (effect.type != AH_EFFECT_SEND_DECISION) return 24;
    result.decision_id = model.in_flight.decision_id;
    result.task_id = "task-1";
    result.revision = 3U;
    result.status = AH_RESULT_INVALID_ACTION;
    result.original_status = AH_RESULT_NONE;
    input = event(AH_EVENT_RESULT_RECEIVED);
    input.result = &result;
    effect = ah_transition(&model, &input);
    if (model.state != AH_STATE_REJECTED || effect.type != AH_EFFECT_NONE)
        return 25;

    status = reach_confirmation(&model);
    if (status != 0) return 30 + status;
    updated = task(4U);
    input = event(AH_EVENT_REQUEST_UPDATED);
    input.task = &updated;
    effect = ah_transition(&model, &input);
    if (model.state != AH_STATE_STALE || effect.type != AH_EFFECT_NONE)
        return 35;
    input = event(AH_EVENT_CONFIRM);
    effect = ah_transition(&model, &input);
    if (effect.type != AH_EFFECT_NONE) return 36;

    status = reach_confirmation(&model);
    if (status != 0) return 40 + status;
    input = event(AH_EVENT_REQUEST_REMOVED);
    input.task_id = "task-1";
    effect = ah_transition(&model, &input);
    if (model.state != AH_STATE_QUIET || effect.type != AH_EFFECT_NONE)
        return 45;

    status = reach_confirmation(&model);
    if (status != 0) return 50 + status;
    input = event(AH_EVENT_CONFIRM);
    effect = ah_transition(&model, &input);
    if (effect.type != AH_EFFECT_SEND_DECISION) return 55;
    result.decision_id = model.in_flight.decision_id;
    result.task_id = "task-1";
    result.revision = 3U;
    result.status = AH_RESULT_ERROR;
    result.retryable = true;
    input = event(AH_EVENT_RESULT_RECEIVED);
    input.result = &result;
    effect = ah_transition(&model, &input);
    if (model.state != AH_STATE_ERROR || effect.type != AH_EFFECT_NONE)
        return 56;
    input = event(AH_EVENT_REVIEW_RETRY);
    effect = ah_transition(&model, &input);
    if (model.state != AH_STATE_CONFIRMATION || effect.type != AH_EFFECT_NONE)
        return 57;
    input = event(AH_EVENT_CONFIRM);
    effect = ah_transition(&model, &input);
    if (model.state != AH_STATE_SEND ||
        effect.type != AH_EFFECT_SEND_DECISION ||
        effect.decision.revision != model.in_flight.revision ||
        effect.decision.decision_id[0] != model.in_flight.decision_id[0])
        return 58;

    status = reach_confirmation(&model);
    if (status != 0) return 60 + status;
    input = event(AH_EVENT_CONFIRM);
    effect = ah_transition(&model, &input);
    if (effect.type != AH_EFFECT_SEND_DECISION) return 65;
    updated = task(4U);
    input = event(AH_EVENT_REQUEST_UPDATED);
    input.task = &updated;
    (void)ah_transition(&model, &input);
    result.decision_id = model.in_flight.decision_id;
    result.task_id = "task-1";
    result.revision = 3U;
    result.status = AH_RESULT_ERROR;
    result.original_status = AH_RESULT_NONE;
    result.retryable = true;
    input = event(AH_EVENT_RESULT_RECEIVED);
    input.result = &result;
    (void)ah_transition(&model, &input);
    input = event(AH_EVENT_REVIEW_RETRY);
    effect = ah_transition(&model, &input);
    if (model.state != AH_STATE_STALE || effect.type != AH_EFFECT_NONE)
        return 66;

    for (index = 0U; index < 128U; ++index) maximum_task_id[index] = 'a';
    maximum_task_id[128] = '\0';
    zero_revision_task.task_id = maximum_task_id;
    zero_revision_task.revision = 0U;
    zero_revision_task.title = NULL;
    zero_revision_task.short_context = NULL;
    zero_revision_task.action_count = 1U;
    zero_revision_task.actions[0].action_id = "approve";
    zero_revision_task.actions[0].label = "Approve";
    ah_model_init(&model, "schema-session");
    input = event(AH_EVENT_REQUEST_ARRIVED);
    input.task = &zero_revision_task;
    effect = ah_transition(&model, &input);
    if (model.state != AH_STATE_ATTENTION || effect.type != AH_EFFECT_NONE)
        return 70;
    input = event(AH_EVENT_OPEN);
    (void)ah_transition(&model, &input);
    input = event(AH_EVENT_ACTIVATE);
    (void)ah_transition(&model, &input);
    (void)ah_transition(&model, &input);
    input = event(AH_EVENT_CONFIRM);
    effect = ah_transition(&model, &input);
    if (effect.type != AH_EFFECT_SEND_DECISION ||
        effect.decision.revision != 0U ||
        effect.decision.task_id[127] != 'a' ||
        effect.decision.task_id[128] != '\0')
        return 71;
    result.decision_id = model.in_flight.decision_id;
    result.task_id = maximum_task_id;
    result.revision = 0U;
    result.status = AH_RESULT_ACCEPTED;
    result.original_status = AH_RESULT_NONE;
    result.retryable = false;
    input = event(AH_EVENT_RESULT_RECEIVED);
    input.result = &result;
    (void)ah_transition(&model, &input);
    if (model.state != AH_STATE_ACK) return 72;

    zero_revision_task.revision = 1U;
    zero_revision_task.task_id = "bad id";
    ah_model_init(&model, "schema-session");
    input = event(AH_EVENT_REQUEST_ARRIVED);
    input.task = &zero_revision_task;
    (void)ah_transition(&model, &input);
    if (model.state != AH_STATE_QUIET) return 73;

    zero_revision_task.task_id = "task-duplicate-actions";
    zero_revision_task.action_count = 2U;
    zero_revision_task.actions[1].action_id = "approve";
    zero_revision_task.actions[1].label = "Also approve";
    (void)ah_transition(&model, &input);
    if (model.state != AH_STATE_QUIET) return 74;

    zero_revision_task.action_count = 1U;
    zero_revision_task.revision = UINT64_C(9007199254740992);
    (void)ah_transition(&model, &input);
    if (model.state != AH_STATE_QUIET) return 75;

    return 0;
}

#ifndef _WIN32
int main(void)
{
    return run_state_test();
}
#endif
