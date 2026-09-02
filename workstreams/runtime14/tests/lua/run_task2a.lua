local script = arg[0]:gsub("\\", "/")
local tests_dir = script:match("^(.*)/[^/]+$")
local lua_dir = assert(arg[1], "explicit Runtime source root required"):gsub("\\", "/")
    .. "/Mods/ClothMorphRuntime/ScriptExtender/Lua"
package.path = tests_dir .. "/?.lua;" .. lua_dir .. "/?.lua;" .. package.path

local T = require("test_support")
local Schema = require("StateSchema7")
local Ledger = require("OwnershipLedger")
local Master = require("MasterState")
local Foundation = require("R1Foundation")

local CHAR_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
local CHAR_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
local CV_A = "11111111-1111-1111-1111-111111111111"
local CV_B = "22222222-2222-2222-2222-222222222222"
local BODY_A = "33333333-3333-3333-3333-333333333333"
local BODY_B = "44444444-4444-4444-4444-444444444444"
local EQUIP_A = "55555555-5555-5555-5555-555555555555"
local EQUIP_B = "66666666-6666-6666-6666-666666666666"
local OWNED_LEGACY = "77777777-7777-7777-7777-777777777777"
local OWNED_PROVIDER = "88888888-8888-8888-8888-888888888888"
local UNRELATED_A = "99999999-9999-9999-9999-999999999999"
local UNRELATED_B = "abababab-abab-abab-abab-abababababab"
local SPOOFED = "cdcdcdcd-cdcd-cdcd-cdcd-cdcdcdcdcdcd"

local function schema_deps()
    return {
        isTrustedBodyOriginal = function(guid)
            return guid == BODY_A or guid == BODY_B
        end,
        isTrustedEquipRaceOriginal = function(guid)
            return guid == EQUIP_A or guid == EQUIP_B
        end,
    }
end

T.test("schema-6 manual fixture migrates every required schema-7 field and exact legacy ownership", function()
    local pv = {
        Version = 6,
        BodyTattooPolicy = "match",
        OptoutTemplates = { keep = true },
        Bodies = {
            [CHAR_A] = {
                Choice = "sbbf",
                AppliedCcsv = OWNED_LEGACY,
                DesiredCcsv = OWNED_LEGACY,
                ClothedChoice = "sbbf",
                OrigBodySetVisual = BODY_A,
                CvGuid = CV_A,
                OrigEquipRace = EQUIP_A,
                OriginalVisuals = { UNRELATED_A, UNRELATED_B },
            },
        },
    }

    local migrated = Schema.Migrate(pv, schema_deps())
    T.equal(migrated.Version, 7)
    T.truthy(migrated.MasterEnabled)
    T.falsy(migrated.MutationGateClosed)
    T.equal(migrated.MasterState, "enabled")
    T.falsy(migrated.PassThroughRestoreComplete)
    T.equal(migrated.MasterTransition, nil)
    T.equal(migrated.CleanupState, "idle")
    T.equal(migrated.CleanupTransaction, nil)
    T.deep_equal(migrated.OptoutTemplates, { keep = true })
    T.deep_equal(migrated.ProviderDescriptors, {})
    T.equal(migrated.BodyTattooPolicy, "match")
    T.equal(migrated.CleanupAudit, nil)

    local rec = migrated.Bodies[CHAR_A]
    T.equal(rec.Choice, "sbbf")
    T.equal(rec.PreferredChoice, "sbbf")
    T.equal(rec.OrigBodySetVisual, BODY_A)
    T.equal(rec.CvGuid, CV_A)
    T.equal(rec.OrigEquipRace, EQUIP_A)
    T.equal(rec.FamilyOrigEquipRace, nil)
    T.deep_equal(rec.OriginalVisuals, { UNRELATED_A, UNRELATED_B })
    T.deep_equal(rec.RemovedOriginalVisuals, {})
    T.equal(rec.AppliedCcsv, OWNED_LEGACY)
    T.equal(rec.DesiredCcsv, OWNED_LEGACY)
    T.equal(rec.ClothedChoice, "sbbf")
    T.equal(rec.BodyFamilyId, nil)
    T.equal(rec.FamilyClothedChoice, nil)
    T.equal(rec.Transition, nil)
    T.equal(rec.RestoreState, "clean")
    T.deep_equal(rec.RestoreFailures, {})
    T.equal(rec.ActiveProvider, nil)
    T.equal(rec.ProviderTransition, nil)
    T.deep_equal(rec.HistoricalOriginals, {})
    T.deep_equal(rec.OwnedCcsvs[OWNED_LEGACY], {
        ProviderId = "legacy.runtime",
        OwnerModuleUuid = Schema.RUNTIME_UUID,
        ProviderDigest = Schema.R0_PACKAGE_SHA256,
        ResourceKind = "body_ccsv",
        AddedForCvGuid = CV_A,
    })
end)

T.test("Honour-like reverted fixture becomes External without inventing ownership", function()
    local pv = {
        Version = 6,
        BodyTattooPolicy = "hide",
        Bodies = {
            [CHAR_B] = {
                Choice = "bcb",
                Reverted = true,
                OrigBodySetVisual = BODY_B,
                CvGuid = CV_B,
                FamilyOrigEquipRace = EQUIP_B,
                SavedCcsvs = { UNRELATED_A, UNRELATED_B },
            },
        },
    }
    Schema.Migrate(pv, schema_deps())
    local rec = pv.Bodies[CHAR_B]
    T.equal(rec.Choice, "external")
    T.equal(rec.PreferredChoice, "vanilla")
    T.deep_equal(rec.OwnedCcsvs, {})
    T.equal(pv.BodyTattooPolicy, "always_hide")
    T.equal(rec.RestoreState, "clean")
end)

T.test("migration rejects minted or missing originals, records stable health, and is idempotent", function()
    local pv = {
        Version = 6,
        Bodies = {
            [CHAR_A] = {
                Choice = "vanilla",
                OrigBodySetVisual = "runtime-minted-body",
                CvGuid = CV_A,
                OrigEquipRace = EQUIP_A,
            },
            [CHAR_B] = {
                Choice = "bcb",
                OrigBodySetVisual = "runtime-minted-body",
                CvGuid = CV_B,
                OrigEquipRace = "runtime-minted-equipment-race",
            },
        },
    }
    Schema.Migrate(pv, schema_deps())
    T.equal(pv.Bodies[CHAR_A].OrigBodySetVisual, nil)
    T.equal(pv.Bodies[CHAR_A].OrigEquipRace, EQUIP_A)
    T.equal(pv.Bodies[CHAR_A].RestoreState, "partial")
    T.deep_equal(pv.Bodies[CHAR_A].RestoreFailures, { "ORIGINAL_BODY_UNTRUSTED_OR_MISSING" })
    T.equal(pv.Bodies[CHAR_B].OrigBodySetVisual, nil)
    T.equal(pv.Bodies[CHAR_B].OrigEquipRace, nil)
    T.equal(pv.Bodies[CHAR_B].RestoreState, "blocked")
    T.deep_equal(pv.Bodies[CHAR_B].RestoreFailures, {
        "ORIGINAL_BODY_UNTRUSTED_OR_MISSING",
        "ORIGINAL_EQUIP_RACE_UNTRUSTED_OR_MISSING",
    })
    local once = T.copy(pv)
    Schema.Migrate(pv, schema_deps())
    T.deep_equal(pv, once, "second migration changed schema-7 state")
end)

local function claim(providerId, owner, digest, resourceKind, cv)
    return {
        ProviderId = providerId,
        OwnerModuleUuid = owner,
        ProviderDigest = digest,
        ResourceKind = resourceKind,
        AddedForCvGuid = cv,
    }
end

local function external_fixture()
    return {
        Choice = "sbbf",
        PreferredChoice = "sbbf",
        OrigBodySetVisual = BODY_A,
        CvGuid = CV_A,
        OrigEquipRace = EQUIP_A,
        OriginalVisuals = {},
        OwnedCcsvs = {
            [OWNED_LEGACY] = Ledger.LegacyRuntimeClaim(CV_A),
            [OWNED_PROVIDER] = claim("provider.one", "provider-owner", "provider-digest", "body_ccsv", CV_A),
            [SPOOFED] = claim("legacy.runtime", Schema.RUNTIME_UUID, "wrong-digest", "body_ccsv", CV_A),
        },
        RemovedOriginalVisuals = {},
        AppliedCcsv = OWNED_LEGACY,
        DesiredCcsv = OWNED_LEGACY,
        ClothedChoice = "sbbf",
        RestoreState = "pending",
        RestoreFailures = {},
        HistoricalOriginals = {},
    }
end

local function restoration_adapters(live, writes)
    return {
        isCharacterAvailable = function() return live.available ~= false end,
        readVisuals = function() return T.copy(live.visuals) end,
        writeVisuals = function(_, value)
            live.visuals = T.copy(value); writes[#writes + 1] = "visuals"; return true
        end,
        readCvGuid = function() return live.cv end,
        validateBodyOriginal = function(guid, cv) return guid == BODY_A and cv == CV_A end,
        writeBodySetVisual = function(_, cv, guid)
            live.body, live.bodyCv = guid, cv; writes[#writes + 1] = "body"; return true
        end,
        readBodySetVisual = function() return live.body end,
        validateEquipRaceOriginal = function(guid) return guid == EQUIP_A end,
        writeEquipRace = function(_, guid)
            live.equip = guid; writes[#writes + 1] = "equip"; return true
        end,
        readEquipRace = function() return live.equip end,
        validateProviderClaim = function(guid, resourceClaim)
            return guid == OWNED_PROVIDER
                and resourceClaim.ProviderId == "provider.one"
                and resourceClaim.ProviderDigest == "provider-digest"
        end,
    }
end

T.test("External subtracts only exact owned CCSVs, preserves unrelated order, and restores matching originals", function()
    local rec = external_fixture()
    local live = {
        available = true,
        cv = CV_A,
        visuals = { UNRELATED_A, OWNED_LEGACY, UNRELATED_B, OWNED_PROVIDER, UNRELATED_A, SPOOFED },
        body = "managed-body",
        equip = "managed-equip",
    }
    local writes = {}
    local adapters = restoration_adapters(live, writes)
    adapters.writeGate = function(mode, char, fn)
        T.equal(mode, "external_restore")
        T.equal(char, CHAR_A)
        return fn()
    end
    local result = Ledger.RestoreExternal(CHAR_A, rec, adapters, {
        capability = "external_restore", makeExternal = true,
    })
    T.equal(result.status, "clean")
    T.deep_equal(live.visuals, { UNRELATED_A, UNRELATED_B, UNRELATED_A, SPOOFED })
    T.equal(live.body, BODY_A)
    T.equal(live.bodyCv, CV_A)
    T.equal(live.equip, EQUIP_A)
    T.equal(rec.Choice, "external")
    T.equal(rec.PreferredChoice, "sbbf")
    T.equal(rec.AppliedCcsv, nil)
    T.equal(rec.DesiredCcsv, nil)
    T.equal(rec.OwnedCcsvs[OWNED_LEGACY], nil)
    T.equal(rec.OwnedCcsvs[OWNED_PROVIDER], nil)
    T.truthy(rec.OwnedCcsvs[SPOOFED] ~= nil)
    T.deep_equal(writes, { "visuals", "body", "equip" })
end)

T.test("External refuses a mismatched CvGuid body restore but still completes independent safe work", function()
    local rec = external_fixture()
    local live = { available = true, cv = CV_B, visuals = { OWNED_LEGACY }, body = "managed", equip = "managed" }
    local writes = {}
    local adapters = restoration_adapters(live, writes)
    adapters.writeGate = function(_, _, fn) return fn() end
    local result = Ledger.RestoreExternal(CHAR_A, rec, adapters, { capability = "external_restore" })
    T.equal(result.status, "partial")
    T.equal(live.body, "managed")
    T.equal(live.equip, EQUIP_A)
    T.deep_equal(live.visuals, {})
    T.deep_equal(rec.RestoreFailures, { "BODY_CV_MISMATCH" })
end)

local function managed_record(choice, body, cv, equip)
    return {
        Choice = choice,
        PreferredChoice = choice,
        OrigBodySetVisual = body,
        CvGuid = cv,
        OrigEquipRace = equip,
        OriginalVisuals = {}, OwnedCcsvs = {}, RemovedOriginalVisuals = {},
        RestoreState = "clean", RestoreFailures = {}, HistoricalOriginals = {},
    }
end

local function schema7_state()
    local state = {
        Version = 7, MasterEnabled = true, MutationGateClosed = false,
        MasterState = "enabled", PassThroughRestoreComplete = false,
        CleanupState = "idle", Bodies = {
            [CHAR_A] = managed_record("sbbf", BODY_A, CV_A, EQUIP_A),
            [CHAR_B] = managed_record("bcb", BODY_B, CV_B, EQUIP_B),
        }, OptoutTemplates = {}, ProviderDescriptors = {}, BodyTattooPolicy = "match",
    }
    return state
end

T.test("ordinary master-off persists the closed gate first, restores independently, and never rolls back or commits cleanup", function()
    local state = schema7_state()
    local persisted, restored = {}, {}
    local runtime = Master.New(state, {
        persist = function(current, reason)
            persisted[#persisted + 1] = { reason = reason, state = T.copy(current) }
        end,
        restoreExternal = function(char, rec, capability)
            restored[#restored + 1] = char
            if char == CHAR_B then
                rec.RestoreState = "blocked"
                rec.RestoreFailures = { "CHARACTER_UNAVAILABLE" }
                return { status = "blocked", failureCodes = rec.RestoreFailures }
            end
            rec.RestoreState, rec.RestoreFailures = "clean", {}
            return { status = "clean", failureCodes = {} }
        end,
    })
    local result = runtime:SetMasterEnabled(false)
    T.equal(persisted[1].reason, "master-off-gated")
    T.falsy(persisted[1].state.MasterEnabled)
    T.truthy(persisted[1].state.MutationGateClosed)
    T.equal(persisted[1].state.MasterState, "off_restoring")
    T.falsy(persisted[1].state.PassThroughRestoreComplete)
    T.equal(persisted[1].state.CleanupState, "idle")
    T.deep_equal(restored, { CHAR_A, CHAR_B })
    T.equal(result.masterState, "off_partial")
    T.deep_equal(result.cleanGuids, { CHAR_A })
    T.deep_equal(result.blockedGuids, { CHAR_B })
    T.falsy(state.PassThroughRestoreComplete)
    T.equal(state.CleanupState, "idle")
    T.equal(state.CleanupTransaction, nil)
    T.equal(state.CommitMarker, nil)
    T.equal(state.Bodies[CHAR_A].RestoreState, "clean")
end)

T.test("ordinary master-off reaches exact pass-through complete only when all tracked records are clean", function()
    local state = schema7_state()
    local calls = 0
    local runtime = Master.New(state, {
        persist = function() end,
        restoreExternal = function(_, rec)
            calls = calls + 1; rec.RestoreState, rec.RestoreFailures = "clean", {}
            return { status = "clean", failureCodes = {} }
        end,
    })
    local first = runtime:SetMasterEnabled(false)
    T.equal(first.masterState, "off_restored")
    T.truthy(state.PassThroughRestoreComplete)
    T.equal(calls, 2)
    local second = runtime:SetMasterEnabled(false)
    T.equal(second.status, "IDEMPOTENT")
    T.equal(calls, 2)
end)

T.test("re-enable applies records independently and leaves a failed character External without rolling back success", function()
    local state = schema7_state()
    state.MasterEnabled = false
    state.MutationGateClosed = true
    state.MasterState = "off_partial"
    state.Bodies[CHAR_B].RestoreState = "blocked"
    local applied = {}
    local runtime = Master.New(state, {
        persist = function() end,
        applyManaged = function(char, rec, choice)
            applied[#applied + 1] = char .. ":" .. choice
            return char == CHAR_A
        end,
    })
    local result = runtime:SetMasterEnabled(true)
    T.equal(result.masterState, "enabled")
    T.truthy(state.MasterEnabled)
    T.falsy(state.MutationGateClosed)
    T.equal(state.Bodies[CHAR_A].Choice, "sbbf")
    T.equal(state.Bodies[CHAR_B].Choice, "external")
    T.equal(state.Bodies[CHAR_B].PreferredChoice, "bcb")
    T.deep_equal(applied, { CHAR_A .. ":sbbf", CHAR_B .. ":bcb" })
end)

T.test("common gate suppresses body, equip, load, MCM, and body-family reapply for External", function()
    local state = schema7_state()
    state.Bodies[CHAR_A].Choice = "external"
    local runtime = Master.New(state, { persist = function() end })
    local ran = {}
    for _, entryPoint in ipairs({ "body", "equip", "load", "mcm", "body_family" }) do
        local ok = runtime:ManagedWrite(entryPoint, CHAR_A, function() ran[#ran + 1] = entryPoint end)
        T.falsy(ok, entryPoint .. " should be suppressed")
    end
    T.deep_equal(ran, {})
    state.Bodies[CHAR_A].Choice = "sbbf"
    local ok = runtime:ManagedWrite("body", CHAR_A, function() ran[#ran + 1] = "body"; return "ok" end)
    T.truthy(ok)
    T.deep_equal(ran, { "body" })
end)

T.test("explicit per-character External preserves PreferredChoice and closes every managed path", function()
    local state = schema7_state()
    local restored = 0
    local runtime = Master.New(state, {
        persist = function() end,
        restoreExternal = function(_, rec)
            restored = restored + 1
            rec.RestoreState, rec.RestoreFailures = "clean", {}
            return { status = "clean", failureCodes = {} }
        end,
    })
    local result = runtime:SetExternal(CHAR_A)
    T.equal(result.status, "clean")
    T.equal(restored, 1)
    T.equal(state.Bodies[CHAR_A].Choice, "external")
    T.equal(state.Bodies[CHAR_A].PreferredChoice, "sbbf")
    T.falsy(runtime:ManagedWrite("mcm", CHAR_A, function() error("must not run") end))
    local repeated = runtime:SetExternal(CHAR_A)
    T.equal(repeated.status, "IDEMPOTENT")
    T.equal(restored, 1)
end)

T.test("foundation installer publishes the exact R1 API diagnostics and common gate", function()
    local state = schema7_state()
    local mod = {}
    local installed = Foundation.Install(mod, state, {
        schema = schema_deps(),
        persist = function() end,
        restoreExternal = function(_, rec)
            rec.RestoreState, rec.RestoreFailures = "clean", {}
            return { status = "clean", failureCodes = {} }
        end,
        applyManaged = function() return true end,
    })
    T.truthy(type(mod.SetMasterEnabled) == "function")
    T.truthy(type(mod.SetExternal) == "function")
    T.truthy(type(mod.GetStateDiagnostics) == "function")
    T.equal(mod.PersistentSchema, 7)
    T.equal(mod.PassThroughApiVersion, 1)
    T.equal(mod.ExternalRefitApiVersion, 1)
    T.equal(mod.BodyFamilyApiVersion, 1)
    T.equal(mod.ProviderRegistrySnapshotApiVersion, 1)
    T.equal(mod.CleanupApiVersion, 0)
    T.equal(mod.RuntimeCodeVersion, "v4.22-s7-foundation")
    T.truthy(installed:CanManagedWrite("body", CHAR_A))
    mod.SetExternal(CHAR_A)
    T.falsy(installed:CanManagedWrite("body", CHAR_A))
    local diagnostics = mod.GetStateDiagnostics()
    T.equal(diagnostics.PackageVersion64, "36451011631513600")
    T.equal(diagnostics.PackageSemver, "1.3.1.0")
    T.equal(diagnostics.RuntimeCodeVersion, "v4.22-s7-foundation")
    T.equal(diagnostics.PersistentSchema, 7)
    T.equal(diagnostics.ScriptExtenderRequiredVersion, 20)
    T.equal(diagnostics.PassThroughApiVersion, 1)
    T.equal(diagnostics.ExternalRefitApiVersion, 1)
    T.equal(diagnostics.BodyFamilyApiVersion, 1)
    T.equal(diagnostics.ProviderRegistrySnapshotApiVersion, 1)
    T.equal(diagnostics.CleanupApiVersion, 0)
    T.truthy(type(mod.GetProviderRegistrySnapshot) == "function")
end)

T.test("foundation refreshes a replaced PersistentVars table before every public or gate entry", function()
    local first = schema7_state()
    local second = schema7_state()
    second.Bodies[CHAR_A].Choice = "external"
    local current = first
    local mod = {}
    local installed = Foundation.Install(mod, first, {
        schema = schema_deps(),
        getState = function() return current end,
        persist = function() end,
    })
    T.truthy(installed:CanManagedWrite("body", CHAR_A))
    current = second
    T.falsy(installed:CanManagedWrite("body", CHAR_A))
    T.equal(mod.GetStateDiagnostics().ExternalGuids[1], CHAR_A)
end)

T.test("MCM forwards External and ordinary master state while apply-on-load obeys the injected gate", function()
    local subscribed
    local tick = 10000
    _G.ModuleUUID = "test-runtime"
    _G.Ext = {
        Utils = { MonotonicTime = function() tick = tick + 2000; return tick end },
        ModEvents = { BG3MCM = { MCM_Setting_Saved = {
            Subscribe = function(_, fn) subscribed = fn end,
        } } },
    }
    package.loaded.MCMIntegration = nil
    local Mcm = require("MCMIntegration")
    local forwarded = {}
    Mcm.InstallClient({
        Log = function() end, Warn = function() end,
        IsValid = function(choice)
            return choice == "vanilla" or choice == "sbbf" or choice == "bcb" or choice == "external"
        end,
        Forward = function(command, value) forwarded[#forwarded + 1] = command .. ":" .. tostring(value) end,
    })
    subscribed({ modUUID = "test-runtime", settingId = "body_choice", value = "External" })
    subscribed({ modUUID = "test-runtime", settingId = "master_enabled", value = false })
    T.deep_equal(forwarded, { "mcm_setbody:external", "mcm_setmaster:off" })

    local applied = 0
    _G.MCM = { Get = function(id)
        if id == "apply_on_load" then return true end
        if id == "body_choice" then return "SBBF" end
    end }
    Mcm.ApplyOnLoad({
        Log = function() end, Warn = function() end,
        IsValid = function(choice) return choice == "sbbf" end,
        ResolveMcmTarget = function() return CHAR_A end,
        CanApplyOnLoad = function() return false end,
        SetDesiredBody = function() applied = applied + 1 end,
    })
    T.equal(applied, 0)
end)

io.write(("TASK2A_LUA_PASS %d/%d\n"):format(T.passed, T.total))
