#ifndef AGENT_HUD_MEMOMIND_STATE_H
#define AGENT_HUD_MEMOMIND_STATE_H

#include <stdbool.h>
#include <stdint.h>

#define AH_CORE_MAX_ACTIONS 2U
#define AH_CORE_MAX_ID_BYTES 128U
#define AH_CORE_MAX_LABEL_BYTES 16U
#define AH_CORE_MAX_TITLE_BYTES 63U
#define AH_CORE_MAX_CONTEXT_BYTES 127U
#define AH_CORE_MAX_REVISION UINT64_C(9007199254740991)

typedef enum {
    AH_STATE_QUIET = 0,
    AH_STATE_ATTENTION,
    AH_STATE_REQUEST,
    AH_STATE_ACTION_MENU,
    AH_STATE_CONFIRMATION,
    AH_STATE_SEND,
    AH_STATE_ACK,
    AH_STATE_ERROR,
    AH_STATE_STALE,
    AH_STATE_REJECTED
} ah_state_t;

typedef enum {
    AH_EVENT_NONE = 0,
    AH_EVENT_REQUEST_ARRIVED,
    AH_EVENT_REQUEST_UPDATED,
    AH_EVENT_REQUEST_REMOVED,
    AH_EVENT_CONNECTION_LOST,
    AH_EVENT_NAVIGATE_NEXT,
    AH_EVENT_NAVIGATE_PREVIOUS,
    AH_EVENT_OPEN,
    AH_EVENT_ACTIVATE,
    AH_EVENT_BACK,
    AH_EVENT_CONFIRM,
    AH_EVENT_RESULT_RECEIVED,
    AH_EVENT_REVIEW_RETRY,
    AH_EVENT_RETRY
} ah_event_type_t;

typedef enum {
    AH_RESULT_NONE = 0,
    AH_RESULT_ACCEPTED,
    AH_RESULT_STALE,
    AH_RESULT_INVALID_ACTION,
    AH_RESULT_ERROR,
    AH_RESULT_DUPLICATE
} ah_result_status_t;

typedef enum {
    AH_EFFECT_NONE = 0,
    AH_EFFECT_SEND_DECISION
} ah_effect_type_t;

typedef struct {
    const char *action_id;
    const char *label;
} ah_core_action_t;

typedef struct {
    const char *task_id;
    uint64_t revision;
    const char *title;
    const char *short_context;
    uint8_t action_count;
    ah_core_action_t actions[AH_CORE_MAX_ACTIONS];
} ah_core_task_t;

typedef struct {
    const char *decision_id;
    const char *task_id;
    uint64_t revision;
    ah_result_status_t status;
    ah_result_status_t original_status;
    bool retryable;
} ah_result_t;

typedef struct {
    ah_event_type_t type;
    const ah_core_task_t *task;
    const char *task_id;
    const ah_result_t *result;
} ah_event_t;

typedef struct {
    char action_id[AH_CORE_MAX_ID_BYTES + 1U];
    char label[AH_CORE_MAX_LABEL_BYTES + 1U];
} ah_action_snapshot_t;

typedef struct {
    char task_id[AH_CORE_MAX_ID_BYTES + 1U];
    uint64_t revision;
    char title[AH_CORE_MAX_TITLE_BYTES + 1U];
    char short_context[AH_CORE_MAX_CONTEXT_BYTES + 1U];
    uint8_t action_count;
    ah_action_snapshot_t actions[AH_CORE_MAX_ACTIONS];
} ah_task_snapshot_t;

typedef struct {
    char decision_id[AH_CORE_MAX_ID_BYTES + 1U];
    char task_id[AH_CORE_MAX_ID_BYTES + 1U];
    uint64_t revision;
    char action_id[AH_CORE_MAX_ID_BYTES + 1U];
} ah_core_decision_t;

typedef struct {
    ah_effect_type_t type;
    ah_core_decision_t decision;
} ah_effect_t;

typedef struct {
    ah_state_t state;
    bool has_task;
    ah_task_snapshot_t task;
    uint8_t focused_action;
    uint8_t selected_action;
    uint64_t confirmation_revision;
    char session_id[AH_CORE_MAX_ID_BYTES + 1U];
    uint32_t next_decision_sequence;
    bool has_in_flight;
    bool retryable;
    bool retry_review;
    ah_core_decision_t in_flight;
} ah_model_t;

void ah_model_init(ah_model_t *model, const char *session_id);
ah_effect_t ah_transition(ah_model_t *model, const ah_event_t *event);

#endif
