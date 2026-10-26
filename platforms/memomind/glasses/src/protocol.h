#ifndef AGENT_HUD_MEMOMIND_PROTOCOL_H
#define AGENT_HUD_MEMOMIND_PROTOCOL_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define AH_REQUEST_CHANNEL UINT16_C(0x4148)
#define AH_RESPONSE_CHANNEL UINT16_C(0x4149)
#define AH_MAX_ID_BYTES 128U
#define AH_MAX_SESSION_BYTES 100U
#define AH_MAX_TITLE_BYTES 63U
#define AH_MAX_CONTEXT_BYTES 127U
#define AH_MAX_LABEL_BYTES 16U
#define AH_MAX_REASON_BYTES 256U
#define AH_MAX_ACTIONS 2U
#define AH_MAX_REVISION UINT64_C(9007199254740991)

typedef struct {
    char action_id[AH_MAX_ID_BYTES + 1U];
    char label[AH_MAX_LABEL_BYTES + 1U];
} ah_wire_action_t;

typedef struct {
    char session_id[AH_MAX_SESSION_BYTES + 1U];
    char task_id[AH_MAX_ID_BYTES + 1U];
    uint64_t revision;
    char title[AH_MAX_TITLE_BYTES + 1U];
    char short_context[AH_MAX_CONTEXT_BYTES + 1U];
    uint8_t action_count;
    ah_wire_action_t actions[AH_MAX_ACTIONS];
} ah_request_t;

typedef struct {
    const char *decision_id;
    const char *task_id;
    uint64_t revision;
    const char *action_id;
} ah_decision_t;

typedef struct {
    char decision_id[AH_MAX_ID_BYTES + 1U];
    char task_id[AH_MAX_ID_BYTES + 1U];
    uint64_t revision;
    uint8_t status;
    uint8_t original_status;
    char reason[AH_MAX_REASON_BYTES + 1U];
} ah_wire_result_t;

bool ah_decode_request(const uint8_t *bytes, size_t length,
                       ah_request_t *request);
size_t ah_encode_decision(const ah_decision_t *decision, uint8_t *output,
                          size_t capacity);
bool ah_decode_result(const uint8_t *bytes, size_t length,
                      ah_wire_result_t *result);

#endif
