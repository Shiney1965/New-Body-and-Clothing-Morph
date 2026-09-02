-- Private production gate binding. No capability or gate setter is exported on
-- Mods.ClothMorphRuntime. Actual R0 modules retain their maps and algorithms.
local M = {}
local mutationAllowed
function M.CanMutate(operation,char)
    return mutationAllowed ~= nil and mutationAllowed(operation,char) == true
end
function M.BindModules(modules, allowed)
    mutationAllowed=allowed
    local entries = {
        EquipRace={SetClothed=1,ForceSetEquipRace=1,RefreshEquipment=1,OnEquipped=2,
            RunBlanketPass=0,CheckContentPresence=0,CheckExternalSources=0,
            RetryPendingExternalRefits=0,SetBCBPakPresent=0,SetOptout=0},
        BodyFamilyEquipRace={SetClothed=1,Restore=1,RefreshEquipment=1,OnEquipped=2,RunBlanketPass=0},
    }
    for moduleName, methods in pairs(entries) do
        local module = modules[moduleName]
        for name, argument in pairs(methods) do
            local original = module[name]
            if type(original)=='function' then
                module[name]=function(...)
                    local char = argument > 0 and select(argument,...) or nil
                    if not allowed(moduleName..'.'..name,char) then return false,'write-gate-closed' end
                    return original(...)
                end
            end
        end
        local original = module.ReapplyAll
        if type(original)=='function' then
            module.ReapplyAll=function(bodies,...)
                local managed={}
                for char,rec in pairs(bodies or {}) do
                    if allowed(moduleName..'.ReapplyAll',char) then managed[char]=rec end
                end
                if next(managed)==nil then return 0 end
                return original(managed,...)
            end
        end
    end
end
return M
