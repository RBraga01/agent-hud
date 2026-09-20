local layout = {}

function layout.truncate(text, limit)
    if #text <= limit then return text end
    return text:sub(1, limit - 3) .. "..."
end

function layout.wrap(text, width, max_lines)
    local lines, current = {}, ""
    for word in text:gmatch("%S+") do
        local candidate = current == "" and word or current .. " " .. word
        if #candidate <= width then
            current = candidate
        else
            lines[#lines + 1] = layout.truncate(current, width)
            current = word
            if #lines == max_lines then return lines end
        end
    end
    if current ~= "" and #lines < max_lines then
        lines[#lines + 1] = layout.truncate(current, width)
    end
    return lines
end

return layout
