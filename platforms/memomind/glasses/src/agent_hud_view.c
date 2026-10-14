#include "agent_hud_view.h"

#include <stddef.h>

static void reset_view(ah_view_t *view)
{
    uint8_t index;
    view->kind = AH_VIEW_QUIET;
    view->heading = NULL;
    view->title = NULL;
    view->body = NULL;
    view->detail = NULL;
    view->primary_label = NULL;
    view->guidance = NULL;
    view->task_id = NULL;
    view->revision = 0U;
    view->action_count = 0U;
    for (index = 0U; index < AH_CORE_MAX_ACTIONS; ++index)
        view->actions[index] = NULL;
    view->focused_action = 0U;
    view->selected_action = NULL;
    view->retryable = false;
}

static bool build_actions(const ah_model_t *model,
                          ah_input_mapping_t mapping, ah_view_t *view)
{
    uint8_t index;
    if (!model->has_task || model->task.action_count == 0U ||
        model->task.action_count > AH_CORE_MAX_ACTIONS ||
        model->focused_action >= model->task.action_count)
        return false;
    view->kind = AH_VIEW_ACTIONS;
    view->heading = "CHOOSE AN ACTION";
    view->title = model->task.title;
    view->action_count = model->task.action_count;
    view->focused_action = model->focused_action;
    for (index = 0U; index < model->task.action_count; ++index)
        view->actions[index] = model->task.actions[index].label;
    view->guidance = mapping == AH_MAPPING_A
        ? "HEAD: MOVE · TAP: SELECT"
        : "TAP: MOVE · DOUBLE: SELECT";
    return true;
}

bool ah_view_build(const ah_model_t *model, ah_input_mapping_t mapping,
                   ah_connectivity_t connectivity, ah_view_t *view)
{
    if (model == NULL || view == NULL) return false;
    reset_view(view);
    if (connectivity == AH_CONNECTIVITY_DISCONNECTED &&
        model->state == AH_STATE_QUIET) {
        view->kind = AH_VIEW_OFFLINE;
        view->heading = "OFFLINE";
        view->detail = "LINK";
        return true;
    }
    switch (model->state) {
    case AH_STATE_QUIET:
        return true;
    case AH_STATE_ATTENTION:
        view->kind = AH_VIEW_ATTENTION;
        view->title = "1";
        view->detail = "REQUEST";
        return true;
    case AH_STATE_REQUEST:
        if (!model->has_task) return false;
        view->kind = AH_VIEW_REQUEST;
        view->heading = "NEEDS YOU · 1 OF 1";
        view->title = model->task.title;
        view->body = model->task.short_context;
        view->primary_label = "Open request";
        view->guidance = mapping == AH_MAPPING_A
            ? "TAP: OPEN · opening sends nothing"
            : "DOUBLE: OPEN · opening sends nothing";
        return true;
    case AH_STATE_ACTION_MENU:
        return build_actions(model, mapping, view);
    case AH_STATE_CONFIRMATION:
        if (!model->has_task ||
            model->selected_action >= model->task.action_count)
            return false;
        view->kind = AH_VIEW_CONFIRMATION;
        view->heading = model->retry_review ? "REVIEW RETRY" : "CONFIRM?";
        view->title = model->task.title;
        view->selected_action =
            model->task.actions[model->selected_action].label;
        view->task_id = model->task.task_id;
        view->revision = model->confirmation_revision != 0U
            ? model->confirmation_revision : model->task.revision;
        view->primary_label = "Confirm & send";
        view->guidance = "only this state may send";
        return true;
    case AH_STATE_SEND:
        view->kind = AH_VIEW_SENDING;
        view->heading = "SENDING";
        view->body = "Waiting for gateway acceptance";
        return true;
    case AH_STATE_ACK:
        view->kind = AH_VIEW_SENT;
        view->heading = "SENT";
        view->body = "Gateway accepted this decision";
        view->detail = "Task completion is not claimed";
        view->guidance = "BACK TO QUIET";
        return true;
    case AH_STATE_ERROR:
        view->kind = AH_VIEW_DELIVERY_UNKNOWN;
        view->heading = "DELIVERY UNKNOWN";
        view->body = model->retryable
            ? "Review before retry" : "Back to dismiss";
        view->detail = "Success was not confirmed";
        view->primary_label = model->retryable
            ? "Review decision" : NULL;
        view->guidance = model->retryable
            ? "DOUBLE: REVIEW · BACK: DISMISS" : "BACK: DISMISS";
        view->retryable = model->retryable;
        return true;
    case AH_STATE_STALE:
        view->kind = AH_VIEW_STALE;
        view->heading = "REQUEST CHANGED";
        view->title = "Read it again";
        view->body = "The revision you reviewed is no longer current.";
        view->detail = "No decision was sent";
        view->primary_label = "Read current request";
        view->guidance = "DOUBLE: READ · BACK: DISMISS";
        return true;
    case AH_STATE_REJECTED:
        view->kind = AH_VIEW_REJECTED;
        view->heading = "ACTION REJECTED";
        view->title = "Action unavailable";
        view->body = "Action is no longer offered";
        view->detail = "No decision was sent";
        view->guidance = "BACK: DISMISS";
        return true;
    default:
        return false;
    }
}
