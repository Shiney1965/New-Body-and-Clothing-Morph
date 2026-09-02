local M = {}

local script = debug.getinfo(1, "S").source:sub(2):gsub("\\", "/")
local testsDir = script:match("^(.*)/[^/]+$")
local runtimeLua = assert(arg[1], "explicit Runtime source root required"):gsub("\\", "/")
    .. "/Mods/ClothMorphRuntime/ScriptExtender/Lua"

local RUNTIME_UUID = "20aca985-e3e9-41d7-bf8f-10f2a3c413e4"
local CHAR = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
local CV = "11111111-1111-1111-1111-111111111111"
local VALID_BODY = "22222222-2222-2222-2222-222222222222"
local VALID_EQUIP = "33333333-3333-3333-3333-333333333333"
local RUNTIME_BODY = "44444444-4444-4444-4444-444444444444"
local RUNTIME_CCSV = "55555555-5555-5555-5555-555555555555"
local RUNTIME_EQUIP = "66666666-6666-6666-6666-666666666666"
local RUNTIME_BODY_B = "77777777-7777-7777-7777-777777777777"
local RUNTIME_CCSV_B = "88888888-8888-8888-8888-888888888888"

M.ids = {
    runtimeUuid = RUNTIME_UUID,
    char = CHAR,
    cv = CV,
    validBody = VALID_BODY,
    validEquip = VALID_EQUIP,
    runtimeBody = RUNTIME_BODY,
    runtimeCcsv = RUNTIME_CCSV,
    runtimeEquip = RUNTIME_EQUIP,
    runtimeBodyB = RUNTIME_BODY_B,
    runtimeCcsvB = RUNTIME_CCSV_B,
}

local function choiceValid(choice)
    return choice == "vanilla" or choice == "sbbf" or choice == "bcb"
        or choice == "external"
end

function M.Boot(options)
    options = options or {}
    local state = options.state or {
        Version = 6,
        BodyTattooPolicy = "match",
        Bodies = {
            [CHAR] = {
                Choice = "sbbf",
                OrigBodySetVisual = VALID_BODY,
                CvGuid = CV,
                OrigEquipRace = VALID_EQUIP,
            },
        },
    }
    local visuals = options.visuals or {}
    local console = {}
    local listeners = {}
    local warnings = {}
    local logs = {}
    local loadedProductionModuleHashes = {}
    local expectedProductionModuleHashes = {}
    local addCalls = 0
    local failAddCcsv = options.failAddCcsv
    local rollbackReadbackAfterAddFailure = options.rollbackReadbackAfterAddFailure
    local registrationCalls = 0
    local registrationOrder = {}
    local loadedModules = options.loadedModules or {
        [RUNTIME_UUID] = true,
        ["99999999-9999-4999-8999-999999999999"] = true,
    }
    local currentBody = options.currentBody or RUNTIME_BODY
    local currentEquip = options.currentEquip or VALID_EQUIP
    local entityCv = options.entityCv or CV
    local characterVisualResolvable = options.characterVisualResolvable == true
    local torsoCovered = options.torsoCovered == true
    local forcedVisualReadback
    local forcedVisualReadbackNil = false
    local bodyResources = options.bodyResources or {
        [VALID_BODY] = { SourceFile = "Generated/Public/BCBPak/valid-body.gr2" },
        [RUNTIME_BODY] = { SourceFile = "Generated/Public/ClothMorphRuntime/runtime-body.gr2" },
        [RUNTIME_BODY_B] = { SourceFile = "Generated/Public/ClothMorphRuntime/runtime-body-b.gr2" },
    }
    local characterVisual = { VisualSet = { BodySetVisual = currentBody } }

    local entity = {
        CharacterCreationAppearance = { Visuals = visuals },
        CharacterCreationStats = { Race = "race", BodyType = "1", BodyShape = "0" },
        ServerCharacter = { Template = {
            CharacterVisualResourceID = entityCv,
            EquipmentRace = currentEquip,
        } },
    }
    function entity:Replicate()
        if forcedVisualReadbackNil then
            self.CharacterCreationAppearance.Visuals = nil
        elseif forcedVisualReadback ~= nil then
            local restored = {}
            for index, value in ipairs(forcedVisualReadback) do restored[index] = value end
            self.CharacterCreationAppearance.Visuals = restored
        end
    end

    local shared = {
        BODY_CHOICES = { vanilla = "vanilla", sbbf = "sbbf", bcb = "bcb", external = "external" },
        CCSV_MAP = {
            ["sbbf__fixture"] = RUNTIME_CCSV,
            ["bcb__fixture"] = RUNTIME_CCSV_B,
        },
        IsValidBodyChoice = choiceValid,
        NextBodyChoice = function(choice)
            if choice == "vanilla" then return "sbbf" end
            if choice == "sbbf" then return "bcb" end
            return "vanilla"
        end,
        ReadCharStats = function() return "race", "1", "0" end,
        ResolveCcsv = function(choice)
            if choice == "sbbf" then return RUNTIME_CCSV, choice .. "__fixture" end
            if choice == "bcb" then return RUNTIME_CCSV_B, choice .. "__fixture" end
            return nil, choice .. "__fixture"
        end,
        FindOverride = function() return {}, {} end,
    }
    local equipRace
    equipRace = {
        MINTED = { vanilla = "minted-vanilla", sbbf = RUNTIME_EQUIP },
        KNOWN_ORIG = options.knownOrig or {},
        OPTOUT = {},
        IsMintedEquipmentRace = function(guid)
            return tostring(guid):lower() == RUNTIME_EQUIP
                or tostring(guid):lower() == "minted-vanilla"
        end,
        IsEligible = function(guid) return guid == VALID_EQUIP end,
        ReadEquipRace = function() return entity.ServerCharacter.Template.EquipmentRace end,
        SetClothed = function(_, choice, rec)
            if choice == "off" then
                entity.ServerCharacter.Template.EquipmentRace = rec.OrigEquipRace
                rec.ClothedChoice = "off"
                return rec.OrigEquipRace ~= nil
            end
            local target = equipRace.MINTED[choice]
            if target == nil then return false end
            entity.ServerCharacter.Template.EquipmentRace = target
            rec.ClothedChoice = choice
            return true
        end,
        ForceSetEquipRace = function(_, guid, rec)
            entity.ServerCharacter.Template.EquipmentRace = guid
            rec.OrigEquipRace = guid
            return true
        end,
        REFIT_BY_VR = options.existingTargets or { vanilla = {}, sbbf = {}, bcb = {} },
        RegisterExternalRefits = function(sourceName)
            registrationCalls = registrationCalls + 1
            registrationOrder[#registrationOrder + 1] = tostring(sourceName)
            return options.failRegistration ~= true
        end,
        RefreshEquipment = function() end,
        ReadEquipRace = function() return entity.ServerCharacter.Template.EquipmentRace end,
        SetBCBPakPresent = function() end,
        HasBCBPak = function() return true end,
        HasLegacyGithyankiPak = function() return false end,
        SetOptout = function() return nil end,
        DumpStatus = function() end,
        RunBlanketPass = function() end,
        ReapplyAll = function() return 0 end,
        RetryPendingExternalRefits = function() end,
        CheckContentPresence = function() end,
        CheckExternalSources = function() end,
        OnEquipped = function() end,
    }
    local bodyFamilyRegistry = {
        ResolveOfficialFamily = function() return nil end,
        IsMintedEquipmentRace = function(guid) return guid == RUNTIME_EQUIP end,
        SafeSourceEquipmentRace = function() return VALID_EQUIP end,
        RegisterBodyFamily = function() return true end,
    }
    local bodyFamilyEquip = {
        ReapplyAll = function() return 0 end,
        RegisterFamilyRefits = function() return true end,
        ReadEquipRace = equipRace.ReadEquipRace,
        OnEquipped = function() end,
        Restore = function() return true end,
    }
    local target = {
        NormGuid = function(value)
            if value == nil or value == "" then return nil end
            return tostring(value):lower()
        end,
        ResolveTarget = function() return CHAR end,
        CanUserControl = function() return true end,
        GetReservedUserId = function() return 1 end,
    }
    local tattooPolicy = {
        Normalize = function(value) return value or "match" end,
        IsHumF = function() return false end,
        DetectEnvironment = function() return "none" end,
        Resolve = function() return nil, "not-applicable" end,
        ResolveCcsv = function() return nil, "not-applicable" end,
        DescribeVariants = function() return {} end,
    }
    local stubs = {
        ["Shared.lua"] = shared,
        ["TattooPolicy.lua"] = tattooPolicy,
        ["TattooStateProbe.lua"] = {},
        ["TattooDiagnostics.lua"] = { Register = function() end },
        ["EquipRace.lua"] = equipRace,
        ["BodyFamilyRegistry.lua"] = bodyFamilyRegistry,
        ["BodyFamilyEquipRace.lua"] = bodyFamilyEquip,
        ["Targeting.lua"] = target,
        ["SharedTemplateProbe.lua"] = {
            ReadSnapshot = function() return {} end,
            CompareSnapshots = function() return { sameTemplate = false } end,
            FormatReport = function() return "fixture" end,
        },
    }
    local actual = {
        ["StateSchema7.lua"] = true,
        ["MasterState.lua"] = true,
        ["OwnershipLedger.lua"] = true,
        ["R1Foundation.lua"] = true,
        ["ProviderRegistry.lua"] = true,
        ["RuntimeRollback.lua"] = true,
        ["MCMIntegration.lua"] = true,
    }
    local moduleCache = {}

    _G.Mods = { ClothMorphRuntime = { ModuleUUID = RUNTIME_UUID } }
    _G.PersistentVars = state
    _G.ModuleUUID = RUNTIME_UUID
    _G.MCM = {
        Get = function() return false end,
        Set = function() return true end,
        Keybinding = { SetCallback = function() end },
    }
    _G.Osi = {
        GetHostCharacter = function() return CHAR end,
        IsPartyMember = function() return 1 end,
        AddCustomVisualOverride = function(_, ccsv)
            addCalls = addCalls + 1
            if failAddCcsv ~= nil
                and tostring(ccsv):lower() == tostring(failAddCcsv):lower() then
                if rollbackReadbackAfterAddFailure ~= nil then
                    forcedVisualReadback = {}
                    for index, value in ipairs(rollbackReadbackAfterAddFailure) do
                        forcedVisualReadback[index] = value
                    end
                end
                error("forced AddCustomVisualOverride failure for " .. tostring(ccsv))
            end
            local live = entity.CharacterCreationAppearance.Visuals
            live[#live + 1] = ccsv
        end,
        GetEquippedItem = function(_, slot)
            if torsoCovered and slot == "Breast" then return "torso-item" end
            return nil
        end,
        Unequip = function() end,
        Equip = function() end,
    }

    local channel = {}
    function channel:SetHandler(fn) self.handler = fn end
    function channel:SetRequestHandler(fn) self.requestHandler = fn end
    function channel:Broadcast() end

    local event = { Subscribe = function(_, fn) listeners[#listeners + 1] = fn end }
    _G.Ext = {
        Require = function(name)
            if stubs[name] ~= nil then return stubs[name] end
            if not actual[name] then error("unexpected Ext.Require: " .. tostring(name)) end
            if moduleCache[name] == nil then
                local modulePath = runtimeLua .. "/" .. name
                if name == "RuntimeRollback.lua" then
                    local expectedStream = assert(io.open(modulePath, "rb"))
                    local expectedSource = expectedStream:read("*a")
                    expectedStream:close()
                    expectedProductionModuleHashes[name] = moduleCache["ProviderRegistry.lua"].Sha256(expectedSource)
                end
                local chunk = assert(loadfile(modulePath))
                moduleCache[name] = chunk()
                if name == "RuntimeRollback.lua" then
                    local stream = assert(io.open(modulePath, "rb"))
                    local source = stream:read("*a")
                    stream:close()
                    loadedProductionModuleHashes[name] = moduleCache["ProviderRegistry.lua"].Sha256(source)
                end
            end
            return moduleCache[name]
        end,
        Utils = {
            Print = function(message) logs[#logs + 1] = tostring(message) end,
            PrintWarning = function(message) warnings[#warnings + 1] = tostring(message) end,
            MonotonicTime = function() return 10000 end,
        },
        StaticData = {
            Get = function(guid, kind)
                if kind == "CharacterCreationSharedVisual" and guid == RUNTIME_CCSV then
                    return { VisualResource = RUNTIME_BODY }
                end
                if kind == "CharacterCreationSharedVisual" and guid == RUNTIME_CCSV_B then
                    return { VisualResource = RUNTIME_BODY_B }
                end
                return nil
            end,
            GetAll = function() return {} end,
        },
        Resource = {
            Get = function(guid, kind)
                if kind == "CharacterVisual" and guid == entityCv and characterVisualResolvable then
                    return characterVisual
                end
                if kind == "Visual" then return bodyResources[guid] end
                return nil
            end,
        },
        Entity = {
            Get = function(guid) if tostring(guid):lower() == CHAR then return entity end end,
            GetAllEntitiesWithComponent = function() return {} end,
        },
        Mod = {
            GetMod = function() return nil end,
            GetLoadOrder = function()
                local out = {}
                for uuid, loaded in pairs(loadedModules) do if loaded then out[#out + 1] = uuid end end
                table.sort(out)
                return out
            end,
        },
        Net = { CreateChannel = function() return channel end },
        Osiris = { RegisterListener = function(name, _, _, fn) listeners[name] = fn end },
        Events = { SessionLoaded = event },
        ModEvents = { BG3MCM = { MCM_Setting_Saved = event } },
        Timer = { WaitFor = function(_, fn) fn() end },
        RegisterConsoleCommand = function(name, fn) console[name] = fn end,
    }

    local chunk = assert(loadfile(runtimeLua .. "/BootstrapServer.lua"))
    chunk()

    return {
        state = _G.PersistentVars,
        mod = _G.Mods.ClothMorphRuntime,
        console = console,
        warnings = warnings,
        logs = logs,
        listeners = listeners,
        entity = entity,
        visuals = visuals,
        channel = channel,
        addCalls = function() return addCalls end,
        registrationCalls = function() return registrationCalls end,
        registrationOrder = registrationOrder,
        loadedProductionModuleHashes = loadedProductionModuleHashes,
        expectedProductionModuleHashes = expectedProductionModuleHashes,
        registerExternalRefits = _G.RegisterExternalRefits,
        readVisuals = function()
            local out = {}
            for index, value in ipairs(entity.CharacterCreationAppearance.Visuals or {}) do out[index] = value end
            return out
        end,
        setCharacterVisualResolvable = function(value) characterVisualResolvable = value == true end,
        setCurrentBody = function(value) characterVisual.VisualSet.BodySetVisual = value end,
        readCurrentBody = function() return characterVisual.VisualSet.BodySetVisual end,
        setTorsoCovered = function(value) torsoCovered = value == true end,
        forceVisualReadback = function(value)
            if value == nil then forcedVisualReadback = nil; return end
            forcedVisualReadback = {}
            for index, item in ipairs(value) do forcedVisualReadback[index] = item end
        end,
        forceVisualReadbackNil = function(value) forcedVisualReadbackNil = value == true end,
        setModuleLoaded = function(uuid, value) loadedModules[tostring(uuid):lower()] = value == true end,
    }
end

return M
