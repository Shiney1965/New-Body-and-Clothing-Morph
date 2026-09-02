local script = debug.getinfo(1, "S").source:sub(2):gsub("\\", "/")
local testsDir = script:match("^(.*)/[^/]+$")
package.path = testsDir .. "/?.lua;" .. package.path

local T = require("test_support")
local Fixture = require("bootstrap_fixture")
local I = Fixture.ids

local OWNER = "99999999-9999-4999-8999-999999999999"

local function externalMaps(target)
    return {
        vanilla = { ["source-vr-a"] = target },
        sbbf = { ["source-vr-a"] = target },
        bcb = { ["source-vr-a"] = target },
    }
end

T.test("production Bootstrap returns ACTIVE only after one atomic legacy provider commit", function()
    local boot = Fixture.Boot()
    T.equal(type(boot.loadedProductionModuleHashes["RuntimeRollback.lua"]), "string")
    T.equal(#boot.loadedProductionModuleHashes["RuntimeRollback.lua"], 64)
    T.equal(boot.loadedProductionModuleHashes["RuntimeRollback.lua"],
        boot.expectedProductionModuleHashes["RuntimeRollback.lua"])
    local result = boot.registerExternalRefits("Provider Alpha", externalMaps(I.runtimeBody), {
        providerId = "provider.alpha",
        ownerModuleUuid = OWNER,
    })

    T.equal(type(result), "table")
    T.equal(result.ok, true)
    T.equal(result.status, "ACTIVE")
    T.equal(result.providerId, "provider.alpha")
    T.equal(result.ownerModuleUuid, OWNER)
    T.equal(result.activationState, "active")
    T.equal(type(result.canonicalDigest), "string")
    T.equal(#result.canonicalDigest, 64)
    T.equal(boot.registrationCalls(), 1)

    local descriptor = boot.state.ProviderDescriptors["provider.alpha"]
    T.equal(descriptor.canonicalDigest, result.canonicalDigest)
    T.equal(descriptor.activationState, "active")
    T.equal(descriptor.apiGeneration, "legacy_v1")
end)

T.test("same provider owner and digest is IDEMPOTENT without a second commit", function()
    local boot = Fixture.Boot()
    local maps = externalMaps(I.runtimeBody)
    local info = { providerId = "provider.alpha", ownerModuleUuid = OWNER }
    local first = boot.registerExternalRefits("Provider Alpha", maps, info)
    local second = boot.registerExternalRefits("Provider Alpha", maps, info)
    T.equal(first.status, "ACTIVE")
    T.equal(second.status, "IDEMPOTENT")
    T.equal(second.activationState, "active")
    T.equal(boot.registrationCalls(), 1)
end)

T.test("rejected queued provider retries when its requirements become available", function()
    local unavailable = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    local boot = Fixture.Boot()
    boot.mod.SetMasterEnabled(false)
    local info = {
        providerId = "provider.retry", ownerModuleUuid = OWNER,
        requiredModuleUuids = { unavailable },
    }
    local queued = boot.registerExternalRefits("Provider Retry", externalMaps(I.runtimeBody), info)
    T.equal(queued.status, "QUEUED_MASTER_OFF")
    local enabled = boot.mod.SetMasterEnabled(true)
    T.equal(enabled.providerActivationResults[1].status, "REQUIRED_MODULE_UNAVAILABLE")
    T.equal(boot.state.ProviderDescriptors["provider.retry"].activationState, "rejected")
    boot.setModuleLoaded(unavailable, true)
    local retried = boot.registerExternalRefits("Provider Retry", externalMaps(I.runtimeBody), info)
    T.equal(retried.status, "ACTIVE")
    T.equal(retried.ok, true)
    T.equal(boot.registrationCalls(), 1)
end)

T.test("ordinary master-off queues exact descriptors and re-enables in providerId lexical order", function()
    local boot = Fixture.Boot()
    boot.mod.SetMasterEnabled(false)
    local beta = boot.registerExternalRefits("Provider Beta", externalMaps(I.runtimeBody), {
        providerId = "provider.beta", ownerModuleUuid = OWNER,
    })
    local alpha = boot.registerExternalRefits("Provider Alpha", externalMaps(I.runtimeBody), {
        providerId = "provider.alpha", ownerModuleUuid = OWNER,
    })
    T.equal(beta.status, "QUEUED_MASTER_OFF")
    T.equal(alpha.status, "QUEUED_MASTER_OFF")
    T.equal(boot.registrationCalls(), 0)
    T.equal(boot.state.ProviderDescriptors["provider.alpha"].activationState, "queued")

    local enabled = boot.mod.SetMasterEnabled(true)
    T.equal(enabled.providerActivationResults[1].providerId, "provider.alpha")
    T.equal(enabled.providerActivationResults[1].status, "ACTIVE")
    T.equal(enabled.providerActivationResults[2].providerId, "provider.beta")
    T.equal(boot.registrationCalls(), 2)
    T.deep_equal(boot.registrationOrder, { "provider.alpha", "provider.beta" })
end)

T.test("cleanup states reject provider registration without descriptor maps queue or READY", function()
    for _, cleanupState in ipairs({ "disable_requested", "cleanup_disabled" }) do
        local state = {
            Version = 7, MasterEnabled = false, MutationGateClosed = true,
            MasterState = "off_restored", PassThroughRestoreComplete = true,
            CleanupState = cleanupState, CleanupTransaction = nil,
            MasterTransition = nil, Bodies = {}, OptoutTemplates = {},
            ProviderDescriptors = {}, BodyTattooPolicy = "match", CleanupAudit = nil,
        }
        local boot = Fixture.Boot({ state = state })
        local rejected = boot.registerExternalRefits("Provider Alpha", externalMaps(I.runtimeBody), {
            providerId = "provider.alpha", ownerModuleUuid = OWNER,
        })
        T.equal(rejected.status, "REJECTED_CLEANUP_DISABLED")
        T.equal(rejected.activationState, "rejected")
        T.equal(boot.state.ProviderDescriptors["provider.alpha"], nil)
        T.equal(boot.registrationCalls(), 0)
        for _, line in ipairs(boot.logs) do T.falsy(line:find("READY", 1, true) ~= nil) end
    end
end)

T.test("digest environment and collision failures add no descriptor or delegate commit", function()
    local unavailable = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    local boot = Fixture.Boot({
        existingTargets = {
            vanilla = { ["collision-source"] = "existing-target" }, sbbf = {}, bcb = {},
        },
    })
    local badDigest = boot.registerExternalRefits("Bad Digest", externalMaps(I.runtimeBody), {
        providerId = "provider.digest", ownerModuleUuid = OWNER,
        canonicalDigest = string.rep("0", 64),
    })
    T.equal(badDigest.status, "DIGEST_MISMATCH")

    local missingModule = boot.registerExternalRefits("Missing Module", externalMaps(I.runtimeBody), {
        providerId = "provider.environment", ownerModuleUuid = OWNER,
        requiredModuleUuids = { unavailable },
    })
    T.equal(missingModule.status, "REQUIRED_MODULE_UNAVAILABLE")

    local collision = boot.registerExternalRefits("Collision", {
        vanilla = { ["collision-source"] = I.runtimeBody }, sbbf = {}, bcb = {},
    }, { providerId = "provider.collision", ownerModuleUuid = OWNER })
    T.equal(collision.status, "SOURCE_COLLISION")
    T.equal(boot.registrationCalls(), 0)
    T.deep_equal(boot.state.ProviderDescriptors, {})
end)

T.test("queued digest drift fails re-enable without any delegate or partial descriptor activation", function()
    local boot = Fixture.Boot()
    boot.mod.SetMasterEnabled(false)
    local queued = boot.registerExternalRefits("Provider Alpha", externalMaps(I.runtimeBody), {
        providerId = "provider.alpha", ownerModuleUuid = OWNER,
    })
    T.equal(queued.status, "QUEUED_MASTER_OFF")
    boot.state.ProviderDescriptors["provider.alpha"].canonicalDigest = string.rep("F", 64)
    local enabled = boot.mod.SetMasterEnabled(true)
    T.equal(enabled.providerActivationResults[1].status, "DIGEST_DRIFT")
    T.equal(boot.registrationCalls(), 0)
    T.equal(boot.state.ProviderDescriptors["provider.alpha"].activationState, "rejected")
end)

T.test("provider registry snapshot is version 1 sorted deeply immutable and zero-write", function()
    local boot = Fixture.Boot()
    boot.registerExternalRefits("Provider Zeta", externalMaps(I.runtimeBody), {
        providerId = "provider.zeta", ownerModuleUuid = OWNER,
    })
    boot.registerExternalRefits("Provider Alpha", externalMaps(I.runtimeBody), {
        providerId = "provider.alpha", ownerModuleUuid = OWNER,
    })
    boot.registerExternalRefits("Rejected", externalMaps(I.runtimeBody), {
        providerId = "provider.rejected", ownerModuleUuid = OWNER,
        canonicalDigest = string.rep("0", 64),
    })
    local before = {
        registrations = boot.registrationCalls(), adds = boot.addCalls(),
        visuals = T.copy(boot.readVisuals()), body = boot.readCurrentBody(),
        equip = boot.entity.ServerCharacter.Template.EquipmentRace,
        descriptors = T.copy(boot.state.ProviderDescriptors),
    }

    T.equal(boot.mod.ProviderRegistrySnapshotApiVersion, 1)
    local snapshot = boot.mod.GetProviderRegistrySnapshot()
    local consoleSnapshot = boot.console.cm_providerregistry()
    T.equal(snapshot.apiVersion, 1)
    T.equal(snapshot.PackageVersion64, "36451011631513600")
    T.equal(snapshot.RuntimeCodeVersion, "v4.22-s7-foundation")
    T.equal(snapshot.PersistentSchema, 7)
    T.equal(snapshot.descriptors[1].providerId, "provider.alpha")
    T.equal(snapshot.descriptors[2].providerId, "provider.zeta")
    T.equal(snapshot.descriptors[1].kind, "external_refits")
    T.equal(snapshot.descriptors[1].apiGeneration, "legacy_v1")
    T.equal(snapshot.descriptors[1].ownerModuleUuid, OWNER)
    T.equal(snapshot.descriptors[1].activationState, "active")
    T.equal(type(snapshot.descriptors[1].sourceKeys), "table")
    T.equal(type(snapshot.descriptors[1].targetKeysByChoice), "table")
    T.equal(snapshot.rejectedAttempts[1].status, "DIGEST_MISMATCH")
    T.deep_equal(consoleSnapshot, snapshot)

    snapshot.descriptors[1].sourceKeys[1] = "mutated"
    snapshot.descriptors[1].targetKeysByChoice.vanilla[1] = "mutated"
    snapshot.rejectedAttempts[1].status = "mutated"
    local fresh = boot.mod.GetProviderRegistrySnapshot()
    T.equal(fresh.descriptors[1].sourceKeys[1], "source-vr-a")
    T.equal(fresh.descriptors[1].targetKeysByChoice.vanilla[1], I.runtimeBody)
    T.equal(fresh.rejectedAttempts[1].status, "DIGEST_MISMATCH")

    T.equal(boot.registrationCalls(), before.registrations)
    T.equal(boot.addCalls(), before.adds)
    T.deep_equal(boot.readVisuals(), before.visuals)
    T.equal(boot.readCurrentBody(), before.body)
    T.equal(boot.entity.ServerCharacter.Template.EquipmentRace, before.equip)
    T.deep_equal(boot.state.ProviderDescriptors, before.descriptors)
end)

T.test("successful provider CCSV write binds exact active descriptor ownership before success", function()
    local boot = Fixture.Boot()
    local registered = boot.registerExternalRefits("Body Provider", externalMaps(I.runtimeBody), {
        providerId = "provider.body", ownerModuleUuid = OWNER,
        bodyCcsvs = { I.runtimeCcsv },
    })
    T.equal(registered.status, "ACTIVE")
    T.truthy(boot.mod.SetDesiredBody(I.char, "sbbf"))
    T.deep_equal(boot.state.Bodies[I.char].OwnedCcsvs[I.runtimeCcsv], {
        ProviderId = "provider.body",
        OwnerModuleUuid = OWNER,
        ProviderDigest = registered.canonicalDigest,
        ResourceKind = "body_ccsv",
        AddedForCvGuid = I.cv,
    })
end)

T.test("duplicate provider CCSV ownership is rejected and an ambiguous claim blocks the live write", function()
    local boot = Fixture.Boot()
    local first = boot.registerExternalRefits("Provider One", externalMaps(I.runtimeBody), {
        providerId = "provider.one", ownerModuleUuid = OWNER,
        bodyCcsvs = { I.runtimeCcsv },
    })
    local duplicate = boot.registerExternalRefits("Provider Two", externalMaps(I.runtimeBody), {
        providerId = "provider.two", ownerModuleUuid = OWNER,
        bodyCcsvs = { I.runtimeCcsv },
    })
    T.equal(first.status, "ACTIVE")
    T.equal(duplicate.status, "BODY_CCSV_OWNER_COLLISION")
    T.equal(boot.state.ProviderDescriptors["provider.two"], nil)

    local ambiguous = T.copy(boot.state.ProviderDescriptors["provider.one"])
    ambiguous.providerId = "provider.injected"
    boot.state.ProviderDescriptors[ambiguous.providerId] = ambiguous
    local before = boot.addCalls()
    boot.mod.SetDesiredBody(I.char, "sbbf")
    T.equal(boot.addCalls(), before)
    T.equal(boot.state.Bodies[I.char].OwnedCcsvs[I.runtimeCcsv], nil)
end)

T.test("failed provider CCSV write adds no provider claim", function()
    local boot = Fixture.Boot({ failAddCcsv = I.runtimeCcsv })
    boot.registerExternalRefits("Body Provider", externalMaps(I.runtimeBody), {
        providerId = "provider.body", ownerModuleUuid = OWNER,
        bodyCcsvs = { I.runtimeCcsv },
    })
    boot.mod.SetDesiredBody(I.char, "sbbf")
    T.equal(boot.state.Bodies[I.char].OwnedCcsvs[I.runtimeCcsv], nil)
    T.equal(boot.state.Bodies[I.char].AppliedCcsv, nil)
    T.deep_equal(boot.readVisuals(), {})
end)

T.test("effective External characters receive no provider write during load reapply", function()
    local boot = Fixture.Boot({ characterVisualResolvable = true })
    boot.registerExternalRefits("Body Provider", externalMaps(I.runtimeBody), {
        providerId = "provider.body", ownerModuleUuid = OWNER,
        bodyCcsvs = { I.runtimeCcsv },
    })
    boot.mod.SetExternal(I.char)
    T.equal(boot.state.Bodies[I.char].Choice, "external")
    local before = boot.addCalls()
    boot.listeners.LevelGameplayStarted()
    T.equal(boot.addCalls(), before)
    T.equal(boot.state.Bodies[I.char].OwnedCcsvs[I.runtimeCcsv], nil)
end)

T.test("interrupted provider transition gates managed provider writes", function()
    local boot = Fixture.Boot()
    boot.registerExternalRefits("Body Provider", externalMaps(I.runtimeBody), {
        providerId = "provider.body", ownerModuleUuid = OWNER,
        bodyCcsvs = { I.runtimeCcsv },
    })
    boot.state.Bodies[I.char].ProviderTransition = {
        schema = 1, Phase = "gated", ProviderId = "provider.body",
    }
    local before = boot.addCalls()
    T.falsy(boot.mod.SetDesiredBody(I.char, "sbbf"))
    T.equal(boot.addCalls(), before)
    T.equal(boot.state.Bodies[I.char].OwnedCcsvs[I.runtimeCcsv], nil)
end)

T.test("preserve_managed prepares an exact schema-6 projection without older-package readiness", function()
    local boot = Fixture.Boot({ characterVisualResolvable = true })
    local beforeVisuals = T.copy(boot.readVisuals())
    local beforeBody = boot.readCurrentBody()
    local beforeEquip = boot.entity.ServerCharacter.Template.EquipmentRace
    local unknown = boot.mod.PrepareRuntimeRollbackV1("OTHER", "preserve_managed")
    T.equal(unknown.status, "UNKNOWN_TARGET_ARTIFACT")
    T.falsy(unknown.ok)
    local unsupported = boot.mod.PrepareRuntimeRollbackV1("R0_CURRENT_BASELINE", "other")
    T.equal(unsupported.status, "UNSUPPORTED_ROLLBACK_MODE")
    T.falsy(unsupported.ok)
    local prepared = boot.mod.PrepareRuntimeRollbackV1("R0_CURRENT_BASELINE", "preserve_managed")
    T.equal(prepared.ok, true)
    T.equal(prepared.status, "PREPARED")
    T.equal(prepared.targetArtifactId, "R0_CURRENT_BASELINE")
    T.equal(prepared.mode, "preserve_managed")
    T.equal(prepared.olderPackageReady, false)
    T.equal(prepared.engineSaveCheckpointRequired, true)
    T.equal(type(prepared.evidenceDigest), "string")
    T.equal(#prepared.evidenceDigest, 64)
    T.equal(boot.state.Version, 6)
    local rec = boot.state.Bodies[I.char]
    T.equal(rec.Choice, "sbbf")
    T.equal(rec.Reverted, false)
    T.equal(rec.PreferredChoice, nil)
    T.equal(rec.OwnedCcsvs, nil)
    T.equal(rec.ProviderTransition, nil)
    T.equal(rec.HistoricalOriginals, nil)
    T.deep_equal(boot.readVisuals(), beforeVisuals)
    T.equal(boot.readCurrentBody(), beforeBody)
    T.equal(boot.entity.ServerCharacter.Template.EquipmentRace, beforeEquip)
end)

T.test("network rollback requires host ownership and remains terminally prepared through diagnostics", function()
    local boot = Fixture.Boot()
    boot.channel.handler({ cmd = "prepare_rollback", arg = {
        targetArtifactId = "R0_CURRENT_BASELINE", mode = "preserve_managed",
    } }, nil)
    T.equal(boot.state.Version, 7)

    boot.channel.handler({ cmd = "prepare_rollback", arg = {
        targetArtifactId = "R0_CURRENT_BASELINE", mode = "preserve_managed",
    } }, 0)
    T.equal(boot.state.Version, 6)
    T.equal(boot.state.RollbackPrepared.status, "PREPARED")
    local diagnostics = boot.mod.GetStateDiagnostics()
    T.equal(diagnostics.PersistentSchema, 6)
    T.equal(boot.state.Version, 6)
    T.falsy(boot.mod.SetDesiredBody(I.char, "sbbf"))
    local snapshot = boot.mod.GetProviderRegistrySnapshot()
    T.equal(snapshot.PersistentSchema, 6)
    T.equal(boot.state.ProviderDescriptors, nil)
    local rejected = boot.registerExternalRefits("Prepared Provider", externalMaps(I.runtimeBody), {
        providerId = "provider.prepared", ownerModuleUuid = OWNER,
    })
    T.equal(rejected.status, "REJECTED_ROLLBACK_PREPARED")
    T.equal(boot.state.ProviderDescriptors, nil)
end)

io.write(("TASK2B_BOOTSTRAP_RED_GREEN %d/%d\n"):format(T.passed, T.total))
