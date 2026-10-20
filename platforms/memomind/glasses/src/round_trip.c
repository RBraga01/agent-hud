#include "round_trip.h"

static bool same_id(const char *left, const char *right)
{
    size_t index = 0U;
    while (index <= AH_MAX_ID_BYTES) {
        if (left[index] != right[index]) return false;
        if (left[index] == '\0') return true;
        ++index;
    }
    return false;
}

static void copy_request(ah_request_t *destination,
                         const ah_request_t *source)
{
    *destination = *source;
}

bool ah_round_trip_receive(ah_round_trip_t *state,
                           const ah_request_t *request)
{
    if (state == 0 || request == 0) return false;
    if (state->has_request && state->accepted &&
        state->request.revision == request->revision &&
        same_id(state->request.task_id, request->task_id))
        return false;
    copy_request(&state->request, request);
    state->has_request = true;
    state->accepted = false;
    return true;
}

bool ah_round_trip_prepare(const ah_round_trip_t *state,
                           ah_decision_t *decision)
{
    if (state == 0 || decision == 0 || !state->has_request || state->accepted)
        return false;
    decision->decision_id = "canonical-test:1";
    decision->task_id = state->request.task_id;
    decision->revision = state->request.revision;
    decision->action_id = state->request.actions[0].action_id;
    return true;
}

void ah_round_trip_mark_accepted(ah_round_trip_t *state)
{
    if (state != 0 && state->has_request) state->accepted = true;
}

void ah_round_trip_cancel(ah_round_trip_t *state)
{
    if (state == 0) return;
    state->has_request = false;
    state->accepted = false;
}
