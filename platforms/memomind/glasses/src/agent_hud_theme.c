#include "agent_hud_theme.h"

ah_theme_t ah_theme_for_state(ah_state_t state)
{
    ah_theme_t theme = {
        .layout = AH_LAYOUT_READING,
        .primary_gray = 15U,
        .secondary_gray = 11U,
        .fill_gray = 1U,
        .border_gray = 13U,
        .border_width = 2U,
        .focus_border_width = 4U,
        .control_radius = 10U,
        .panel_radius = 16U
    };
    switch (state) {
    case AH_STATE_QUIET:
        theme.layout = AH_LAYOUT_BLANK;
        theme.border_width = 0U;
        break;
    case AH_STATE_ATTENTION:
        theme.layout = AH_LAYOUT_INDICATOR;
        break;
    case AH_STATE_ACTION_MENU:
        theme.layout = AH_LAYOUT_CHOICES;
        break;
    case AH_STATE_CONFIRMATION:
        theme.layout = AH_LAYOUT_CONFIRMATION;
        break;
    case AH_STATE_SEND:
    case AH_STATE_ACK:
        theme.layout = AH_LAYOUT_STATUS;
        break;
    case AH_STATE_ERROR:
    case AH_STATE_STALE:
    case AH_STATE_REJECTED:
        theme.layout = AH_LAYOUT_WARNING;
        break;
    case AH_STATE_REQUEST:
    default:
        break;
    }
    return theme;
}
