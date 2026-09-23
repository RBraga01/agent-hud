local protocol = require("core_protocol")

local transport = {}

function transport.bind_receive(callback)
    frame.bluetooth.receive_callback(callback)
end

function transport.send_decision(decision)
    frame.bluetooth.send(protocol.encode_decision(decision))
end

return transport
