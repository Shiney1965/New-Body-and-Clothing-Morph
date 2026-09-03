local M = {}

M.SCHEMA_VERSION = 7
M.RUNTIME_UUID = "20aca985-e3e9-41d7-bf8f-10f2a3c413e4"
M.R0_PACKAGE_SHA256 = "6610090CEE01091F802273D70FAEE071DCBA891900D77479ABBD828FCDDC60C6"

local MANAGED_CHOICES = { vanilla = true, sbbf = true, bcb = true }

local function validDigest(value)
    if type(value)~="string" then return false end
    local text = tostring(value or "")
    return #text == 64 and text:match("^%x+$") ~= nil
end

local function validGuid(value)
    if type(value)~="string" then return false end
    local text = tostring(value or "")
    if #text ~= 36 or text:sub(9, 9) ~= "-" or text:sub(14, 14) ~= "-"
        or text:sub(19, 19) ~= "-" or text:sub(24, 24) ~= "-" then return false end
    local compact = text:gsub("-", "")
    return #compact == 32 and compact:match("^%x+$") ~= nil
end

local function arrayOf(value, predicate)
    if type(value)~="table" then return false end
    local count=0
    for key,item in pairs(value) do
        if type(key)~="number" or key<1 or key%1~=0 or key>#value or not predicate(item) then return false end
        count=count+1
    end
    return count==#value
end

local function nonemptyString(value) return type(value)=="string" and value~="" end
local function providerClaim(value)
    return type(value)=="table" and nonemptyString(value.ProviderId)
        and validGuid(value.OwnerModuleUuid) and validDigest(value.ProviderDigest)
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
    for _,key in ipairs({'MasterEnabled','MutationGateClosed','PassThroughRestoreComplete'}) do
        if type(state[key]) ~= 'boolean' then return false,'SCHEMA7_'..key..'_INVALID' end
    end
    local masters={enabled=true,enabling=true,off_restoring=true,off_restored=true,off_partial=true,off_blocked=true}
    local cleanup={idle=true,disable_requested=true,cleanup_disabled=true}
    if not masters[state.MasterState] or not cleanup[state.CleanupState] then
        return false,'SCHEMA7_STATE_INVALID'
    end
    if state.CleanupState=="idle" then
        if state.MasterEnabled then
            if state.MasterState=="enabled" then
                if state.MutationGateClosed or state.MasterTransition~=nil then return false,"SCHEMA7_MASTER_PREDICATES_INVALID" end
            elseif state.MasterState~="enabling" or not state.MutationGateClosed then return false,"SCHEMA7_MASTER_PREDICATES_INVALID" end
        elseif not state.MutationGateClosed or state.MasterState:sub(1,4)~="off_" then
            return false,"SCHEMA7_MASTER_PREDICATES_INVALID"
        end
    end
    if state.BodyTattooPolicy~='match' and state.BodyTattooPolicy~='always_show' and state.BodyTattooPolicy~='always_hide' then
        return false,'SCHEMA7_TATTOO_POLICY_INVALID'
    end
    for _,key in ipairs({'OptoutTemplates','ProviderDescriptors'}) do
        if type(state[key])~='table' then return false,'SCHEMA7_'..key..'_INVALID' end
    end
    for _,key in ipairs({'MasterTransition','CleanupTransaction','CleanupAudit'}) do
        if state[key]~=nil and type(state[key])~='table' then return false,'SCHEMA7_'..key..'_INVALID' end
    end
    for id,descriptor in pairs(state.ProviderDescriptors) do
        local unresolved=type(descriptor)=="table" and descriptor.apiGeneration=="legacy_v1"
            and descriptor.ownerModuleUuid=="" and descriptor.ownerUnresolved==true
            and type(descriptor.canonicalPayload)=="table" and descriptor.canonicalPayload.ownerUnresolved==true
            and descriptor.canonicalPayload.ownerModuleUuid==""
        if not nonemptyString(id) or type(descriptor)~="table" or descriptor.providerId~=id
            or (not unresolved and not validGuid(descriptor.ownerModuleUuid)) or not validDigest(descriptor.canonicalDigest)
            or (descriptor.activationState~="active" and descriptor.activationState~="queued" and descriptor.activationState~="rejected")
            or type(descriptor.canonicalPayload)~="table" then return false,"SCHEMA7_PROVIDER_DESCRIPTOR_INVALID" end
    end
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
        for _,key in ipairs({'OriginalVisuals','OwnedCcsvs','RemovedOriginalVisuals','RestoreFailures','HistoricalOriginals'}) do
            if type(rec[key])~='table' then return false,'SCHEMA7_'..key..'_INVALID:'..tostring(charGuid) end
        end
        if not arrayOf(rec.OriginalVisuals,validGuid) or not arrayOf(rec.RestoreFailures,nonemptyString)
            or not arrayOf(rec.HistoricalOriginals,function(row) return type(row)=="table" end) then
            return false,"SCHEMA7_RECORD_ARRAY_INVALID:"..tostring(charGuid)
        end
        for guid,value in pairs(rec.RemovedOriginalVisuals) do
            if not validGuid(guid) or type(value)~="boolean" then return false,"SCHEMA7_REMOVED_VISUAL_INVALID" end
        end
        if rec.ActiveProvider~=nil and not providerClaim(rec.ActiveProvider) then return false,"SCHEMA7_ACTIVE_PROVIDER_INVALID" end
        if rec.Transition~=nil then
            local transition=rec.Transition
            local phases={gated=true,captured=true,restoring=true,applying=true,verifying=true}
            if type(transition)~="table" or (transition.Direction~="to_external" and transition.Direction~="to_managed")
                or not phases[transition.Phase] then return false,"SCHEMA7_OWNERSHIP_TRANSITION_INVALID" end
        end
        if rec.RestoreState~='clean' and rec.RestoreState~='pending' and rec.RestoreState~='partial' and rec.RestoreState~='blocked' then
            return false,'SCHEMA7_RESTORE_STATE_INVALID:'..tostring(charGuid)
        end
        for _,key in ipairs({'Transition','ProviderTransition','ActiveProvider'}) do
            if rec[key]~=nil and type(rec[key])~='table' then return false,'SCHEMA7_'..key..'_INVALID:'..tostring(charGuid) end
        end
        for _,key in ipairs({'CvGuid','OrigBodySetVisual','OrigEquipRace','FamilyOrigEquipRace','AppliedCcsv','DesiredCcsv'}) do
            if rec[key]~=nil and not validGuid(rec[key]) then return false,'SCHEMA7_'..key..'_INVALID:'..tostring(charGuid) end
        end
        if type(rec.OwnedCcsvs) ~= "table" then
            return false, "SCHEMA7_OWNED_CCSVS_INVALID:" .. tostring(charGuid)
        end
        for guid, claim in pairs(rec.OwnedCcsvs) do
            if not validateClaim(guid, claim, rec.CvGuid) then
                return false, "SCHEMA7_OWNERSHIP_CLAIM_INVALID:" .. tostring(charGuid)
                    .. ":" .. tostring(guid)
            end
            if claim.ProviderId~='legacy.runtime' then
                local descriptor=state.ProviderDescriptors[claim.ProviderId]
                local found=false
                if type(descriptor)=='table' and descriptor.activationState=='active'
                    and descriptor.ownerModuleUuid==claim.OwnerModuleUuid
                    and descriptor.canonicalDigest==claim.ProviderDigest then
                    for _,resource in ipairs(descriptor.bodyCcsvs or {}) do if resource==guid then found=true end end
                end
                if not found then return false,'SCHEMA7_STALE_PROVIDER_CLAIM:'..tostring(guid) end
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
    if rec.AppliedCcsv ~= nil and rec.AppliedCcsv ~= "" then
        if rec.CvGuid ~= nil and rec.CvGuid ~= "" then
            -- The trusted schema-6 AppliedCcsv field records the Runtime's
            -- successful write, not physical ownership of the source mesh.
            -- It may therefore name the accepted provider's CCSV even when
            -- that provider resource is currently absent. Infer no other claim.
            rec.OwnedCcsvs[rec.AppliedCcsv] = legacyClaim(rec.CvGuid)
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
    if type(state)~="table" then return nil,"PERSISTENT_STATE_NOT_TABLE" end
    -- An engine-created, genuinely empty new-save table is not a damaged
    -- existing schema. Initialize only that exact empty shape.
    if next(state)==nil then state.Version=6 end
    deps = type(deps) == "table" and deps or {}
    local sourceVersion = state.Version
    if sourceVersion ~= 6 and sourceVersion ~= 7 then
        return nil, "UNSUPPORTED_PERSISTENT_SCHEMA:" .. tostring(state.Version)
    end
    if sourceVersion == 7 then
        local valid, failure = validateSchema7(state)
        if not valid then return nil, failure end
        return state
    end
    if state.Bodies~=nil and type(state.Bodies)~='table' then return nil,'SCHEMA6_BODIES_INVALID' end
    for charGuid,record in pairs(state.Bodies or {}) do
        if type(record)~='table' then return nil,'SCHEMA6_BODY_RECORD_INVALID:'..tostring(charGuid) end
        for _,key in ipairs({'AppliedCcsv','CvGuid'}) do
            if record[key]~=nil and not validGuid(record[key]) then
                return nil,'SCHEMA6_'..key..'_INVALID:'..tostring(charGuid)
            end
        end
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
