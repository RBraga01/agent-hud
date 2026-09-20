local input = {}

function input.bind(dispatch, profile)
    if profile == "B" then
        frame.button.single(function() dispatch("OPEN") end)
        frame.imu.tap_callback(function(kind)
            if kind == "single" then dispatch("NAVIGATE") end
        end)
    else
        frame.button.single(function() dispatch("NAVIGATE") end)
    end
    frame.button.double(function() dispatch("ACTIVATE") end)
    frame.button.long(function() dispatch("BACK") end)
end

return input
