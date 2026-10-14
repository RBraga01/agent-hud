#include <stdint.h>

#include "protocol.h"
#include "round_trip.h"
#include "expected_protocol_vector.h"

static int same(const char *left, const char *right)
{
    size_t index = 0U;
    while (left[index] == right[index]) {
        if (left[index] == '\0') return 1;
        ++index;
    }
    return 0;
}

#ifdef _WIN32
__declspec(dllexport)
#endif
int run_test(void)
{
    static const uint8_t request_bytes[] = EXPECTED_REQUEST_BYTES;
    static const uint8_t expected_decision[] = EXPECTED_DECISION_BYTES;
    static const uint8_t result_bytes[] = EXPECTED_RESULT_BYTES;
    ah_request_t request;
    ah_decision_t decision;
    ah_wire_result_t result;
    ah_round_trip_t round_trip = {
        .has_request = false,
        .accepted = false
    };
    ah_decision_t prepared;
    uint8_t encoded[512];
    size_t encoded_length;
    size_t index;

    if (sizeof(request_bytes) != EXPECTED_REQUEST_LENGTH ||
        !ah_decode_request(request_bytes, sizeof(request_bytes), &request))
        return 1;
    if (!same(request.session_id, "session-abc") ||
        !same(request.task_id, "task-42") ||
        request.revision != UINT64_C(9007199254740991) ||
        !same(request.title, "Review deploy?") ||
        !same(request.short_context, "Tests passed.") ||
        request.action_count != 2U ||
        !same(request.actions[0].action_id, "approve") ||
        !same(request.actions[1].action_id, "inspect"))
        return 2;

    decision.decision_id = "session-abc:1";
    decision.task_id = request.task_id;
    decision.revision = request.revision;
    decision.action_id = request.actions[1].action_id;
    encoded_length = ah_encode_decision(&decision, encoded, sizeof(encoded));
    if (encoded_length != EXPECTED_DECISION_LENGTH ||
        encoded_length != sizeof(expected_decision))
        return 3;
    for (index = 0U; index < encoded_length; ++index) {
        if (encoded[index] != expected_decision[index]) return 4;
    }

    if (!ah_decode_result(result_bytes, sizeof(result_bytes), &result) ||
        !same(result.decision_id, "session-abc:1") ||
        !same(result.task_id, "task-42") ||
        result.revision != UINT64_C(9007199254740991) ||
        result.status != 1U || result.original_status != 0U ||
        result.reason[0] != '\0')
        return 5;

    if (!ah_round_trip_receive(&round_trip, &request) ||
        !ah_round_trip_prepare(&round_trip, &prepared) ||
        prepared.revision != request.revision ||
        !same(prepared.task_id, request.task_id) ||
        !same(prepared.action_id, "approve"))
        return 6;
    ah_round_trip_mark_accepted(&round_trip);
    if (ah_round_trip_prepare(&round_trip, &prepared) ||
        ah_round_trip_receive(&round_trip, &request))
        return 7;

    encoded[0] = 0U;
    if (ah_decode_request(encoded, sizeof(request_bytes), &request)) return 8;
    return 0;
}

#ifndef _WIN32
int main(void)
{
    return run_test();
}
#endif
