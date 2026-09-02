local M = {}

local RUNTIME_UUID = "20aca985-e3e9-41d7-bf8f-10f2a3c413e4"
local R0_PACKAGE_SHA256 = "6610090CEE01091F802273D70FAEE071DCBA891900D77479ABBD828FCDDC60C6"

local function lower(value) return tostring(value or ""):lower() end

function M.LegacyRuntimeClaim(cvGuid)
    return {
        ProviderId = "legacy.runtime",
        OwnerModuleUuid = RUNTIME_UUID,
        ProviderDigest = R0_PACKAGE_SHA256,
        ResourceKind = "body_ccsv",
        AddedForCvGuid = cvGuid,
    }
end

local function completeClaim(claim, cvGuid)
    if type(claim) ~= "table" then return false end
    if claim.ProviderId == nil or claim.OwnerModuleUuid == nil or claim.ProviderDigest == nil
        or claim.ResourceKind == nil or claim.AddedForCvGuid == nil then return false end
    if claim.ResourceKind ~= "body_ccsv" and claim.ResourceKind ~= "fallback_ccsv" then return false end
    return lower(claim.AddedForCvGuid) == lower(cvGuid)
end

local function exactClaim(guid, claim, cvGuid, deps)
    if not completeClaim(claim, cvGuid) then return false end
    if claim.ProviderId == "legacy.runtime" then
        return lower(claim.OwnerModuleUuid) == lower(RUNTIME_UUID)
            and tostring(claim.ProviderDigest):upper() == R0_PACKAGE_SHA256
    end
    if deps.validateProviderClaim == nil then return false end
    local ok, valid = pcall(deps.validateProviderClaim, guid, claim)
    return ok and valid == true
end

function M.SubtractOwned(visuals, ownedCcsvs, cvGuid, deps)
    deps = type(deps) == "table" and deps or {}
    local drop = {}
    for guid, claim in pairs(type(ownedCcsvs) == "table" and ownedCcsvs or {}) do
        if exactClaim(guid, claim, cvGuid, deps) then drop[lower(guid)] = true end
    end
    local keep, removed = {}, {}
    for _, guid in ipairs(type(visuals) == "table" and visuals or {}) do
        if drop[lower(guid)] then
            removed[#removed + 1] = guid
        else
            keep[#keep + 1] = guid
        end
    end
    return keep, removed, drop
end

local function arraysEqual(a, b)
    if type(a) ~= "table" or type(b) ~= "table" or #a ~= #b then return false end
    for index, value in ipairs(a) do
        if tostring(value) ~= tostring(b[index]) then return false end
    end
    return true
end

local function addFailure(failures, code)
    failures[#failures + 1] = code
end

local function doRestore(charGuid, record, deps, options)
    local failures = {}
    if deps.isCharacterAvailable ~= nil and deps.isCharacterAvailable(charGuid) ~= true then
        record.RestoreState = "blocked"
        record.RestoreFailures = { "CHARACTER_UNAVAILABLE" }
        if options.makeExternal then record.Choice = "external" end
        return { status = "blocked", failureCodes = record.RestoreFailures }
    end

    local visualsOk = false
    local currentVisuals = deps.readVisuals and deps.readVisuals(charGuid) or nil
    if type(currentVisuals) ~= "table" then
        addFailure(failures, "CCSV_READ_FAILED")
    else
        local keep, _, drop = M.SubtractOwned(currentVisuals, record.OwnedCcsvs, record.CvGuid, deps)
        local writeOk = true
        if not arraysEqual(currentVisuals, keep) then
            writeOk = deps.writeVisuals ~= nil and deps.writeVisuals(charGuid, keep) == true
        end
        local after = writeOk and deps.readVisuals and deps.readVisuals(charGuid) or nil
        if writeOk and arraysEqual(after, keep) then
            visualsOk = true
            for guid in pairs(drop) do
                for ownedGuid in pairs(record.OwnedCcsvs or {}) do
                    if lower(ownedGuid) == guid then record.OwnedCcsvs[ownedGuid] = nil end
                end
            end
            record.AppliedCcsv, record.DesiredCcsv = nil, nil
        else
            addFailure(failures, "CCSV_WRITE_OR_READBACK_FAILED")
        end
    end

    local bodyOk = false
    local liveCv = deps.readCvGuid and deps.readCvGuid(charGuid) or nil
    if record.CvGuid == nil or liveCv == nil or lower(record.CvGuid) ~= lower(liveCv) then
        addFailure(failures, "BODY_CV_MISMATCH")
    elseif record.OrigBodySetVisual == nil
        or deps.validateBodyOriginal == nil
        or deps.validateBodyOriginal(record.OrigBodySetVisual, liveCv, record, charGuid) ~= true then
        addFailure(failures, "ORIGINAL_BODY_UNTRUSTED_OR_MISSING")
    else
        local writeOk = deps.writeBodySetVisual ~= nil
            and deps.writeBodySetVisual(charGuid, liveCv, record.OrigBodySetVisual) == true
        local after = writeOk and deps.readBodySetVisual
            and deps.readBodySetVisual(charGuid, liveCv) or nil
        if writeOk and lower(after) == lower(record.OrigBodySetVisual) then
            bodyOk = true
        else
            addFailure(failures, "BODY_WRITE_OR_READBACK_FAILED")
        end
    end

    local targetEquip
    if record.BodyFamilyId ~= nil then
        targetEquip = record.FamilyOrigEquipRace or record.OrigEquipRace
    else
        targetEquip = record.OrigEquipRace or record.FamilyOrigEquipRace
    end
    local equipOk = false
    if targetEquip == nil or deps.validateEquipRaceOriginal == nil
        or deps.validateEquipRaceOriginal(targetEquip, record, charGuid) ~= true then
        addFailure(failures, "ORIGINAL_EQUIP_RACE_UNTRUSTED_OR_MISSING")
    else
        local writeOk = deps.writeEquipRace ~= nil and deps.writeEquipRace(charGuid, targetEquip) == true
        local after = writeOk and deps.readEquipRace and deps.readEquipRace(charGuid) or nil
        if writeOk and lower(after) == lower(targetEquip) then
            equipOk = true
            record.ClothedChoice = "off"
        else
            addFailure(failures, "EQUIP_RACE_WRITE_OR_READBACK_FAILED")
        end
    end

    if options.makeExternal then record.Choice = "external" end
    local status
    if #failures == 0 and visualsOk and bodyOk and equipOk then
        status = "clean"
    elseif bodyOk or equipOk then
        status = "partial"
    else
        status = "blocked"
    end
    record.RestoreState, record.RestoreFailures = status, failures
    return { status = status, failureCodes = failures }
end

function M.RestoreExternal(charGuid, record, deps, options)
    deps = type(deps) == "table" and deps or {}
    options = type(options) == "table" and options or {}
    local capability = options.capability or "external_restore"
    if type(deps.writeGate) ~= "function" then
        record.RestoreState = "blocked"
        record.RestoreFailures = { "WRITE_GATE_REQUIRED" }
        return { status = "blocked", failureCodes = record.RestoreFailures }
    end
    local accepted, result = deps.writeGate(capability, charGuid, function()
        return doRestore(charGuid, record, deps, options)
    end)
    if type(accepted) == "table" and result == nil then
        result, accepted = accepted, true
    end
    if accepted == false then
        record.RestoreState = "blocked"
        record.RestoreFailures = { "WRITE_GATE_CLOSED" }
        return { status = "blocked", failureCodes = record.RestoreFailures }
    end
    return result
end

return M
