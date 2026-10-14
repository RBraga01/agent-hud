#ifndef AGENT_HUD_MEMOMIND_VIEW_H
#define AGENT_HUD_MEMOMIND_VIEW_H

#include "agent_hud_state.h"
#include "input_mapping.h"

typedef enum {
    AH_VIEW_QUIET = 0,
    AH_VIEW_OFFLINE,
    AH_VIEW_ATTENTION,
    AH_VIEW_REQUEST,
    AH_VIEW_ACTIONS,
    AH_VIEW_CONFIRMATION,
    AH_VIEW_SENDING,
    AH_VIEW_SENT,
    AH_VIEW_DELIVERY_UNKNOWN,
    AH_VIEW_STALE,
    AH_VIEW_REJECTED
} ah_view_kind_t;

typedef struct {
    ah_view_kind_t kind;
    const char *heading;
    const char *title;
    const char *body;
    const char *detail;
    const char *primary_label;
    const char *guidance;
    const char *task_id;
    uint64_t revision;
    uint8_t action_count;
    const char *actions[AH_CORE_MAX_ACTIONS];
    uint8_t focused_action;
    const char *selected_action;
    bool retryable;
} ah_view_t;

typedef enum {
    AH_CONNECTIVITY_UNKNOWN = 0,
    AH_CONNECTIVITY_CONNECTED,
    AH_CONNECTIVITY_DISCONNECTED
} ah_connectivity_t;

bool ah_view_build(const ah_model_t *model, ah_input_mapping_t mapping,
                   ah_connectivity_t connectivity, ah_view_t *view);

#endif
