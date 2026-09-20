-- Independent Lua binding of the normative M0 contract. No SDK dependency.
local json = require("core_json")
local canonical = {}

local function identifier(value)
    return type(value) == "string" and #value > 0 and #value <= 128
        and not value:find("[^%w._:-]")
end

function canonical.to_request(envelope)
    if type(envelope) ~= "table" or not identifier(envelope.session_id)
        or #envelope.session_id > 100 then return nil end
    local task = envelope.task
    local presentation = envelope.presentation
    if type(presentation) ~= "table" or type(presentation.title) ~= "string"
        or #presentation.title == 0 or type(presentation.short_context) ~= "string" then return nil end
    if type(task) ~= "table" or not identifier(task.task_id) then return nil end
    if type(task.revision) ~= "number" or task.revision < 0
        or task.revision > 9007199254740991 or task.revision % 1 ~= 0 then return nil end
    if type(task.actions) ~= "table" or #task.actions < 1 or #task.actions > 2 then return nil end
    local actions, seen = {}, {}
    for _, action in ipairs(task.actions) do
        if type(action) ~= "table" or not identifier(action.action_id)
            or seen[action.action_id] or type(action.label) ~= "string"
            or #action.label < 1 or #action.label > 16 then return nil end
        seen[action.action_id] = true
        actions[#actions + 1] = { id = action.action_id, label = action.label }
    end
    return {
        type = "request", request_id = task.task_id, version = task.revision,
        title = presentation.title, short_context = presentation.short_context,
        primary_action = actions[1], secondary_action = actions[2],
        audio_available = false, status = "pending", canonical = true,
        session_id = envelope.session_id,
    }
end

function canonical.encode(decision)
    return string.char(0x22) .. '{"decision_id":' .. json.quote(decision.decision_id)
        .. ',"task_id":' .. json.quote(decision.task_id)
        .. ',"revision":' .. tostring(decision.revision)
        .. ',"action_id":' .. json.quote(decision.action_id) .. '}'
end

function canonical.receive_result(state, result)
    local decision = state.decision
    if state.name ~= "SEND" or not decision or type(result) ~= "table" then return state end
    if result.decision_id ~= decision.decision_id or result.task_id ~= decision.task_id
        or result.revision ~= decision.revision then return state end
    local status = result.status
    if status == "DUPLICATE" then
        status = result.original_status
        if status ~= "ACCEPTED" and status ~= "STALE" and status ~= "INVALID_ACTION" then
            return state
        end
    end
    local states = { ACCEPTED = "ACK", STALE = "STALE", INVALID_ACTION = "REJECTED", ERROR = "ERROR" }
    if not states[status] then return state end
    state.name = states[status]
    state.canonical_status = status
    return state
end

return canonical
