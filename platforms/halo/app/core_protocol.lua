local json = require("core_json")
local canonical = require("core_canonical")

local protocol = {
    REQUEST = 0x10,
    RESULT = 0x11,
    DECISION = 0x20,
}

function protocol.decode(message)
    if type(message) ~= "string" or #message < 2 then return nil, "short message" end
    local code = string.byte(message, 1)
    local ok, payload = pcall(json.decode, string.sub(message, 2))
    if not ok then return nil, "invalid json" end
    return code, payload
end

function protocol.encode_decision(decision)
    if decision.decision_id then return canonical.encode(decision) end
    local body = '{"type":"decision","request_id":' .. json.quote(decision.request_id)
        .. ',"version":' .. tostring(decision.version)
        .. ',"action_id":' .. json.quote(decision.action_id) .. '}'
    return string.char(protocol.DECISION) .. body
end

return protocol
