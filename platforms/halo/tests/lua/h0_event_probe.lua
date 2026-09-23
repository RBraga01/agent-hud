frame.button.single(function()
    frame.bluetooth.send("button:single")
end)

frame.button.double(function()
    frame.bluetooth.send("button:double")
end)

frame.button.long(function()
    frame.bluetooth.send("button:long")
end)

frame.imu.tap_callback(function(kind)
    frame.bluetooth.send("tap:" .. kind)
end)

frame.bluetooth.receive_callback(function(data)
    if data == "read-direction" then
        local direction = frame.imu.direction()
        local message = string.format(
            "direction:%.1f,%.1f,%.1f",
            direction.pitch,
            direction.roll,
            direction.heading
        )
        frame.bluetooth.send(message)
        return
    end

    frame.bluetooth.send("ble:" .. data)
end)

frame.sleep(5.0)
