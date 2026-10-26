#include "input_mapping.h"

#include <stddef.h>

static bool map_common(ah_state_t state, ah_physical_input_t input,
                       ah_event_type_t *event)
{
    if (input == AH_INPUT_BACK || input == AH_INPUT_HEAD_SHAKE) {
        *event = AH_EVENT_BACK;
        return true;
    }
    if (input == AH_INPUT_HEAD_LEFT) {
        *event = AH_EVENT_NAVIGATE_PREVIOUS;
        return true;
    }
    if (input == AH_INPUT_HEAD_RIGHT) {
        *event = AH_EVENT_NAVIGATE_NEXT;
        return true;
    }
    if (input == AH_INPUT_PRIMARY_DOUBLE && state == AH_STATE_CONFIRMATION) {
        *event = AH_EVENT_CONFIRM;
        return true;
    }
    if (input == AH_INPUT_PRIMARY_DOUBLE && state == AH_STATE_ERROR) {
        *event = AH_EVENT_REVIEW_RETRY;
        return true;
    }
    return false;
}

bool ah_map_input(ah_input_mapping_t mapping, ah_state_t state,
                  ah_physical_input_t input, ah_event_type_t *event)
{
    if (event == NULL) return false;
    *event = AH_EVENT_NONE;
    if (map_common(state, input, event)) return true;
    if (mapping == AH_MAPPING_A) {
        if (input == AH_INPUT_PRIMARY_SINGLE &&
            (state == AH_STATE_ATTENTION || state == AH_STATE_STALE)) {
            *event = AH_EVENT_OPEN;
            return true;
        }
        if (input == AH_INPUT_PRIMARY_SINGLE &&
            (state == AH_STATE_REQUEST || state == AH_STATE_ACTION_MENU)) {
            *event = AH_EVENT_ACTIVATE;
            return true;
        }
        return false;
    }
    if (input == AH_INPUT_PRIMARY_SINGLE &&
        (state == AH_STATE_ATTENTION || state == AH_STATE_STALE)) {
        *event = AH_EVENT_OPEN;
        return true;
    }
    if (input == AH_INPUT_PRIMARY_SINGLE && state == AH_STATE_ACTION_MENU) {
        *event = AH_EVENT_NAVIGATE_NEXT;
        return true;
    }
    if (input == AH_INPUT_PRIMARY_DOUBLE &&
        (state == AH_STATE_REQUEST || state == AH_STATE_ACTION_MENU)) {
        *event = AH_EVENT_ACTIVATE;
        return true;
    }
    return false;
}
