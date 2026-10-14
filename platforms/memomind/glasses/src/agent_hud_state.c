#include "agent_hud_state.h"

#include <stddef.h>

static bool copy_text(char *destination, size_t capacity, const char *source)
{
    size_t index = 0U;
    if (destination == NULL || capacity == 0U || source == NULL) return false;
    while (source[index] != '\0') {
        if (index + 1U >= capacity) return false;
        destination[index] = source[index];
        ++index;
    }
    destination[index] = '\0';
    return index != 0U;
}

static bool identifier_character(char value)
{
    return (value >= 'A' && value <= 'Z') ||
           (value >= 'a' && value <= 'z') ||
           (value >= '0' && value <= '9') ||
           value == '.' || value == '_' || value == ':' || value == '-';
}

static bool copy_identifier(char *destination, size_t capacity,
                            const char *source)
{
    size_t index = 0U;
    if (destination == NULL || capacity == 0U || source == NULL) return false;
    while (source[index] != '\0') {
        if (index + 1U >= capacity || !identifier_character(source[index]))
            return false;
        destination[index] = source[index];
        ++index;
    }
    destination[index] = '\0';
    return index != 0U;
}

static bool copy_optional_text(char *destination, size_t capacity,
                               const char *source)
{
    size_t index = 0U;
    if (destination == NULL || capacity == 0U) return false;
    if (source == NULL) {
        destination[0] = '\0';
        return true;
    }
    while (source[index] != '\0') {
        if (index + 1U >= capacity) return false;
        destination[index] = source[index];
        ++index;
    }
    destination[index] = '\0';
    return true;
}

static bool same_text(const char *left, const char *right)
{
    size_t index = 0U;
    if (left == NULL || right == NULL) return false;
    while (index <= AH_CORE_MAX_ID_BYTES) {
        if (left[index] != right[index]) return false;
        if (left[index] == '\0') return true;
        ++index;
    }
    return false;
}

static ah_effect_t no_effect(void)
{
    ah_effect_t effect = {.type = AH_EFFECT_NONE};
    return effect;
}

static bool text_fits(const char *source, size_t maximum, bool required)
{
    size_t index = 0U;
    if (source == NULL) return !required;
    while (source[index] != '\0') {
        if (index >= maximum) return false;
        ++index;
    }
    return !required || index != 0U;
}

static bool identifier_valid(const char *source)
{
    size_t index = 0U;
    if (source == NULL) return false;
    while (source[index] != '\0') {
        if (index >= AH_CORE_MAX_ID_BYTES ||
            !identifier_character(source[index]))
            return false;
        ++index;
    }
    return index != 0U;
}

static bool task_valid(const ah_core_task_t *source)
{
    uint8_t index;
    if (source == NULL || !identifier_valid(source->task_id) ||
        source->revision > AH_CORE_MAX_REVISION ||
        !text_fits(source->title, AH_CORE_MAX_TITLE_BYTES, false) ||
        !text_fits(source->short_context, AH_CORE_MAX_CONTEXT_BYTES, false) ||
        source->action_count == 0U ||
        source->action_count > AH_CORE_MAX_ACTIONS)
        return false;
    for (index = 0U; index < source->action_count; ++index) {
        uint8_t previous;
        if (!identifier_valid(source->actions[index].action_id) ||
            !text_fits(source->actions[index].label,
                       AH_CORE_MAX_LABEL_BYTES, true))
            return false;
        for (previous = 0U; previous < index; ++previous)
            if (same_text(source->actions[previous].action_id,
                          source->actions[index].action_id))
                return false;
    }
    return true;
}

static void copy_task(ah_task_snapshot_t *destination,
                      const ah_core_task_t *source)
{
    uint8_t index;
    (void)copy_identifier(destination->task_id, sizeof(destination->task_id),
                          source->task_id);
    destination->revision = source->revision;
    (void)copy_optional_text(destination->title, sizeof(destination->title),
                             source->title);
    (void)copy_optional_text(destination->short_context,
                             sizeof(destination->short_context),
                             source->short_context);
    destination->action_count = source->action_count;
    for (index = 0U; index < source->action_count; ++index) {
        (void)copy_identifier(destination->actions[index].action_id,
                              sizeof(destination->actions[index].action_id),
                              source->actions[index].action_id);
        (void)copy_text(destination->actions[index].label,
                        sizeof(destination->actions[index].label),
                        source->actions[index].label);
    }
}

static void append_sequence(char *destination, size_t capacity,
                            const char *session_id, uint32_t sequence)
{
    char digits[10];
    size_t length = 0U;
    size_t digit_count = 0U;
    uint32_t value = sequence;
    while (session_id[length] != '\0' && length + 1U < capacity) {
        destination[length] = session_id[length];
        ++length;
    }
    if (length + 2U >= capacity) {
        destination[0] = '\0';
        return;
    }
    destination[length++] = ':';
    do {
        digits[digit_count++] = (char)('0' + value % 10U);
        value /= 10U;
    } while (value != 0U && digit_count < sizeof(digits));
    if (length + digit_count >= capacity) {
        destination[0] = '\0';
        return;
    }
    while (digit_count != 0U)
        destination[length++] = digits[--digit_count];
    destination[length] = '\0';
}

static bool result_matches(const ah_model_t *model, const ah_result_t *result)
{
    return model->has_in_flight && result != NULL &&
           same_text(model->in_flight.decision_id, result->decision_id) &&
           same_text(model->in_flight.task_id, result->task_id) &&
           model->in_flight.revision == result->revision;
}

static ah_result_status_t effective_status(const ah_result_t *result)
{
    if (result->status == AH_RESULT_DUPLICATE) {
        if (result->original_status == AH_RESULT_ACCEPTED ||
            result->original_status == AH_RESULT_STALE ||
            result->original_status == AH_RESULT_INVALID_ACTION)
            return result->original_status;
        return AH_RESULT_NONE;
    }
    return result->status;
}

static bool task_matches(const ah_model_t *model, const char *task_id)
{
    return model->has_task && task_id != NULL &&
           same_text(model->task.task_id, task_id);
}

static void clear_transient_state(ah_model_t *model)
{
    uint8_t index;
    model->state = AH_STATE_QUIET;
    model->has_task = false;
    model->task.task_id[0] = '\0';
    model->task.revision = 0U;
    model->task.title[0] = '\0';
    model->task.short_context[0] = '\0';
    model->task.action_count = 0U;
    for (index = 0U; index < AH_CORE_MAX_ACTIONS; ++index) {
        model->task.actions[index].action_id[0] = '\0';
        model->task.actions[index].label[0] = '\0';
    }
    model->focused_action = 0U;
    model->selected_action = 0U;
    model->confirmation_revision = 0U;
    model->has_in_flight = false;
    model->retryable = false;
    model->retry_review = false;
    model->in_flight.decision_id[0] = '\0';
    model->in_flight.task_id[0] = '\0';
    model->in_flight.revision = 0U;
    model->in_flight.action_id[0] = '\0';
}

void ah_model_init(ah_model_t *model, const char *session_id)
{
    if (model == NULL) return;
    clear_transient_state(model);
    model->next_decision_sequence = 1U;
    if (!copy_identifier(model->session_id, sizeof(model->session_id) - 11U,
                         session_id))
        (void)copy_identifier(model->session_id, sizeof(model->session_id),
                              "session");
}

static ah_effect_t receive_task(ah_model_t *model,
                                const ah_core_task_t *task,
                                bool update)
{
    if (!task_valid(task)) return no_effect();
    if (model->has_task && same_text(model->task.task_id, task->task_id)) {
        if (task->revision < model->task.revision) return no_effect();
        if (task->revision == model->task.revision) return no_effect();
        copy_task(&model->task, task);
        if (model->state == AH_STATE_SEND) return no_effect();
        if (model->state == AH_STATE_CONFIRMATION) {
            model->state = AH_STATE_STALE;
            model->retry_review = false;
            return no_effect();
        }
        model->state = AH_STATE_REQUEST;
        model->focused_action = 0U;
        model->selected_action = 0U;
        model->retry_review = false;
        return no_effect();
    }
    copy_task(&model->task, task);
    model->has_task = true;
    model->focused_action = 0U;
    model->selected_action = 0U;
    model->retry_review = false;
    if (model->state != AH_STATE_SEND)
        model->state = update ? AH_STATE_REQUEST : AH_STATE_ATTENTION;
    return no_effect();
}

static ah_effect_t confirm(ah_model_t *model)
{
    ah_effect_t effect = {.type = AH_EFFECT_NONE};
    if (model->state != AH_STATE_CONFIRMATION || !model->has_task ||
        model->selected_action >= model->task.action_count ||
        model->confirmation_revision != model->task.revision)
        return no_effect();
    if (model->retry_review) {
        if (!model->has_in_flight ||
            model->in_flight.revision != model->task.revision ||
            !same_text(model->in_flight.task_id, model->task.task_id) ||
            !same_text(model->in_flight.action_id,
                       model->task.actions[model->selected_action].action_id)) {
            model->state = AH_STATE_STALE;
            model->retry_review = false;
            return no_effect();
        }
        model->state = AH_STATE_SEND;
        model->retryable = false;
        model->retry_review = false;
        effect.type = AH_EFFECT_SEND_DECISION;
        effect.decision = model->in_flight;
        return effect;
    }
    model->in_flight.revision = model->task.revision;
    if (!copy_identifier(model->in_flight.task_id,
                         sizeof(model->in_flight.task_id),
                         model->task.task_id) ||
        !copy_identifier(model->in_flight.action_id,
                         sizeof(model->in_flight.action_id),
                         model->task.actions[model->selected_action].action_id))
        return no_effect();
    append_sequence(model->in_flight.decision_id,
                    sizeof(model->in_flight.decision_id),
                    model->session_id, model->next_decision_sequence++);
    if (model->in_flight.decision_id[0] == '\0') return no_effect();
    model->has_in_flight = true;
    model->retryable = false;
    model->retry_review = false;
    model->state = AH_STATE_SEND;
    effect.type = AH_EFFECT_SEND_DECISION;
    effect.decision = model->in_flight;
    return effect;
}

static ah_effect_t receive_result(ah_model_t *model,
                                  const ah_result_t *result)
{
    ah_result_status_t status;
    if (model->state != AH_STATE_SEND || !result_matches(model, result))
        return no_effect();
    status = effective_status(result);
    if (status == AH_RESULT_NONE) return no_effect();
    model->retry_review = false;
    if (status == AH_RESULT_ACCEPTED) {
        model->state = AH_STATE_ACK;
        model->retryable = false;
    } else if (status == AH_RESULT_STALE) {
        model->state = AH_STATE_STALE;
        model->retryable = false;
    } else if (status == AH_RESULT_INVALID_ACTION) {
        model->state = AH_STATE_REJECTED;
        model->retryable = false;
    } else {
        model->state = AH_STATE_ERROR;
        model->retryable = status == AH_RESULT_ERROR && result->retryable;
    }
    return no_effect();
}

ah_effect_t ah_transition(ah_model_t *model, const ah_event_t *event)
{
    ah_effect_t effect;
    if (model == NULL || event == NULL) return no_effect();
    switch (event->type) {
    case AH_EVENT_REQUEST_ARRIVED:
        return receive_task(model, event->task, false);
    case AH_EVENT_REQUEST_UPDATED:
        return receive_task(model, event->task, true);
    case AH_EVENT_REQUEST_REMOVED:
        if (model->state != AH_STATE_SEND && task_matches(model, event->task_id)) {
            model->has_task = false;
            model->state = AH_STATE_QUIET;
            model->retry_review = false;
        }
        return no_effect();
    case AH_EVENT_CONNECTION_LOST:
        clear_transient_state(model);
        return no_effect();
    case AH_EVENT_NAVIGATE_NEXT:
    case AH_EVENT_NAVIGATE_PREVIOUS:
        if (model->state == AH_STATE_ACTION_MENU &&
            model->task.action_count != 0U) {
            if (event->type == AH_EVENT_NAVIGATE_NEXT)
                model->focused_action = (uint8_t)(
                    (model->focused_action + 1U) % model->task.action_count);
            else
                model->focused_action = model->focused_action == 0U
                    ? (uint8_t)(model->task.action_count - 1U)
                    : (uint8_t)(model->focused_action - 1U);
        }
        return no_effect();
    case AH_EVENT_OPEN:
        if ((model->state == AH_STATE_ATTENTION ||
             model->state == AH_STATE_STALE) && model->has_task)
            model->state = AH_STATE_REQUEST;
        return no_effect();
    case AH_EVENT_ACTIVATE:
        if (model->state == AH_STATE_REQUEST && model->has_task) {
            model->focused_action = 0U;
            model->state = AH_STATE_ACTION_MENU;
        } else if (model->state == AH_STATE_ACTION_MENU && model->has_task &&
                   model->focused_action < model->task.action_count) {
            model->selected_action = model->focused_action;
            model->confirmation_revision = model->task.revision;
            model->retry_review = false;
            model->state = AH_STATE_CONFIRMATION;
        }
        return no_effect();
    case AH_EVENT_BACK:
        if (model->state == AH_STATE_ATTENTION)
            model->state = AH_STATE_QUIET;
        else if (model->state == AH_STATE_REQUEST)
            model->state = AH_STATE_ATTENTION;
        else if (model->state == AH_STATE_ACTION_MENU)
            model->state = AH_STATE_REQUEST;
        else if (model->state == AH_STATE_CONFIRMATION) {
            model->retry_review = false;
            model->state = AH_STATE_ACTION_MENU;
        }
        else if (model->state == AH_STATE_ACK ||
                 model->state == AH_STATE_ERROR ||
                 model->state == AH_STATE_REJECTED) {
            model->state = AH_STATE_QUIET;
            model->retry_review = false;
        }
        return no_effect();
    case AH_EVENT_CONFIRM:
        return confirm(model);
    case AH_EVENT_RESULT_RECEIVED:
        return receive_result(model, event->result);
    case AH_EVENT_REVIEW_RETRY:
        if (model->state == AH_STATE_ERROR && model->has_in_flight &&
            model->retryable) {
            uint8_t index;
            if (!model->has_task ||
                model->in_flight.revision != model->task.revision ||
                !same_text(model->in_flight.task_id, model->task.task_id)) {
                model->state = AH_STATE_STALE;
                model->retryable = false;
                return no_effect();
            }
            for (index = 0U; index < model->task.action_count; ++index) {
                if (same_text(model->in_flight.action_id,
                              model->task.actions[index].action_id)) {
                    model->selected_action = index;
                    model->confirmation_revision = model->task.revision;
                    model->retry_review = true;
                    model->state = AH_STATE_CONFIRMATION;
                    return no_effect();
                }
            }
            model->state = AH_STATE_STALE;
            model->retryable = false;
        }
        return no_effect();
    case AH_EVENT_RETRY:
        if (model->state == AH_STATE_ERROR && model->has_in_flight &&
            model->retryable) {
            model->state = AH_STATE_SEND;
            model->retry_review = false;
            effect.type = AH_EFFECT_SEND_DECISION;
            effect.decision = model->in_flight;
            return effect;
        }
        return no_effect();
    case AH_EVENT_NONE:
    default:
        return no_effect();
    }
}
