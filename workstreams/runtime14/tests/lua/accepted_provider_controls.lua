-- Read-only diagnostic: execute the exact extracted accepted provider bootstrap
-- against isolated mocked API surfaces. This is not BG3/gameplay evidence.
local bootstrapPath = assert(arg[1], "exact extracted provider bootstrap required")
for _, apiVersion in ipairs({1, 2}) do
    local calls, warnings, sessionCallbacks = {}, {}, {}
    local runtime = {
        BodyFamilyApiVersion = apiVersion,
        RegisterBodyFamily = function(source, spec)
            calls[#calls + 1] = "body"
            assert(source == "ClothMorphTieflingBT1Test")
            assert(spec.moduleUuid == "b57bab2c-5679-5445-8fee-ca8c282990a5")
            assert(spec.profiles.bcb.requiredModUuid == "1d24059d-ff23-4a79-8892-57c85d512416")
            return true
        end,
        RegisterFamilyRefits = function() calls[#calls + 1] = "refits"; return true end,
        ReapplyBodyFamilies = function() calls[#calls + 1] = "reapply" end,
    }
    local env = setmetatable({
        Mods = {ClothMorphRuntime = runtime},
        Ext = {
            Utils = {
                Print = function() end,
                PrintWarning = function(message) warnings[#warnings + 1] = message end,
            },
            Events = {SessionLoaded = {Subscribe = function(_, fn)
                sessionCallbacks[#sessionCallbacks + 1] = fn
            end}},
            Osiris = {RegisterListener = function() end},
        },
    }, {__index = _G})
    assert(loadfile(bootstrapPath, "t", env))()
    assert(#sessionCallbacks == 1)
    sessionCallbacks[1]()
    if apiVersion == 1 then
        assert(table.concat(calls, ",") == "body,refits,reapply")
        assert(#warnings == 0)
    else
        assert(#calls == 0)
        assert(#warnings == 1)
        assert(warnings[1]:find("paired Runtime body-family API v1 is unavailable", 1, true))
    end
    print(string.format("api=%d calls=%d sequence=%s warnings=%d", apiVersion,
        #calls, table.concat(calls, ","), #warnings))
end
print("ACCEPTED_PROVIDER_API_GUARD_REPRODUCED")
