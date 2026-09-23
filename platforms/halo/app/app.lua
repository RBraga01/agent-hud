local display = require("adapter_display")
local input = require("adapter_input")
local transport = require("adapter_transport")
local protocol = require("core_protocol")
local reducer = require("core_reducer")
local render = require("ui_render")
local canonical = require("core_canonical")

local App = {}
App.__index = App

function App.new(input_profile)
    return setmetatable({
        state = reducer.initial_state(),
        input_profile = input_profile or "A",
        decision_counter = 0,
    }, App)
end

function App:on_receive(message)
    local code, payload = protocol.decode(message)
    if code == protocol.REQUEST then
        if not self.session_id and type(payload) == "table" then
            payload.canonical = nil
            payload.session_id = nil
            self.state = reducer.receive_request(self.state, payload)
        end
    elseif code == protocol.RESULT then
        if not (self.state.request and self.state.request.canonical) then
            self.state = reducer.receive_result(self.state, payload)
        end
    elseif code == 0x12 then
        local request = canonical.to_request(payload)
        if request and (not self.session_id or self.session_id == request.session_id) then
            self.session_id = request.session_id
            self.state = reducer.receive_request(self.state, request)
        end
    elseif code == 0x13 then
        self.state = canonical.receive_result(self.state, payload)
    end
    render.draw(self.state, self.input_profile)
end

function App:on_input(event)
    self.state = reducer.dispatch(self.state, event)
    local decision = reducer.take_decision(self.state, function()
        self.decision_counter = self.decision_counter + 1
        return self.session_id .. ":" .. tostring(self.decision_counter)
    end)
    if decision then transport.send_decision(decision) end
    render.draw(self.state, self.input_profile)
end

function App:start()
    display.initialize()
    render.draw(self.state, self.input_profile)
    transport.bind_receive(function(message) self:on_receive(message) end)
    input.bind(function(event) self:on_input(event) end, self.input_profile)
    while true do frame.sleep(0.1) end
end

return App
