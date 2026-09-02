local script = arg[0]:gsub("\\", "/")
local testsDir = script:match("^(.*)/[^/]+$")
package.path = testsDir .. "/?.lua;" .. package.path

local T = require("test_support")
local Fixture = require("bootstrap_fixture")
local I = Fixture.ids

local function hasValue(array, expected)
    for _, value in ipairs(array or {}) do if value == expected then return true end end
    return false
end

T.test("production Bootstrap binds every successful Runtime CCSV write before returning success", function()
    local boot = Fixture.Boot()
    local ok = boot.mod.SetDesiredBody(I.char, "sbbf")
    T.truthy(ok)
    T.equal(boot.addCalls(), 1)
    local rec = boot.state.Bodies[I.char]
    T.deep_equal(rec.OwnedCcsvs[I.runtimeCcsv], {
        ProviderId = "legacy.runtime",
        OwnerModuleUuid = I.runtimeUuid,
        ProviderDigest = "6610090CEE01091F802273D70FAEE071DCBA891900D77479ABBD828FCDDC60C6",
        ResourceKind = "body_ccsv",
        AddedForCvGuid = I.cv,
    })
    T.equal(rec.Choice, "sbbf")
end)

T.test("managed CCSV to Vanilla permanently retires the exact claim after live readback", function()
    local boot = Fixture.Boot()
    T.truthy(boot.mod.SetDesiredBody(I.char, "sbbf"))
    local rec = boot.state.Bodies[I.char]
    T.truthy(rec.OwnedCcsvs[I.runtimeCcsv] ~= nil)

    T.truthy(boot.mod.SetDesiredBody(I.char, "vanilla"))
    T.deep_equal(boot.readVisuals(), {})
    T.equal(rec.AppliedCcsv, nil)
    T.equal(rec.DesiredCcsv, nil)
    T.equal(rec.OwnedCcsvs[I.runtimeCcsv], nil)
end)

T.test("permanent retirement removes only the exact target claim", function()
    local boot = Fixture.Boot()
    T.truthy(boot.mod.SetDesiredBody(I.char, "sbbf"))
    local rec = boot.state.Bodies[I.char]
    rec.OwnedCcsvs[I.runtimeCcsvB] = {
        ProviderId = "legacy.runtime",
        OwnerModuleUuid = I.runtimeUuid,
        ProviderDigest = "6610090CEE01091F802273D70FAEE071DCBA891900D77479ABBD828FCDDC60C6",
        ResourceKind = "body_ccsv",
        AddedForCvGuid = I.cv,
    }

    T.truthy(boot.mod.SetDesiredBody(I.char, "vanilla"))
    T.equal(rec.OwnedCcsvs[I.runtimeCcsv], nil)
    T.truthy(rec.OwnedCcsvs[I.runtimeCcsvB] ~= nil)
end)

T.test("successful base-body adoption permanently retires the legacy CCSV claim", function()
    local boot = Fixture.Boot()
    T.truthy(boot.mod.SetDesiredBody(I.char, "sbbf"))
    local rec = boot.state.Bodies[I.char]
    T.truthy(rec.OwnedCcsvs[I.runtimeCcsv] ~= nil)

    boot.setCurrentBody(I.validBody)
    boot.setCharacterVisualResolvable(true)
    T.truthy(boot.mod.SetDesiredBody(I.char, "sbbf"))
    T.equal(boot.readCurrentBody(), I.runtimeBody)
    T.deep_equal(boot.readVisuals(), {})
    T.equal(rec.AppliedCcsv, nil)
    T.equal(rec.DesiredCcsv, nil)
    T.equal(rec.OwnedCcsvs[I.runtimeCcsv], nil)
end)

T.test("temporary armor concealment preserves ownership while DesiredCcsv remains", function()
    local boot = Fixture.Boot()
    T.truthy(boot.mod.SetDesiredBody(I.char, "sbbf"))
    local rec = boot.state.Bodies[I.char]

    boot.setTorsoCovered(true)
    boot.mod.Reconcile(I.char, "fixture-covered")
    T.deep_equal(boot.readVisuals(), {})
    T.equal(rec.AppliedCcsv, nil)
    T.equal(rec.DesiredCcsv, I.runtimeCcsv)
    T.truthy(rec.OwnedCcsvs[I.runtimeCcsv] ~= nil)

    boot.setTorsoCovered(false)
    boot.mod.Reconcile(I.char, "fixture-uncovered")
    T.deep_equal(boot.readVisuals(), { I.runtimeCcsv })
    T.truthy(rec.OwnedCcsvs[I.runtimeCcsv] ~= nil)
end)

T.test("managed CCSV switch cannot accumulate a stale prior claim", function()
    local boot = Fixture.Boot()
    T.truthy(boot.mod.SetDesiredBody(I.char, "sbbf"))
    local rec = boot.state.Bodies[I.char]
    T.truthy(boot.mod.SetDesiredBody(I.char, "bcb"))
    T.deep_equal(boot.readVisuals(), { I.runtimeCcsvB })
    T.equal(rec.OwnedCcsvs[I.runtimeCcsv], nil)
    T.truthy(rec.OwnedCcsvs[I.runtimeCcsvB] ~= nil)
end)

T.test("failed managed CCSV replacement restores exact prior record and live visual state", function()
    local unrelatedA = "99999999-9999-9999-9999-999999999991"
    local unrelatedB = "99999999-9999-9999-9999-999999999992"
    local boot = Fixture.Boot({
        visuals = { unrelatedA, unrelatedB },
        failAddCcsv = I.runtimeCcsvB,
    })
    T.truthy(boot.mod.SetDesiredBody(I.char, "sbbf"))
    local rec = boot.state.Bodies[I.char]
    local prior = {
        Choice = rec.Choice,
        PreferredChoice = rec.PreferredChoice,
        DesiredCcsv = rec.DesiredCcsv,
        AppliedCcsv = rec.AppliedCcsv,
        OwnedCcsvs = T.copy(rec.OwnedCcsvs),
        Visuals = boot.readVisuals(),
    }
    T.deep_equal(prior.Visuals, { unrelatedA, unrelatedB, I.runtimeCcsv })

    local result = boot.mod.SetDesiredBody(I.char, "bcb")

    T.falsy(result)
    T.equal(rec.Choice, prior.Choice)
    T.equal(rec.PreferredChoice, prior.PreferredChoice)
    T.equal(rec.DesiredCcsv, prior.DesiredCcsv)
    T.equal(rec.AppliedCcsv, prior.AppliedCcsv)
    T.deep_equal(rec.OwnedCcsvs, prior.OwnedCcsvs)
    T.deep_equal(boot.readVisuals(), prior.Visuals)
end)

T.test("failed replacement rollback reports blocked state and closes managed writes", function()
    local unrelated = "99999999-9999-9999-9999-999999999993"
    local boot = Fixture.Boot({
        visuals = { unrelated },
        failAddCcsv = I.runtimeCcsvB,
        rollbackReadbackAfterAddFailure = { unrelated },
    })
    T.truthy(boot.mod.SetDesiredBody(I.char, "sbbf"))

    T.falsy(boot.mod.SetDesiredBody(I.char, "bcb"))
    local rec = boot.state.Bodies[I.char]
    T.equal(rec.RestoreState, "blocked")
    T.truthy(hasValue(rec.RestoreFailures, "MANAGED_REAPPLY_ROLLBACK_FAILED"))
    T.truthy(hasValue(boot.mod.GetStateDiagnostics().BlockedGuids, I.char))

    local addCalls = boot.addCalls()
    T.falsy(boot.mod.SetDesiredBody(I.char, "bcb"))
    T.equal(boot.addCalls(), addCalls)
end)

T.test("failed permanent retirement readback preserves live marker and exact claim", function()
    local boot = Fixture.Boot()
    T.truthy(boot.mod.SetDesiredBody(I.char, "sbbf"))
    local rec = boot.state.Bodies[I.char]
    boot.forceVisualReadback({ I.runtimeCcsv })

    boot.mod.SetDesiredBody(I.char, "vanilla")
    T.deep_equal(boot.readVisuals(), { I.runtimeCcsv })
    T.equal(rec.AppliedCcsv, I.runtimeCcsv)
    T.truthy(rec.OwnedCcsvs[I.runtimeCcsv] ~= nil)
end)

T.test("failed Vanilla retirement returns false and preserves prior intent without equipment continuation", function()
    local boot = Fixture.Boot()
    T.truthy(boot.mod.SetDesiredBody(I.char, "sbbf"))
    local rec = boot.state.Bodies[I.char]
    local priorChoice = rec.Choice
    local priorPreferred = rec.PreferredChoice
    local priorDesired = rec.DesiredCcsv
    local priorApplied = rec.AppliedCcsv
    local priorEquip = boot.entity.ServerCharacter.Template.EquipmentRace
    boot.forceVisualReadback({ I.runtimeCcsv })

    local result = boot.mod.SetDesiredBody(I.char, "vanilla")
    T.falsy(result)
    T.equal(rec.Choice, priorChoice)
    T.equal(rec.PreferredChoice, priorPreferred)
    T.equal(rec.DesiredCcsv, priorDesired)
    T.equal(rec.AppliedCcsv, priorApplied)
    T.truthy(rec.OwnedCcsvs[I.runtimeCcsv] ~= nil)
    T.equal(boot.entity.ServerCharacter.Template.EquipmentRace, priorEquip)
end)

T.test("failed base-body retirement returns false before body or equipment continuation", function()
    local boot = Fixture.Boot()
    T.truthy(boot.mod.SetDesiredBody(I.char, "sbbf"))
    local rec = boot.state.Bodies[I.char]
    local priorChoice = rec.Choice
    local priorPreferred = rec.PreferredChoice
    local priorDesired = rec.DesiredCcsv
    local priorApplied = rec.AppliedCcsv
    local priorEquip = boot.entity.ServerCharacter.Template.EquipmentRace
    boot.setCurrentBody(I.validBody)
    boot.setCharacterVisualResolvable(true)
    boot.forceVisualReadback({ I.runtimeCcsv })

    local result = boot.mod.SetDesiredBody(I.char, "bcb")
    T.falsy(result)
    T.equal(boot.readCurrentBody(), I.validBody)
    T.equal(rec.Choice, priorChoice)
    T.equal(rec.PreferredChoice, priorPreferred)
    T.equal(rec.DesiredCcsv, priorDesired)
    T.equal(rec.AppliedCcsv, priorApplied)
    T.truthy(rec.OwnedCcsvs[I.runtimeCcsv] ~= nil)
    T.equal(boot.entity.ServerCharacter.Template.EquipmentRace, priorEquip)
end)

T.test("failed load-time base retirement suppresses the base write", function()
    local boot = Fixture.Boot()
    T.truthy(boot.mod.SetDesiredBody(I.char, "sbbf"))
    local rec = boot.state.Bodies[I.char]
    local priorChoice = rec.Choice
    local priorDesired = rec.DesiredCcsv
    local priorApplied = rec.AppliedCcsv
    boot.setCurrentBody(I.validBody)
    boot.setCharacterVisualResolvable(true)
    boot.forceVisualReadback({ I.runtimeCcsv })

    boot.mod.ReapplyBaseBodies("fixture-load")
    T.equal(boot.readCurrentBody(), I.validBody)
    T.equal(rec.Choice, priorChoice)
    T.equal(rec.DesiredCcsv, priorDesired)
    T.equal(rec.AppliedCcsv, priorApplied)
    T.truthy(rec.OwnedCcsvs[I.runtimeCcsv] ~= nil)
end)

T.test("missing live Visuals readback cannot retire the marker or exact claim", function()
    local boot = Fixture.Boot()
    T.truthy(boot.mod.SetDesiredBody(I.char, "sbbf"))
    local rec = boot.state.Bodies[I.char]
    boot.forceVisualReadbackNil(true)

    boot.mod.SetDesiredBody(I.char, "vanilla")
    T.equal(rec.AppliedCcsv, I.runtimeCcsv)
    T.truthy(rec.OwnedCcsvs[I.runtimeCcsv] ~= nil)
end)

T.test("production Bootstrap refuses a CCSV write when live and saved CvGuid differ", function()
    local liveCv = "99999999-9999-9999-9999-999999999999"
    local boot = Fixture.Boot({ entityCv = liveCv })
    local ok = boot.mod.SetDesiredBody(I.char, "sbbf")
    T.equal(boot.addCalls(), 0)
    T.equal(boot.state.Bodies[I.char].OwnedCcsvs[I.runtimeCcsv], nil)
    T.truthy(ok, "independent clothed half remains allowed")
end)

T.test("production raw CCSV console compatibility command cannot create custom schema choice", function()
    local boot = Fixture.Boot()
    local before = boot.addCalls()
    local result = boot.console.cm_applyccsv("cm_applyccsv", "ffffffff-ffff-ffff-ffff-ffffffffffff", I.char)
    T.falsy(result)
    T.equal(boot.addCalls(), before)
    T.falsy(boot.state.Bodies[I.char].Choice == "custom")
end)

T.test("production public raw CCSV helper cannot create custom schema choice", function()
    local boot = Fixture.Boot()
    local before = boot.addCalls()
    local result = boot.mod.ApplyCcsv(
        I.char, "ffffffff-ffff-ffff-ffff-ffffffffffff", "custom")
    T.falsy(result)
    T.equal(boot.addCalls(), before)
    T.falsy(boot.state.Bodies[I.char].Choice == "custom")
end)

T.test("production seterace compatibility command cannot trust or write an arbitrary GUID", function()
    local boot = Fixture.Boot()
    local rec = boot.state.Bodies[I.char]
    local beforeOriginal = rec.OrigEquipRace
    local beforeLive = boot.entity.ServerCharacter.Template.EquipmentRace
    local result = boot.console.cm_seterace(
        "cm_seterace", "ffffffff-ffff-ffff-ffff-ffffffffffff", I.char)
    T.falsy(result)
    T.equal(rec.OrigEquipRace, beforeOriginal)
    T.equal(boot.entity.ServerCharacter.Template.EquipmentRace, beforeLive)
end)

T.test("production Bootstrap leaves unsupported schema versions unchanged and closes all writes", function()
    for _, version in ipairs({ 0, 5, 8 }) do
        local state = { Version = version, Bodies = {} }
        local boot = Fixture.Boot({ state = state })
        T.equal(boot.state.Version, version)
        local result = boot.mod.SetMasterEnabled(false)
        T.falsy(result.ok)
        T.equal(boot.addCalls(), 0)
    end
end)

T.test("schema-6 AppliedCcsv without CvGuid creates no invalid claim and blocks restoration", function()
    local state = {
        Version = 6,
        Bodies = { [I.char] = {
            Choice = "sbbf",
            AppliedCcsv = I.runtimeCcsv,
            OrigBodySetVisual = I.validBody,
            OrigEquipRace = I.validEquip,
        } },
    }
    local boot = Fixture.Boot({ state = state })
    local rec = boot.state.Bodies[I.char]
    T.equal(rec.OwnedCcsvs[I.runtimeCcsv], nil)
    T.equal(rec.RestoreState, "blocked")
    T.truthy(hasValue(rec.RestoreFailures, "LEGACY_CCSV_CV_GUID_MISSING"))
end)

T.test("schema-6 unresolvable AppliedCcsv cannot become a legacy Runtime claim", function()
    local unknownCcsv = "ffffffff-ffff-ffff-ffff-ffffffffffff"
    local state = {
        Version = 6,
        Bodies = { [I.char] = {
            Choice = "sbbf", AppliedCcsv = unknownCcsv, CvGuid = I.cv,
            OrigBodySetVisual = I.validBody, OrigEquipRace = I.validEquip,
        } },
    }
    local boot = Fixture.Boot({ state = state })
    local rec = boot.state.Bodies[I.char]
    T.equal(rec.OwnedCcsvs[unknownCcsv], nil)
    T.equal(rec.RestoreState, "blocked")
    T.truthy(hasValue(rec.RestoreFailures, "LEGACY_CCSV_UNTRUSTED"))
end)

T.test("malformed schema-7 ownership claim closes production writes", function()
    local state = {
        Version = 7,
        MasterEnabled = true,
        MutationGateClosed = false,
        MasterState = "enabled",
        PassThroughRestoreComplete = false,
        CleanupState = "idle",
        Bodies = { [I.char] = {
            Choice = "sbbf", PreferredChoice = "sbbf",
            OrigBodySetVisual = I.validBody, CvGuid = I.cv, OrigEquipRace = I.validEquip,
            OriginalVisuals = {}, RemovedOriginalVisuals = {},
            OwnedCcsvs = { [I.runtimeCcsv] = {
                ProviderId = "legacy.runtime", OwnerModuleUuid = I.runtimeUuid,
                ProviderDigest = "wrong", ResourceKind = "body_ccsv", AddedForCvGuid = I.cv,
            } },
            RestoreState = "clean", RestoreFailures = {}, HistoricalOriginals = {},
        } },
        OptoutTemplates = {}, ProviderDescriptors = {}, BodyTattooPolicy = "match",
    }
    local boot = Fixture.Boot({ state = state })
    local result = boot.mod.SetMasterEnabled(false)
    T.falsy(result.ok)
    T.equal(boot.addCalls(), 0)
end)

T.test("schema-7 ownership claim with non-GUID identity fields closes production writes", function()
    local state = {
        Version = 7,
        MasterEnabled = true, MutationGateClosed = false, MasterState = "enabled",
        PassThroughRestoreComplete = false, CleanupState = "idle",
        Bodies = { [I.char] = {
            Choice = "sbbf", PreferredChoice = "sbbf",
            OrigBodySetVisual = I.validBody, CvGuid = I.cv, OrigEquipRace = I.validEquip,
            OriginalVisuals = {}, RemovedOriginalVisuals = {},
            OwnedCcsvs = { ["not-a-guid"] = {
                ProviderId = "legacy.runtime", OwnerModuleUuid = I.runtimeUuid,
                ProviderDigest = "6610090CEE01091F802273D70FAEE071DCBA891900D77479ABBD828FCDDC60C6",
                ResourceKind = "body_ccsv", AddedForCvGuid = I.cv,
            } },
            RestoreState = "clean", RestoreFailures = {}, HistoricalOriginals = {},
        } },
        OptoutTemplates = {}, ProviderDescriptors = {}, BodyTattooPolicy = "match",
    }
    local boot = Fixture.Boot({ state = state })
    local result = boot.mod.SetMasterEnabled(false)
    T.falsy(result.ok)
    T.equal(boot.addCalls(), 0)
end)

T.test("production migration rejects unresolved and Runtime-minted originals but preserves proven originals", function()
    local arbitraryBody = "77777777-7777-7777-7777-777777777777"
    local arbitraryEquip = "88888888-8888-8888-8888-888888888888"
    local state = { Version = 6, Bodies = {
        [I.char] = {
            Choice = "sbbf", OrigBodySetVisual = arbitraryBody,
            CvGuid = I.cv, OrigEquipRace = arbitraryEquip,
        },
    } }
    local rejected = Fixture.Boot({ state = state, currentEquip = I.validEquip })
    T.equal(rejected.state.Bodies[I.char].OrigBodySetVisual, nil)
    T.equal(rejected.state.Bodies[I.char].OrigEquipRace, nil)

    local mintedState = { Version = 6, Bodies = {
        [I.char] = {
            Choice = "sbbf", OrigBodySetVisual = I.runtimeBody,
            CvGuid = I.cv, OrigEquipRace = I.runtimeEquip,
        },
    } }
    local minted = Fixture.Boot({ state = mintedState, currentEquip = I.runtimeEquip })
    T.equal(minted.state.Bodies[I.char].OrigBodySetVisual, nil)
    T.equal(minted.state.Bodies[I.char].OrigEquipRace, nil)

    local valid = Fixture.Boot({ characterVisualResolvable = true, currentBody = I.validBody })
    T.equal(valid.state.Bodies[I.char].OrigBodySetVisual, I.validBody)
    T.equal(valid.state.Bodies[I.char].OrigEquipRace, I.validEquip)
end)

T.test("production migration rejects resolved but unrelated body and current but unregistered EquipmentRace", function()
    local arbitraryBody = "77777777-7777-7777-7777-777777777777"
    local arbitraryEquip = "88888888-8888-8888-8888-888888888888"
    local state = { Version = 6, Bodies = {
        [I.char] = {
            Choice = "sbbf", OrigBodySetVisual = arbitraryBody,
            CvGuid = I.cv, OrigEquipRace = arbitraryEquip,
        },
    } }
    local boot = Fixture.Boot({
        state = state,
        currentEquip = arbitraryEquip,
        characterVisualResolvable = true,
        currentBody = I.validBody,
        bodyResources = {
            [I.validBody] = { SourceFile = "Generated/Public/BCBPak/valid-body.gr2" },
            [arbitraryBody] = { SourceFile = "Generated/Public/SomeOtherMod/arbitrary-body.gr2" },
            [I.runtimeBody] = { SourceFile = "Generated/Public/ClothMorphRuntime/runtime-body.gr2" },
        },
    })
    T.equal(boot.state.Bodies[I.char].OrigBodySetVisual, nil)
    T.equal(boot.state.Bodies[I.char].OrigEquipRace, nil)
end)

T.test("production managed apply cannot capture a Runtime-minted body as a missing original", function()
    local state = {
        Version = 7,
        MasterEnabled = true, MutationGateClosed = false, MasterState = "enabled",
        PassThroughRestoreComplete = false, CleanupState = "idle",
        Bodies = { [I.char] = {
            Choice = "sbbf", PreferredChoice = "sbbf",
            OrigBodySetVisual = nil, CvGuid = nil, OrigEquipRace = I.validEquip,
            OriginalVisuals = {}, RemovedOriginalVisuals = {}, OwnedCcsvs = {},
            RestoreState = "partial", RestoreFailures = { "ORIGINAL_BODY_UNTRUSTED_OR_MISSING" },
            HistoricalOriginals = {},
        } },
        OptoutTemplates = {}, ProviderDescriptors = {}, BodyTattooPolicy = "match",
    }
    local boot = Fixture.Boot({
        state = state,
        characterVisualResolvable = true,
        currentBody = I.runtimeBody,
    })
    boot.mod.SetDesiredBody(I.char, "sbbf")
    T.equal(boot.state.Bodies[I.char].OrigBodySetVisual, nil)
end)

T.test("production diagnostics expose all ten lineage fields without advertising Task-2B registry API", function()
    local boot = Fixture.Boot()
    local diagnostics = boot.mod.GetStateDiagnostics()
    local consoleDiagnostics = boot.console.cm_state()
    local expected = {
        PackageVersion64 = "36451011631513600",
        PackageSemver = "1.3.1.0",
        RuntimeCodeVersion = "v4.22-s7-foundation",
        PersistentSchema = 7,
        ScriptExtenderRequiredVersion = 20,
        PassThroughApiVersion = 1,
        ExternalRefitApiVersion = 1,
        BodyFamilyApiVersion = 1,
        ProviderRegistrySnapshotApiVersion = 1,
        CleanupApiVersion = 0,
    }
    for key, value in pairs(expected) do
        T.equal(diagnostics[key], value, key)
        T.equal(consoleDiagnostics[key], value, "console " .. key)
    end
    T.equal(boot.mod.ProviderRegistrySnapshotApiVersion, 1)
    T.truthy(type(boot.mod.GetProviderRegistrySnapshot) == "function")

    boot.mod.SetMasterEnabled(false)
    local registered = boot.registerExternalRefits("provider", {}, {})
    T.equal(registered.status, "MAPS_EMPTY")
    T.equal(boot.registrationCalls(), 0)
end)

io.write(("TASK2A_BOOTSTRAP_RED_GREEN %d/%d\n"):format(T.passed, T.total))
