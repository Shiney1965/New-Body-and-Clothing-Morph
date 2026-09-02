local M = {}

M.SCHEMA_VERSION = 7
M.RUNTIME_UUID = "20aca985-e3e9-41d7-bf8f-10f2a3c413e4"
M.R0_PACKAGE_SHA256 = "6610090CEE01091F802273D70FAEE071DCBA891900D77479ABBD828FCDDC60C6"

local MANAGED_CHOICES = { vanilla = true, sbbf = true, bcb = true }

local function validDigest(value)
    local text = tostring(value or "")
    return #text == 64 and text:match("^%x+$") ~= nil
end

local function validGuid(value)
    local text = tostring(value or "")
    if #text ~= 36 or text:sub(9, 9) ~= "-" or text:sub(14, 14) ~= "-"
        or text:sub(19, 19) ~= "-" or text:sub(24, 24) ~= "-" then return false end
    local compact = text:gsub("-", "")
    return #compact == 32 and compact:match("^%x+$") ~= nil
end

local function validateClaim(guid, claim, cvGuid)
    if type(claim) ~= "table" then return false end
    if not validGuid(guid) or tostring(claim.ProviderId or "") == ""
        or not validGuid(claim.OwnerModuleUuid) or not validDigest(claim.ProviderDigest)
        or not validGuid(claim.AddedForCvGuid) then return false end
    if claim.ResourceKind ~= "body_ccsv" and claim.ResourceKind ~= "fallback_ccsv" then return false end
    if tostring(claim.AddedForCvGuid):lower() ~= tostring(cvGuid or ""):lower() then return false end
    if claim.ProviderId == "legacy.runtime" then
        return tostring(claim.OwnerModuleUuid):lower() == M.RUNTIME_UUID
            and tostring(claim.ProviderDigest):upper() == M.R0_PACKAGE_SHA256
    end
    return true
end

local function validateSchema7(state)
    if type(state.Bodies) ~= "table" then return false, "SCHEMA7_BODIES_INVALID" end
    for charGuid, rec in pairs(state.Bodies) do
        if type(rec) ~= "table" then
            return false, "SCHEMA7_BODY_RECORD_INVALID:" .. tostring(charGuid)
        end
        if rec.Choice ~= "external" and not MANAGED_CHOICES[rec.Choice] then
            return false, "SCHEMA7_CHOICE_INVALID:" .. tostring(charGuid)
        end
        if not MANAGED_CHOICES[rec.PreferredChoice] then
            return false, "SCHEMA7_PREFERRED_CHOICE_INVALID:" .. tostring(charGuid)
        end
        if type(rec.OwnedCcsvs) ~= "table" then
            return false, "SCHEMA7_OWNED_CCSVS_INVALID:" .. tostring(charGuid)
        end
        for guid, claim in pairs(rec.OwnedCcsvs) do
            if not validateClaim(guid, claim, rec.CvGuid) then
                return false, "SCHEMA7_OWNERSHIP_CLAIM_INVALID:" .. tostring(charGuid)
                    .. ":" .. tostring(guid)
            end
        end
    end
    return true
end

local function normalizePolicy(value)
    if value == "always_show" or value == "show" then return "always_show" end
    if value == "always_hide" or value == "hide" then return "always_hide" end
    return "match"
end

local function cloneArray(value)
    local out = {}
    if type(value) == "table" then
        for index, item in ipairs(value) do out[index] = item end
    end
    return out
end

local function trustedBody(rec, charGuid, deps)
    local guid = rec.OrigBodySetVisual
    if guid == nil or guid == "" or rec.CvGuid == nil or rec.CvGuid == "" then return nil end
    if deps.isTrustedBodyOriginal == nil then return guid end
    local ok, trusted = pcall(deps.isTrustedBodyOriginal, guid, rec.CvGuid, rec, charGuid)
    if ok and trusted == true then return guid end
    return nil
end

local function trustedEquip(guid, rec, charGuid, deps)
    if guid == nil or guid == "" then return nil end
    if deps.isTrustedEquipRaceOriginal == nil then return guid end
    local ok, trusted = pcall(deps.isTrustedEquipRaceOriginal, guid, rec, charGuid)
    if ok and trusted == true then return guid end
    return nil
end

local function legacyClaim(cvGuid)
    return {
        ProviderId = "legacy.runtime",
        OwnerModuleUuid = M.RUNTIME_UUID,
        ProviderDigest = M.R0_PACKAGE_SHA256,
        ResourceKind = "body_ccsv",
        AddedForCvGuid = cvGuid,
    }
end

local function initialRestoreHealth(rec)
    local failures = {}
    if rec.OrigBodySetVisual == nil then
        failures[#failures + 1] = "ORIGINAL_BODY_UNTRUSTED_OR_MISSING"
    end
    if rec.OrigEquipRace == nil and rec.FamilyOrigEquipRace == nil then
        failures[#failures + 1] = "ORIGINAL_EQUIP_RACE_UNTRUSTED_OR_MISSING"
    end
    if #failures == 0 then return "clean", failures end
    if #failures == 1 then return "partial", failures end
    return "blocked", failures
end

local function migrateRecord(rec, charGuid, deps)
    rec = type(rec) == "table" and rec or {}
    local priorChoice = rec.Choice
    if rec.Reverted == true then
        rec.Choice = "external"
        rec.PreferredChoice = "vanilla"
    elseif MANAGED_CHOICES[priorChoice] then
        rec.Choice = priorChoice
        rec.PreferredChoice = priorChoice
    else
        rec.Choice = "external"
        rec.PreferredChoice = "vanilla"
    end

    rec.OrigBodySetVisual = trustedBody(rec, charGuid, deps)
    rec.OrigEquipRace = trustedEquip(rec.OrigEquipRace, rec, charGuid, deps)
    rec.FamilyOrigEquipRace = trustedEquip(rec.FamilyOrigEquipRace, rec, charGuid, deps)
    rec.OriginalVisuals = cloneArray(rec.OriginalVisuals)
    rec.OwnedCcsvs = {}
    local legacyCcsvMissingCv = false
    local legacyCcsvUntrusted = false
    if rec.AppliedCcsv ~= nil and rec.AppliedCcsv ~= "" then
        if rec.CvGuid ~= nil and rec.CvGuid ~= "" then
            local trusted = true
            if deps.isRuntimeOwnedCcsv ~= nil then
                local ok, result = pcall(deps.isRuntimeOwnedCcsv, rec.AppliedCcsv, rec, charGuid)
                trusted = ok and result == true
            end
            if trusted then
                rec.OwnedCcsvs[rec.AppliedCcsv] = legacyClaim(rec.CvGuid)
            else
                legacyCcsvUntrusted = true
            end
        else
            legacyCcsvMissingCv = true
        end
    end
    rec.RemovedOriginalVisuals = type(rec.RemovedOriginalVisuals) == "table"
        and rec.RemovedOriginalVisuals or {}
    rec.Transition = nil
    rec.ActiveProvider = nil
    rec.ProviderTransition = nil
    rec.HistoricalOriginals = type(rec.HistoricalOriginals) == "table"
        and rec.HistoricalOriginals or {}
    rec.RestoreState, rec.RestoreFailures = initialRestoreHealth(rec)
    if legacyCcsvMissingCv then
        rec.RestoreFailures[#rec.RestoreFailures + 1] = "LEGACY_CCSV_CV_GUID_MISSING"
        rec.RestoreState = "blocked"
    end
    if legacyCcsvUntrusted then
        rec.RestoreFailures[#rec.RestoreFailures + 1] = "LEGACY_CCSV_UNTRUSTED"
        rec.RestoreState = "blocked"
    end
    return rec
end

local function ensureRecord(rec)
    rec.OriginalVisuals = type(rec.OriginalVisuals) == "table" and rec.OriginalVisuals or {}
    rec.OwnedCcsvs = type(rec.OwnedCcsvs) == "table" and rec.OwnedCcsvs or {}
    rec.RemovedOriginalVisuals = type(rec.RemovedOriginalVisuals) == "table"
        and rec.RemovedOriginalVisuals or {}
    rec.HistoricalOriginals = type(rec.HistoricalOriginals) == "table"
        and rec.HistoricalOriginals or {}
    rec.RestoreFailures = type(rec.RestoreFailures) == "table" and rec.RestoreFailures or {}
    if rec.RestoreState ~= "clean" and rec.RestoreState ~= "pending"
        and rec.RestoreState ~= "partial" and rec.RestoreState ~= "blocked" then
        rec.RestoreState = "pending"
    end
    if rec.Choice ~= "external" and not MANAGED_CHOICES[rec.Choice] then rec.Choice = "external" end
    if not MANAGED_CHOICES[rec.PreferredChoice] then rec.PreferredChoice = "vanilla" end
end

function M.Migrate(state, deps)
    state = type(state) == "table" and state or {}
    deps = type(deps) == "table" and deps or {}
    local sourceVersion = tonumber(state.Version) or 0
    if sourceVersion ~= 6 and sourceVersion ~= 7 then
        return nil, "UNSUPPORTED_PERSISTENT_SCHEMA:" .. tostring(state.Version)
    end
    if sourceVersion == 7 then
        local valid, failure = validateSchema7(state)
        if not valid then return nil, failure end
    end
    state.Bodies = type(state.Bodies) == "table" and state.Bodies or {}
    state.OptoutTemplates = type(state.OptoutTemplates) == "table" and state.OptoutTemplates or {}
    state.ProviderDescriptors = type(state.ProviderDescriptors) == "table"
        and state.ProviderDescriptors or {}
    state.BodyTattooPolicy = normalizePolicy(state.BodyTattooPolicy)

    if sourceVersion < M.SCHEMA_VERSION then
        for charGuid, rec in pairs(state.Bodies) do
            state.Bodies[charGuid] = migrateRecord(rec, charGuid, deps)
        end
        state.MasterEnabled = true
        state.MutationGateClosed = false
        state.MasterState = "enabled"
        state.PassThroughRestoreComplete = false
        state.MasterTransition = nil
        state.CleanupState = "idle"
        state.CleanupTransaction = nil
        state.CleanupAudit = nil
        state.Version = M.SCHEMA_VERSION
    else
        for _, rec in pairs(state.Bodies) do ensureRecord(rec) end
        if type(state.MasterEnabled) ~= "boolean" then state.MasterEnabled = true end
        if type(state.MutationGateClosed) ~= "boolean" then state.MutationGateClosed = false end
        if state.MasterState == nil then state.MasterState = "enabled" end
        if type(state.PassThroughRestoreComplete) ~= "boolean" then
            state.PassThroughRestoreComplete = false
        end
        if state.CleanupState == nil then state.CleanupState = "idle" end
        state.Version = M.SCHEMA_VERSION
    end
    return state
end

return M
