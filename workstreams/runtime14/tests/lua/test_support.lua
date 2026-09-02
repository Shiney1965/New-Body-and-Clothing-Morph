local M = { total = 0, passed = 0 }

local function render(value, seen)
    if type(value) ~= "table" then return tostring(value) end
    seen = seen or {}
    if seen[value] then return "<cycle>" end
    seen[value] = true
    local keys = {}
    for key in pairs(value) do keys[#keys + 1] = key end
    table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
    local parts = {}
    for _, key in ipairs(keys) do
        parts[#parts + 1] = tostring(key) .. "=" .. render(value[key], seen)
    end
    return "{" .. table.concat(parts, ",") .. "}"
end

function M.equal(actual, expected, label)
    if actual ~= expected then
        error((label or "values differ") .. ": expected " .. render(expected)
            .. ", got " .. render(actual), 2)
    end
end

function M.truthy(value, label)
    if value ~= true then error((label or "expected true") .. ": got " .. render(value), 2) end
end

function M.falsy(value, label)
    if value ~= false then error((label or "expected false") .. ": got " .. render(value), 2) end
end

function M.deep_equal(actual, expected, label, path)
    path = path or "root"
    if type(actual) ~= type(expected) then
        error((label or "tables differ") .. ": type mismatch at " .. path
            .. " expected " .. type(expected) .. " got " .. type(actual), 2)
    end
    if type(actual) ~= "table" then
        if actual ~= expected then
            error((label or "tables differ") .. ": mismatch at " .. path
                .. " expected " .. render(expected) .. " got " .. render(actual), 2)
        end
        return
    end
    for key, value in pairs(expected) do
        M.deep_equal(actual[key], value, label, path .. "." .. tostring(key))
    end
    for key in pairs(actual) do
        if expected[key] == nil then
            error((label or "tables differ") .. ": unexpected key at "
                .. path .. "." .. tostring(key), 2)
        end
    end
end

function M.copy(value, seen)
    if type(value) ~= "table" then return value end
    seen = seen or {}
    if seen[value] then return seen[value] end
    local out = {}
    seen[value] = out
    for key, item in pairs(value) do out[M.copy(key, seen)] = M.copy(item, seen) end
    return out
end

function M.test(name, fn)
    M.total = M.total + 1
    local ok, err = pcall(fn)
    if not ok then
        io.stderr:write("FAIL " .. name .. "\n" .. tostring(err) .. "\n")
        os.exit(1)
    end
    M.passed = M.passed + 1
    io.write("PASS " .. name .. "\n")
end

return M
