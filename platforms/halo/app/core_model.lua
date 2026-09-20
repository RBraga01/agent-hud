local model = {}

local function non_empty_string(value)
    return type(value) == "string" and #value > 0
end

local function valid_action(value)
    return type(value) == "table"
        and non_empty_string(value.id)
        and non_empty_string(value.label)
end

function model.new_request(payload)
    if type(payload) ~= "table" or payload.type ~= "request" then
        return nil, "invalid type"
    end
    if not non_empty_string(payload.request_id) then return nil, "invalid request_id" end
    if type(payload.version) ~= "number" or payload.version < (payload.canonical and 0 or 1)
        or payload.version % 1 ~= 0 then return nil, "invalid version" end
    if not non_empty_string(payload.title) then return nil, "invalid title" end
    if type(payload.short_context) ~= "string" then return nil, "invalid context" end
    if not valid_action(payload.primary_action) then return nil, "invalid primary action" end
    if payload.secondary_action ~= nil and not valid_action(payload.secondary_action) then
        return nil, "invalid secondary action"
    end
    if type(payload.audio_available) ~= "boolean" then return nil, "invalid audio flag" end
    if payload.status ~= "pending" then return nil, "invalid status" end

    local actions = { payload.primary_action }
    if payload.secondary_action then actions[#actions + 1] = payload.secondary_action end
    if payload.audio_available then
        actions[#actions + 1] = { id = "audio", label = "Audio", kind = "audio" }
    end

    return {
        request_id = payload.request_id,
        version = payload.version,
        title = payload.title,
        short_context = payload.short_context,
        actions = actions,
        audio_available = payload.audio_available,
        status = payload.status,
        canonical = payload.canonical,
        session_id = payload.session_id,
    }
end

return model
