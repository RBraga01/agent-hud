#ifndef AGENT_HUD_MEMOMIND_INPUT_MAPPING_H
#define AGENT_HUD_MEMOMIND_INPUT_MAPPING_H

#include "agent_hud_state.h"

typedef enum {
    AH_MAPPING_A = 0,
    AH_MAPPING_B
} ah_input_mapping_t;

typedef enum {
    AH_INPUT_NONE = 0,
    AH_INPUT_PRIMARY_SINGLE,
    AH_INPUT_PRIMARY_DOUBLE,
    AH_INPUT_BACK,
    AH_INPUT_HEAD_LEFT,
    AH_INPUT_HEAD_RIGHT,
    AH_INPUT_HEAD_SHAKE
} ah_physical_input_t;

bool ah_map_input(ah_input_mapping_t mapping, ah_state_t state,
                  ah_physical_input_t input, ah_event_type_t *event);

#endif
