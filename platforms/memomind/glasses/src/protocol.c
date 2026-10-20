#include "protocol.h"

#define AH_HEADER_BYTES 6U
#define AH_MAGIC_A UINT8_C(0x41)
#define AH_MAGIC_H UINT8_C(0x48)
#define AH_VERSION UINT8_C(2)
#define AH_REQUEST UINT8_C(1)
#define AH_DECISION UINT8_C(2)
#define AH_RESULT UINT8_C(3)

static uint16_t read_u16_be(const uint8_t *bytes)
{
    return (uint16_t)(((uint16_t)bytes[0] << 8U) | (uint16_t)bytes[1]);
}

static uint64_t read_u64_be(const uint8_t *bytes)
{
    uint64_t value = 0U;
    uint8_t index;
    for (index = 0U; index < 8U; ++index)
        value = (value << 8U) | (uint64_t)bytes[index];
    return value;
}

static void write_u16_be(uint8_t *bytes, uint16_t value)
{
    bytes[0] = (uint8_t)(value >> 8U);
    bytes[1] = (uint8_t)value;
}

static void write_u64_be(uint8_t *bytes, uint64_t value)
{
    int8_t index;
    for (index = 7; index >= 0; --index) {
        bytes[index] = (uint8_t)value;
        value >>= 8U;
    }
}

static bool identifier_byte(uint8_t value)
{
    return (value >= (uint8_t)'A' && value <= (uint8_t)'Z') ||
           (value >= (uint8_t)'a' && value <= (uint8_t)'z') ||
           (value >= (uint8_t)'0' && value <= (uint8_t)'9') ||
           value == (uint8_t)'.' || value == (uint8_t)'_' ||
           value == (uint8_t)':' || value == (uint8_t)'-';
}

static bool valid_header(const uint8_t *bytes, size_t length, uint8_t type)
{
    if (bytes == 0 || length < AH_HEADER_BYTES) return false;
    if (bytes[0] != AH_MAGIC_A || bytes[1] != AH_MAGIC_H ||
        bytes[2] != AH_VERSION || bytes[3] != type)
        return false;
    return (size_t)read_u16_be(bytes + 4U) == length - AH_HEADER_BYTES;
}

static bool read_text(const uint8_t *payload, size_t payload_length,
                      size_t *offset, char *output, size_t capacity,
                      bool allow_empty, bool identifier)
{
    size_t length;
    size_t index;
    if (*offset >= payload_length || capacity == 0U) return false;
    length = (size_t)payload[(*offset)++];
    if ((!allow_empty && length == 0U) || length >= capacity ||
        *offset + length > payload_length)
        return false;
    for (index = 0U; index < length; ++index) {
        uint8_t value = payload[*offset + index];
        if (value == 0U || (identifier && !identifier_byte(value))) return false;
        output[index] = (char)value;
    }
    output[length] = '\0';
    *offset += length;
    return true;
}

static bool read_long_text(const uint8_t *payload, size_t payload_length,
                           size_t *offset, char *output, size_t capacity)
{
    size_t length;
    size_t index;
    if (*offset + 2U > payload_length || capacity == 0U) return false;
    length = (size_t)read_u16_be(payload + *offset);
    *offset += 2U;
    if (length >= capacity || *offset + length > payload_length) return false;
    for (index = 0U; index < length; ++index) {
        if (payload[*offset + index] == 0U) return false;
        output[index] = (char)payload[*offset + index];
    }
    output[length] = '\0';
    *offset += length;
    return true;
}

static bool same_text(const char *left, const char *right)
{
    size_t index = 0U;
    while (left[index] == right[index]) {
        if (left[index] == '\0') return true;
        ++index;
    }
    return false;
}

bool ah_decode_request(const uint8_t *bytes, size_t length,
                       ah_request_t *request)
{
    const uint8_t *payload;
    size_t payload_length;
    size_t offset = 0U;
    uint8_t index;
    if (request == 0 || !valid_header(bytes, length, AH_REQUEST)) return false;
    payload = bytes + AH_HEADER_BYTES;
    payload_length = length - AH_HEADER_BYTES;
    if (!read_text(payload, payload_length, &offset, request->session_id,
                   sizeof(request->session_id), false, true) ||
        !read_text(payload, payload_length, &offset, request->task_id,
                   sizeof(request->task_id), false, true) ||
        offset + 8U > payload_length)
        return false;
    request->revision = read_u64_be(payload + offset);
    offset += 8U;
    if (request->revision > AH_MAX_REVISION ||
        !read_text(payload, payload_length, &offset, request->title,
                   sizeof(request->title), false, false) ||
        !read_text(payload, payload_length, &offset, request->short_context,
                   sizeof(request->short_context), true, false) ||
        offset >= payload_length)
        return false;
    request->action_count = payload[offset++];
    if (request->action_count == 0U || request->action_count > AH_MAX_ACTIONS)
        return false;
    for (index = 0U; index < request->action_count; ++index) {
        if (!read_text(payload, payload_length, &offset,
                       request->actions[index].action_id,
                       sizeof(request->actions[index].action_id), false, true) ||
            !read_text(payload, payload_length, &offset,
                       request->actions[index].label,
                       sizeof(request->actions[index].label), false, false))
            return false;
    }
    if (request->action_count == 2U &&
        same_text(request->actions[0].action_id,
                  request->actions[1].action_id))
        return false;
    return offset == payload_length;
}

static size_t bounded_identifier_length(const char *text)
{
    size_t length = 0U;
    if (text == 0) return 0U;
    while (length <= AH_MAX_ID_BYTES && text[length] != '\0') {
        if (!identifier_byte((uint8_t)text[length])) return 0U;
        ++length;
    }
    return length;
}

static size_t write_text(uint8_t *output, size_t offset, const char *text,
                         size_t length)
{
    size_t index;
    output[offset++] = (uint8_t)length;
    for (index = 0U; index < length; ++index) output[offset++] = (uint8_t)text[index];
    return offset;
}

size_t ah_encode_decision(const ah_decision_t *decision, uint8_t *output,
                          size_t capacity)
{
    size_t decision_length;
    size_t task_length;
    size_t action_length;
    size_t payload_length;
    size_t offset;
    if (decision == 0 || output == 0 || decision->revision > AH_MAX_REVISION)
        return 0U;
    decision_length = bounded_identifier_length(decision->decision_id);
    task_length = bounded_identifier_length(decision->task_id);
    action_length = bounded_identifier_length(decision->action_id);
    if (decision_length == 0U || decision_length > AH_MAX_ID_BYTES ||
        task_length == 0U || task_length > AH_MAX_ID_BYTES ||
        action_length == 0U || action_length > AH_MAX_ID_BYTES)
        return 0U;
    payload_length = 1U + decision_length + 1U + task_length + 8U + 1U +
                     action_length;
    if (payload_length > UINT16_MAX || capacity < AH_HEADER_BYTES + payload_length)
        return 0U;
    output[0] = AH_MAGIC_A;
    output[1] = AH_MAGIC_H;
    output[2] = AH_VERSION;
    output[3] = AH_DECISION;
    write_u16_be(output + 4U, (uint16_t)payload_length);
    offset = write_text(output, AH_HEADER_BYTES, decision->decision_id,
                        decision_length);
    offset = write_text(output, offset, decision->task_id, task_length);
    write_u64_be(output + offset, decision->revision);
    offset += 8U;
    return write_text(output, offset, decision->action_id, action_length);
}

bool ah_decode_result(const uint8_t *bytes, size_t length,
                      ah_wire_result_t *result)
{
    const uint8_t *payload;
    size_t payload_length;
    size_t offset = 0U;
    if (result == 0 || !valid_header(bytes, length, AH_RESULT)) return false;
    payload = bytes + AH_HEADER_BYTES;
    payload_length = length - AH_HEADER_BYTES;
    if (!read_text(payload, payload_length, &offset, result->decision_id,
                   sizeof(result->decision_id), false, true) ||
        !read_text(payload, payload_length, &offset, result->task_id,
                   sizeof(result->task_id), false, true) ||
        offset + 10U > payload_length)
        return false;
    result->revision = read_u64_be(payload + offset);
    offset += 8U;
    result->status = payload[offset++];
    result->original_status = payload[offset++];
    if (result->revision > AH_MAX_REVISION ||
        !read_long_text(payload, payload_length, &offset, result->reason,
                        sizeof(result->reason)) ||
        offset != payload_length || result->status < 1U ||
        result->status > 5U)
        return false;
    if (result->status == 5U)
        return result->original_status >= 1U && result->original_status <= 3U;
    return result->original_status == 0U;
}
