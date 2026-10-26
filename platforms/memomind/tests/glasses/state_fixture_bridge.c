#include <stddef.h>

#include "agent_hud_state.h"

#ifdef _WIN32
#define AH_EXPORT __declspec(dllexport)

/* This test DLL is deliberately linked without the Windows platform CRT. */
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
#else
#define AH_EXPORT
#endif

#define AH_FIXTURE_MAX_TRANSMISSIONS 8U

enum {
    AH_FIXTURE_FOCUS = 1,
    AH_FIXTURE_SELECT,
    AH_FIXTURE_CONFIRM,
    AH_FIXTURE_CANCEL,
    AH_FIXTURE_UPDATE,
    AH_FIXTURE_RESULT,
    AH_FIXTURE_RETRY
};

static ah_model_t fixture_model;
static ah_core_decision_t fixture_transmissions[AH_FIXTURE_MAX_TRANSMISSIONS];
static uint32_t fixture_transmission_count;
static ah_result_status_t fixture_result;

static bool same_text(const char *left, const char *right)
{
    size_t index = 0U;
    if (left == NULL || right == NULL) return false;
    do {
        if (left[index] != right[index]) return false;
        if (left[index] == '\0') return true;
        ++index;
    } while (index <= AH_CORE_MAX_ID_BYTES);
    return false;
}

static void record_effect(ah_effect_t effect)
{
    if (effect.type != AH_EFFECT_SEND_DECISION ||
        fixture_transmission_count >= AH_FIXTURE_MAX_TRANSMISSIONS)
        return;
    fixture_transmissions[fixture_transmission_count++] = effect.decision;
}

static void apply_simple(ah_event_type_t type)
{
    ah_event_t event = {.type = type};
    record_effect(ah_transition(&fixture_model, &event));
}

static void ensure_action_menu(void)
{
    if (fixture_model.state == AH_STATE_ATTENTION)
        apply_simple(AH_EVENT_OPEN);
    if (fixture_model.state == AH_STATE_REQUEST)
        apply_simple(AH_EVENT_ACTIVATE);
}

static bool focus_action(const char *action_id)
{
    uint8_t index;
    ensure_action_menu();
    if (fixture_model.state != AH_STATE_ACTION_MENU || action_id == NULL)
        return false;
    for (index = 0U; index < fixture_model.task.action_count; ++index) {
        if (same_text(fixture_model.task.actions[index].action_id, action_id)) {
            while (fixture_model.focused_action != index)
                apply_simple(AH_EVENT_NAVIGATE_NEXT);
            return true;
        }
    }
    return false;
}

AH_EXPORT void ah_fixture_reset(const char *session_id,
                                const char *task_id,
                                uint64_t revision,
                                const char *action_0_id,
                                const char *action_0_label,
                                const char *action_1_id,
                                const char *action_1_label)
{
    ah_core_task_t task = {
        .task_id = task_id,
        .revision = revision,
        .title = "Fixture task",
        .short_context = "Shared Agent HUD conformance fixture",
        .action_count = action_1_id == NULL ? 1U : 2U,
        .actions = {
            {.action_id = action_0_id, .label = action_0_label},
            {.action_id = action_1_id, .label = action_1_label}
        }
    };
    ah_event_t event = {.type = AH_EVENT_REQUEST_ARRIVED, .task = &task};
    fixture_transmission_count = 0U;
    fixture_result = AH_RESULT_NONE;
    ah_model_init(&fixture_model, session_id);
    (void)ah_transition(&fixture_model, &event);
}

static void apply_update(const char *task_id, uint64_t revision)
{
    ah_core_task_t task = {
        .task_id = task_id,
        .revision = revision,
        .title = "Fixture task",
        .short_context = "Shared Agent HUD conformance fixture",
        .action_count = fixture_model.task.action_count,
        .actions = {
            {
                .action_id = fixture_model.task.actions[0].action_id,
                .label = fixture_model.task.actions[0].label
            },
            {
                .action_id = fixture_model.task.actions[1].action_id,
                .label = fixture_model.task.actions[1].label
            }
        }
    };
    ah_event_t event = {.type = AH_EVENT_REQUEST_UPDATED, .task = &task};
    record_effect(ah_transition(&fixture_model, &event));
}

static void apply_result(const char *decision_id,
                         const char *task_id,
                         uint64_t revision,
                         ah_result_status_t status,
                         ah_result_status_t original_status)
{
    ah_result_t result = {
        .decision_id = decision_id,
        .task_id = task_id,
        .revision = revision,
        .status = status,
        .original_status = original_status,
        .retryable = status == AH_RESULT_ERROR
    };
    ah_event_t event = {.type = AH_EVENT_RESULT_RECEIVED, .result = &result};
    ah_state_t prior_state = fixture_model.state;
    record_effect(ah_transition(&fixture_model, &event));
    if (prior_state != AH_STATE_SEND || fixture_model.state == AH_STATE_SEND)
        return;
    fixture_result = status == AH_RESULT_DUPLICATE ? original_status : status;
}

AH_EXPORT void ah_fixture_apply(int type,
                                const char *identifier,
                                const char *task_id,
                                uint64_t revision,
                                int status,
                                int original_status)
{
    switch (type) {
    case AH_FIXTURE_FOCUS:
        (void)focus_action(identifier);
        break;
    case AH_FIXTURE_SELECT:
        if (focus_action(identifier)) apply_simple(AH_EVENT_ACTIVATE);
        break;
    case AH_FIXTURE_CONFIRM:
        apply_simple(AH_EVENT_CONFIRM);
        break;
    case AH_FIXTURE_CANCEL:
        apply_simple(AH_EVENT_BACK);
        break;
    case AH_FIXTURE_UPDATE:
        apply_update(task_id, revision);
        break;
    case AH_FIXTURE_RESULT:
        apply_result(identifier, task_id, revision,
                     (ah_result_status_t)status,
                     (ah_result_status_t)original_status);
        break;
    case AH_FIXTURE_RETRY:
        {
            uint32_t before = fixture_transmission_count;
            apply_simple(AH_EVENT_RETRY);
            if (fixture_transmission_count != before) fixture_result = AH_RESULT_NONE;
        }
        break;
    default:
        break;
    }
}

AH_EXPORT uint32_t ah_fixture_transmission_count(void)
{
    return fixture_transmission_count;
}

AH_EXPORT const char *ah_fixture_decision_id(uint32_t index)
{
    return index < fixture_transmission_count
        ? fixture_transmissions[index].decision_id : "";
}

AH_EXPORT const char *ah_fixture_task_id(uint32_t index)
{
    return index < fixture_transmission_count
        ? fixture_transmissions[index].task_id : "";
}

AH_EXPORT uint64_t ah_fixture_revision(uint32_t index)
{
    return index < fixture_transmission_count
        ? fixture_transmissions[index].revision : 0U;
}

AH_EXPORT const char *ah_fixture_action_id(uint32_t index)
{
    return index < fixture_transmission_count
        ? fixture_transmissions[index].action_id : "";
}

AH_EXPORT int ah_fixture_result(void)
{
    return (int)fixture_result;
}
