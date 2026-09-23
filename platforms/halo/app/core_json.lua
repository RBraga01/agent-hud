local json = {}

function json.quote(value)
    local escaped = value:gsub("\\", "\\\\")
        :gsub('"', '\\"')
        :gsub("\n", "\\n")
        :gsub("\r", "\\r")
        :gsub("\t", "\\t")
    return '"' .. escaped .. '"'
end

function json.decode(text)
    local pos = 1

    local function fail(message)
        error(message .. " at byte " .. pos)
    end

    local function skip_space()
        local _, last = text:find("^[ \n\r\t]*", pos)
        pos = (last or pos - 1) + 1
    end

    local function parse_string()
        if text:sub(pos, pos) ~= '"' then fail("expected string") end
        pos = pos + 1
        local out = {}
        while pos <= #text do
            local char = text:sub(pos, pos)
            pos = pos + 1
            if char == '"' then return table.concat(out) end
            if char == "\\" then
                local escape = text:sub(pos, pos)
                pos = pos + 1
                local escapes = {
                    ['"'] = '"', ["\\"] = "\\", ["/"] = "/",
                    b = "\b", f = "\f", n = "\n", r = "\r", t = "\t",
                }
                if not escapes[escape] then fail("unsupported escape") end
                out[#out + 1] = escapes[escape]
            else
                if char:byte() < 0x20 then fail("control character in string") end
                out[#out + 1] = char
            end
        end
        fail("unterminated string")
    end

    local parse_value

    local function parse_object()
        local object = {}
        pos = pos + 1
        skip_space()
        if text:sub(pos, pos) == "}" then pos = pos + 1 return object end
        while true do
            local key = parse_string()
            skip_space()
            if text:sub(pos, pos) ~= ":" then fail("expected colon") end
            pos = pos + 1
            object[key] = parse_value()
            skip_space()
            local char = text:sub(pos, pos)
            if char == "}" then pos = pos + 1 return object end
            if char ~= "," then fail("expected comma") end
            pos = pos + 1
            skip_space()
        end
    end

    local function parse_array()
        local array = {}
        pos = pos + 1
        skip_space()
        if text:sub(pos, pos) == "]" then pos = pos + 1 return array end
        while true do
            array[#array + 1] = parse_value()
            skip_space()
            local char = text:sub(pos, pos)
            if char == "]" then pos = pos + 1 return array end
            if char ~= "," then fail("expected comma") end
            pos = pos + 1
        end
    end

    function parse_value()
        skip_space()
        local char = text:sub(pos, pos)
        if char == '"' then return parse_string() end
        if char == "{" then return parse_object() end
        if char == "[" then return parse_array() end
        local literals = { ["true"] = true, ["false"] = false }
        for token, value in pairs(literals) do
            if text:sub(pos, pos + #token - 1) == token then
                pos = pos + #token
                return value
            end
        end
        if text:sub(pos, pos + 3) == "null" then pos = pos + 4 return nil end
        local number = text:sub(pos):match("^-?%d+%.?%d*[eE]?[+-]?%d*")
        if number and #number > 0 then pos = pos + #number return tonumber(number) end
        fail("invalid value")
    end

    local value = parse_value()
    skip_space()
    if pos <= #text then fail("trailing content") end
    return value
end

return json
