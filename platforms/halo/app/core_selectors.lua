local selectors = {}

function selectors.state_name(state)
    return state.name
end

function selectors.can_send(state)
    return state.name == "CONFIRMATION" and state.selected_action ~= nil
end

return selectors
