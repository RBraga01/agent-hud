local model = require("core_model")

local reducer = {}

function reducer.initial_state()
    return {
        name = "QUIET",
        request = nil,
        focus = 1,
        selected_action = nil,
        latest_version = nil,
    }
end

function reducer.receive_request(state, payload)
    local request = model.new_request(payload)
    if not request then return state end
    -- A new observation cannot undo a decision already transmitted.
    if state.name == "SEND" or state.name == "ACK" then return state end

    if state.request and request.request_id == state.request.request_id then
        if request.version <= (state.latest_version or state.request.version) then return state end
        if state.name ~= "QUIET" and state.name ~= "ATTENTION" then
            state.latest_version = request.version
            state.stale_request = request
            state.send_pending = false
            state.name = "STALE"
            return state
        end
    elseif state.name ~= "QUIET" and state.name ~= "ATTENTION" then
        return state
    end

    state.request = request
    state.latest_version = request.version
    state.focus = 1
    state.selected_action = nil
    state.name = "ATTENTION"
    return state
end

function reducer.dispatch(state, event)
    if event == "BACK" then
        if state.name == "ATTENTION" then
            return reducer.initial_state()
        elseif state.name == "REQUEST" then
            state.name = "ATTENTION"
        elseif state.name == "ACTION_MENU" then
            state.name = "REQUEST"
        elseif state.name == "CONFIRMATION" then
            state.name = "ACTION_MENU"
            state.selected_action = nil
            state.decision = nil
        elseif state.name == "ACK" or state.name == "ERROR" or state.name == "STALE"
            or state.name == "REJECTED" then
            return reducer.initial_state()
        end
        return state
    end

    if event == "NAVIGATE" and state.name == "ACTION_MENU" then
        state.focus = (state.focus % (#state.request.actions + 1)) + 1
        return state
    end
    if event == "OPEN" then
        if state.name == "ATTENTION" then
            state.name = "REQUEST"
        elseif state.name == "REQUEST" then
            state.name = "ACTION_MENU"
            state.focus = 1
        end
        return state
    end
    if event ~= "ACTIVATE" then return state end

    if state.name == "ERROR" then
        state.name = "CONFIRMATION"
    elseif state.name == "STALE" and state.stale_request then
        state.request = state.stale_request
        state.stale_request = nil
        state.selected_action = nil
        state.focus = 1
        state.name = "ATTENTION"
    elseif state.name == "ATTENTION" then
        state.name = "REQUEST"
    elseif state.name == "REQUEST" then
        state.name = "ACTION_MENU"
        state.focus = 1
    elseif state.name == "ACTION_MENU" then
        if state.focus > #state.request.actions then
            return reducer.initial_state()
        end
        state.selected_action = state.request.actions[state.focus]
        state.decision = nil
        state.name = "CONFIRMATION"
    elseif state.name == "CONFIRMATION" then
        if state.latest_version ~= state.request.version then
            state.name = "STALE"
            return state
        end
        state.name = "SEND"
        state.send_pending = true
        state.canonical_status = nil
    end
    return state
end

function reducer.take_decision(state, allocate)
    if state.name ~= "SEND" or not state.send_pending then return nil end
    state.send_pending = false
    if state.request.canonical then
        if not state.decision then
            state.decision = {
                decision_id = allocate(), task_id = state.request.request_id,
                revision = state.request.version, action_id = state.selected_action.id,
            }
        end
        return state.decision
    end
    return {
        request_id = state.request.request_id,
        version = state.request.version,
        action_id = state.selected_action.id,
    }
end

function reducer.receive_result(state, payload)
    if state.name ~= "SEND" or type(payload) ~= "table" then return state end
    if payload.type ~= "result" then return state end
    if payload.request_id ~= state.request.request_id
        or payload.version ~= state.request.version then return state end
    if payload.status == "ack" then
        state.name = "ACK"
    elseif payload.status == "error" then
        state.name = "ERROR"
    end
    return state
end

return reducer
