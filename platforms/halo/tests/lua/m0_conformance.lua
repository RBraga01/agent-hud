-- Test-only mapping of normative events to the application's existing inputs.
-- All state transitions and decision generation execute in production modules.
local App = require("app")
local json = require("core_json")
agent_hud = App.new("B")
local receive = agent_hud.on_receive

function agent_hud:on_receive(message)
    if message:byte(1) ~= 0x7e then return receive(self, message) end
    local event = json.decode(message:sub(2))
    if event.type == "observe" then
        local status = self.state.canonical_status
        frame.bluetooth.send(string.char(0x7f) .. '{"state":' .. json.quote(self.state.name)
            .. ',"result":' .. (status and json.quote(status) or 'null') .. '}')
    elseif event.type == "focus" then
        self:on_input("NAVIGATE")
    elseif event.type == "select" and self.state.name == "ACTION_MENU" then
        for index, action in ipairs(self.state.request.actions) do
            if action.id == event.action_id then
                while self.state.focus ~= index do self:on_input("NAVIGATE") end
                self:on_input("ACTIVATE")
                break
            end
        end
    elseif event.type == "confirm" and self.state.name == "CONFIRMATION" then
        self:on_input("ACTIVATE")
    elseif event.type == "cancel" then
        self:on_input("BACK")
    elseif event.type == "retry" and self.state.name == "ERROR" then
        self:on_input("ACTIVATE")
        self:on_input("ACTIVATE")
    end
end

agent_hud:start()
