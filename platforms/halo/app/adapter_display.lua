local display = {}

function display.initialize()
    frame.display.power_save(false)
    frame.display.clear(0x000000)
end

function display.clear(color) frame.display.clear(color) end
function display.font(id, size, scale) frame.display.set_font(id, size, scale) end
function display.text(text, x, y, color) frame.display.text(text, x, y, color) end
function display.circle(x, y, radius, color, filled)
    frame.display.circle(x, y, radius, color, filled)
end
function display.rect(x, y, width, height, color, filled)
    frame.display.rect(x, y, width, height, color, filled)
end

return display
