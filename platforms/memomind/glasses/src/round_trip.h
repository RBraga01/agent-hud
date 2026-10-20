#ifndef AGENT_HUD_MEMOMIND_ROUND_TRIP_H
#define AGENT_HUD_MEMOMIND_ROUND_TRIP_H

#include "protocol.h"

typedef struct {
    ah_request_t request;
    bool has_request;
    bool accepted;
} ah_round_trip_t;

bool ah_round_trip_receive(ah_round_trip_t *state,
                           const ah_request_t *request);
bool ah_round_trip_prepare(const ah_round_trip_t *state,
                           ah_decision_t *decision);
void ah_round_trip_mark_accepted(ah_round_trip_t *state);
void ah_round_trip_cancel(ah_round_trip_t *state);

#endif
