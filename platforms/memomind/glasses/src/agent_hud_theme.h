#ifndef AGENT_HUD_MEMOMIND_THEME_H
#define AGENT_HUD_MEMOMIND_THEME_H

#include <stdint.h>

#include "agent_hud_state.h"

typedef enum {
    AH_LAYOUT_BLANK = 0,
    AH_LAYOUT_INDICATOR,
    AH_LAYOUT_READING,
    AH_LAYOUT_CHOICES,
    AH_LAYOUT_CONFIRMATION,
    AH_LAYOUT_STATUS,
    AH_LAYOUT_WARNING
} ah_layout_t;

typedef struct {
    ah_layout_t layout;
    uint8_t primary_gray;
    uint8_t secondary_gray;
    uint8_t fill_gray;
    uint8_t border_gray;
    uint8_t border_width;
    uint8_t focus_border_width;
    uint8_t control_radius;
    uint8_t panel_radius;
} ah_theme_t;

ah_theme_t ah_theme_for_state(ah_state_t state);

#endif
