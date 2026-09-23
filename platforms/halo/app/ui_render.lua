local display = require("adapter_display")
local layout = require("ui_layout")
local palette = require("ui_palette")

local render = {}

local function heading(text, color)
    display.font(1, 8, 1)
    display.text(text, 24, 28, color or palette.accent)
end

local function footer(text)
    display.font(0, 8, 1)
    display.text(text, 24, 218, palette.muted)
end

function render.draw(state, input_profile)
    display.clear(palette.background)
    if state.name == "QUIET" then return end
    if state.name == "ATTENTION" then
        display.circle(222, 34, 8, palette.accent, false)
        display.circle(222, 34, 2, palette.accent, true)
        return
    end

    if state.name == "REQUEST" then
        heading("REQUEST")
        display.text(layout.truncate(state.request.title, 25), 24, 62, palette.text)
        local lines = layout.wrap(state.request.short_context, 25, 3)
        for index, line in ipairs(lines) do
            display.text(line, 24, 90 + (index - 1) * 18, palette.muted)
        end
        footer("DOUBLE: ACTIONS")
        return
    end

    if state.name == "ACTION_MENU" then
        heading("CHOOSE ACTION")
        local entries = {}
        for _, action in ipairs(state.request.actions) do entries[#entries + 1] = action.label end
        entries[#entries + 1] = "Cancel"
        for index, label in ipairs(entries) do
            local y = 62 + (index - 1) * 34
            if index == state.focus then display.rect(20, y - 6, 216, 26, palette.focus, true) end
            display.text(layout.truncate(label, 22), 30, y, palette.text)
        end
        if input_profile == "B" then
            footer("TAP: MOVE  DOUBLE: SELECT")
        else
            footer("SINGLE: MOVE  DOUBLE: SELECT")
        end
        return
    end

    if state.name == "CONFIRMATION" then
        heading("CONFIRM", palette.confirm)
        display.rect(20, 58, 216, 88, palette.confirm, false)
        display.text(layout.truncate(state.selected_action.label, 22), 30, 78, palette.text)
        display.text(layout.truncate(state.request.request_id, 18), 30, 104, palette.muted)
        display.text("VERSION " .. state.request.version, 30, 124, palette.muted)
        footer("DOUBLE TO SEND")
        return
    end

    if state.name == "SEND" then
        heading("SENDING...", palette.confirm)
        footer("WAITING FOR RESULT")
        return
    end

    if state.name == "ACK" then
        display.circle(128, 92, 28, palette.success, false)
        display.text("OK", 120, 88, palette.success)
        heading("SENT", palette.success)
        display.text(layout.truncate(state.selected_action.label, 22), 48, 150, palette.text)
        footer("LONG: CLOSE")
        return
    end

    if state.name == "ERROR" then
        heading(state.request.canonical and "DELIVERY UNKNOWN" or "NOT SENT", palette.danger)
        display.rect(20, 58, 216, 88, palette.danger, false)
        display.text(state.request.canonical and "CHECK / RETRY" or "DELIVERY FAILED", 38, 82, palette.text)
        display.text("RECONFIRM TO RETRY", 30, 112, palette.muted)
        display.text("2X REVIEW", 92, 190, palette.muted)
        display.text("HOLD CLOSE", 88, 212, palette.muted)
        return
    end

    if state.name == "STALE" then
        heading("STALE REQUEST", palette.danger)
        display.rect(20, 58, 216, 88, palette.danger, false)
        display.text(state.canonical_status and "RELOAD REQUIRED" or "VERSION CHANGED", 42, 82, palette.text)
        display.text(
            state.canonical_status and "NOT ACCEPTED" or
                (tostring(state.request.version) .. " -> " .. tostring(state.latest_version)),
            86,
            112,
            palette.muted
        )
        if state.stale_request then display.text("2X RELOAD", 92, 190, palette.muted) end
        display.text("HOLD CLOSE", 88, 212, palette.muted)
    end

    if state.name == "REJECTED" then
        heading("ACTION REJECTED", palette.danger)
        display.text("NO LONGER OFFERED", 30, 82, palette.text)
        footer("LONG: CLOSE")
    end
end

return render
