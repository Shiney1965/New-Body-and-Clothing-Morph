-- ===========================================================================
-- ClothMorphRuntime / BootstrapServer.lua
-- ---------------------------------------------------------------------------
-- SERVER context. Osi.* exists here (and ONLY here). Applies / clears / switches
-- the per-character nude-body override and persists the choice in PersistentVars.
--
-- VERIFIED MECHANISM (in-game, 2026-06-24):
--   * APPLY a body  : Osi.AddCustomVisualOverride(char, ccsv)
--       -> APPENDS the CCSV GUID to entity.CharacterCreationAppearance.Visuals
--          and renders it. (ccsv = a CharacterCreationSharedVisual GUID.)
--   * There is NO Osiris remove. RemoveCustomVisualOverride does not exist.
--   * Overrides STACK (each Add appends) and PERSIST in the savegame.
--   * CLEAR / SWITCH / REVERT (the only way): read
--       entity.CharacterCreationAppearance.Visuals, rebuild the array WITHOUT the
--       CCSV(s) we appended, assign it back, then
--       entity:Replicate("CharacterCreationAppearance")  -- syncs + re-renders.
--     Confirmed: assigning a Lua array to .Visuals + Replicate works and the body
--     visibly reverts.
--
-- Because overrides persist in the save, we do NOT re-apply on load (that would
-- stack). We DO strip-before-apply on every change so we never accumulate.
--
-- Gotchas obeyed: console cmds need "!"; no os.*/io.* (use Ext.*); Net via
-- Ext.Net.CreateChannel; all risky calls pcall'd; ASCII only.
--
-- v4.15 (2026-07-24): BASE-BODY MECHANISM ("Outcome C", probe-verified live).
-- Primary nude path is now a re-point of the character's CharacterVisual
-- resource field VisualSet.BodySetVisual to the chosen body VisualResource
-- (see the BASE-BODY section below). The CCSV overlay above remains as the
-- automatic FALLBACK (mechanism flag / no CV / rejected write / unmapped VR)
-- and for legacy saves until migrated.
-- ===========================================================================

local Shared    = Ext.Require("Shared.lua")
local TattooPolicy = Ext.Require("TattooPolicy.lua")
local TattooStateProbe = Ext.Require("TattooStateProbe.lua")
local TattooDiagnostics = Ext.Require("TattooDiagnostics.lua")
local EquipRace = Ext.Require("EquipRace.lua")  -- clothed half (EquipmentRace runtime, 2026-07-01)
local BodyFamilyRegistry = Ext.Require("BodyFamilyRegistry.lua")
local BodyFamilyEquipRace = Ext.Require("BodyFamilyEquipRace.lua")
local Targeting = Ext.Require("Targeting.lua")
local SharedTemplateProbe = Ext.Require("SharedTemplateProbe.lua")
local McmGlue   = Ext.Require("MCMIntegration.lua")  -- BG3MCM bridge (hard dependency as of v4.7, 2026-07-11)
local StateSchema7 = Ext.Require("StateSchema7.lua")
local R1Foundation = Ext.Require("R1Foundation.lua")
local OwnershipLedger = Ext.Require("OwnershipLedger.lua")

local MOD = Mods.ClothMorphRuntime
local BG3MCM_UUID = "755a8a72-407f-4f0d-9a33-274ac0f0b53d"

PersistentVars = PersistentVars or {}
local SCHEMA_VERSION = 7

local R1Runtime
local R1Capability
local SetDesiredBody
local BaseRestoreToken = {}
local SharedReapplyDepth = 0
local function R1CanWrite(entryPoint, char)
    if R1Runtime == nil then return false end
    local capability = "managed"
    -- A transition may invoke only its own synchronous mutation chain. Event
    -- callbacks never inherit the capability and a different character cannot
    -- borrow it through reentrant engine calls.
    local transitionOperations = {
        ["set-desired-body"]=true, ["body-strip"]=true, ["body-ccsv"]=true,
        ["body-base"]=true, ["equip-reconcile"]=true,
        ["EquipRace.SetClothed"]=true, ["EquipRace.RunBlanketPass"]=true,
        ["EquipRace.ForceSetEquipRace"]=true,
        ["EquipRace.RefreshEquipment"]=true,
        ["BodyFamilyEquipRace.SetClothed"]=true,
        ["BodyFamilyEquipRace.RunBlanketPass"]=true,
        ["BodyFamilyEquipRace.RefreshEquipment"]=true,
    }
    if R1Capability and transitionOperations[entryPoint]
        and (char == nil or char == R1Capability.char) then
        capability = R1Capability.kind
    end
    local accepted = R1Runtime:WriteGate(capability, char, function() return true end)
    return accepted == true
end

local function R1WithCapability(capability, char, fn)
    local previous = R1Capability
    R1Capability = { kind=capability, char=char }
    local ok, a, b = pcall(fn)
    R1Capability = previous
    if not ok then error(a) end
    return a, b
end

local function IsTrustedSchema6BodyOriginal(guid, cvGuid)
    if guid == nil or cvGuid == nil then return false end
    local needle = tostring(guid):lower()
    if needle == "3bc12bd9-6c5e-5067-a20f-b17e45647a10"
        or needle == "a4891ad7-53b0-5448-8d9c-9fabfdb067b6" then return false end
    for _, ccsv in pairs(Shared.CCSV_MAP or {}) do
        local visual
        pcall(function()
            local object = Ext.StaticData.Get(ccsv, "CharacterCreationSharedVisual")
            if object ~= nil then visual = tostring(object.VisualResource):lower() end
        end)
        if visual == needle then return false end
    end
    local resource
    pcall(function() resource = Ext.Resource.Get(guid, "Visual") end)
    if resource == nil then return false end
    local sourceFile = ""
    pcall(function() sourceFile = tostring(resource.SourceFile or ""):lower() end)
    if sourceFile == "" or sourceFile:find("clothmorphruntime", 1, true) ~= nil then
        return false
    end
    -- A saved trusted original is expected to differ from the currently
    -- managed CV value. Resource provenance, not equality to the live target,
    -- determines original trust; same-CV attestation is checked by restoration.
    return true
end

local function IsTrustedSchema6EquipOriginal(guid, _record, charGuid)
    if guid == nil then return false end
    if EquipRace.IsMintedEquipmentRace ~= nil and EquipRace.IsMintedEquipmentRace(guid) then return false end
    if BodyFamilyRegistry.IsMintedEquipmentRace ~= nil
        and BodyFamilyRegistry.IsMintedEquipmentRace(guid) then return false end
    local needle = tostring(guid):lower()
    for _, known in pairs(EquipRace.KNOWN_ORIG or {}) do
        if tostring(known):lower() == needle then return true end
    end
    local safeSource
    pcall(function() safeSource = BodyFamilyRegistry.SafeSourceEquipmentRace() end)
    if safeSource ~= nil and tostring(safeSource):lower() == needle then return true end
    local eligible = false
    pcall(function() eligible = EquipRace.IsEligible(guid) == true end)
    return eligible
end

local function IsRuntimeOwnedCcsv(guid)
    local needle = tostring(guid or ""):lower()
    if needle == "" then return false end
    for _, mapped in pairs(Shared.CCSV_MAP or {}) do
        if tostring(mapped):lower() == needle then return true end
    end
    local visualGuid
    pcall(function()
        local ccsv = Ext.StaticData.Get(guid, "CharacterCreationSharedVisual")
        visualGuid = ccsv and tostring(ccsv.VisualResource) or nil
    end)
    if visualGuid == nil or visualGuid == "" or visualGuid == "nil" then return false end
    local sourceFile = ""
    pcall(function()
        local visual = Ext.Resource.Get(visualGuid, "Visual")
        sourceFile = tostring(visual.SourceFile or ""):lower()
    end)
    return sourceFile:find("clothmorphruntime", 1, true) ~= nil
end

local SCHEMA_DEPS = {
    isTrustedBodyOriginal = IsTrustedSchema6BodyOriginal,
    isTrustedEquipRaceOriginal = IsTrustedSchema6EquipOriginal,
    isRuntimeOwnedCcsv = IsRuntimeOwnedCcsv,
}

local function Log(msg)  Ext.Utils.Print("[ClothMorphRuntime:Server] " .. tostring(msg)) end
local function Warn(msg) Ext.Utils.PrintWarning("[ClothMorphRuntime:Server] " .. tostring(msg)) end

-- Normalize any Osiris object reference to a bare lowercase GUID. Osiris
-- events (Equipped/Unequipped) pass characters as "Name_guid" strings while
-- our PV.Bodies records are keyed by the bare GUID form - a raw table lookup
-- silently misses and the auto-toggle no-ops (bug found in-game 2026-07-04:
-- equipping vanilla armor over the SBBF nude body clipped instead of
-- reconciling). Bare GUIDs are accepted by both Osi.* and Ext.Entity.Get.
-- NOTE: must be defined BEFORE EnsurePV (which uses it for re-keying).
local function NormGuid(s)
    s = tostring(s or "")
    local g = s:match("(%x%x%x%x%x%x%x%x%-%x%x%x%x%-%x%x%x%x%-%x%x%x%x%-%x%x%x%x%x%x%x%x%x%x%x%x)%s*$")
    return (g or s):lower()
end

-- ---------------------------------------------------------------------------
-- PersistentVars schema (saved into the BG3 savegame by SE):
--   PersistentVars = {
--     Version = <int>,
--     Bodies  = { [characterGuid] = { Choice="vanilla|sbbf|bcb", AppliedCcsv=<guid|nil>,
--                                     DesiredCcsv=<guid|nil>,             -- v3 (nude half)
--                                     ClothedChoice="vanilla|sbbf"|nil,   -- v4 (clothed half; nil = vanilla)
--                                     OrigEquipRace=<guid|nil>,           -- v4 (recorded at first flip)
--                                     OrigBodySetVisual=<guid|nil>,       -- v5 (pristine CV body VR)
--                                     CvGuid=<guid|nil> } },              -- v5 (CV the orig belongs to)
--   }
-- The override itself ALSO lives in the savegame (CharacterCreationAppearance);
-- PersistentVars just records WHICH CCSV is ours so we know what to strip.
-- ---------------------------------------------------------------------------
local function EnsurePV()
    PersistentVars = PersistentVars or {}
    if type(PersistentVars.RollbackPrepared) == "table"
        and PersistentVars.RollbackPrepared.status == "PREPARED" then
        return PersistentVars, "ROLLBACK_PREPARED_CHECKPOINT_REQUIRED"
    end
    local migrated, failure = StateSchema7.Migrate(PersistentVars, SCHEMA_DEPS)
    if migrated == nil then return PersistentVars, failure end
    -- Re-key all records to bare lowercase GUIDs (idempotent; guards against
    -- records created from prefixed "Name_guid" strings).
    local rekeyed = {}
    local changed = false
    for k, rec in pairs(PersistentVars.Bodies) do
        local nk = NormGuid(k)
        if rekeyed[nk] == nil then rekeyed[nk] = rec end
        if nk ~= k then changed = true end
    end
    if changed then PersistentVars.Bodies = rekeyed end
    return PersistentVars
end

local function GetHostChar()
    local ok, char = pcall(function() return Osi.GetHostCharacter() end)
    if ok and char ~= nil and char ~= "" then return NormGuid(char) end
    return nil
end

local function ResolveCommandChar(charArg)
    local char = Targeting.NormGuid(charArg)
    if char == nil then char = GetHostChar() end
    return char
end

local NormalizeNetUserId
local function ResolveNetTarget(data, user)
    local requested = Targeting.NormGuid(data and (data.target or data.char or data.character))
    local userId = NormalizeNetUserId(user)
    if userId == nil or requested == nil then
        Warn(("Net channel: denied cmd='%s' target='%s' reason=missing-sender-user"):format(
            tostring(data and data.cmd),
            tostring(data and data.target)))
        return nil
    end
    local char, err, why = Targeting.ResolveTarget(data, userId, {
        getHostChar = GetHostChar,
    })
    if char == nil then
        -- Extra diagnostics so a future MP session can calibrate the id formats.
        local reserved, reservedWhy = Targeting.GetReservedUserId(requested, { getEntity = GetEntity })
        Warn(("Net channel: denied cmd='%s' target='%s' reason=%s%s [senderType=%s sender=%s reservedForTarget=%s reservedRead=%s]"):format(
            tostring(data and data.cmd),
            tostring(data and data.target),
            tostring(err),
            why and ("/" .. tostring(why)) or "",
            type(user), tostring(user), tostring(reserved), tostring(reservedWhy)))
    end
    return char
end

-- Ext.Net supplies a peer/network id; Osiris ownership uses a user id whose
-- low word is one. Accept only unambiguous scalar integers and normalize once.
NormalizeNetUserId = function(user)
    local kind = type(user)
    local n = nil
    if kind == "number" then
        n = user
    elseif kind == "string" then
        n = tonumber(user)
    else
        return nil, "invalid-sender-type"
    end
    local integer = n ~= nil and math.tointeger(n) or nil
    if integer == nil or integer < 0 or integer > 0xffffffff then
        return nil, "invalid-sender-value"
    end
    return (integer & 0xffff0000) | 0x0001
end

-- Global tattoo-policy changes use a stricter authority path than ordinary
-- per-character commands. ResolveNetTarget intentionally tolerates host and
-- party targets for legacy single-player commands, so it must not authorize a
-- client-forwarded global setting. The sender must own the authoritative host.
local function AuthorizeTattooPolicyUser(user)
    local host = GetHostChar()
    if host == nil then
        Warn("Tattoo policy network update denied: host character unavailable.")
        return false
    end
    if user == nil then
        Warn("Tattoo policy network update denied: missing sender ownership.")
        return false
    end
    local userId, normalizeWhy = NormalizeNetUserId(user)
    if userId == nil then
        Warn(("Tattoo policy network update denied: malformed sender (%s)."):format(
            tostring(normalizeWhy)))
        return false
    end
    local ok, why = Targeting.CanUserControl(userId, host)
    if not ok then
        Warn(("Tattoo policy network update denied: host ownership check failed (%s)."):format(
            tostring(why)))
        return false
    end
    return true
end

-- BG3-MCM's saved event carries no origin. It is authoritative only when the
-- runtime can prove a sole ClientControl user owns the host, or when the
-- current BG3-MCM explicitly reports host-only mode. All API gaps fail closed.
local function AuthorizeMcmTattooPolicy()
    local host = GetHostChar()
    if host == nil then return false, "host-unavailable" end

    local userIds, distinct = {}, {}
    local unknown = 0
    local okList, list = pcall(function()
        return Ext.Entity.GetAllEntitiesWithComponent("ClientControl")
    end)
    if okList and list ~= nil then
        local okScan = pcall(function()
            for _, entity in pairs(list) do
                local raw = nil
                pcall(function() raw = entity.UserReservedFor.UserID end)
                local kind = type(raw)
                local n = nil
                if kind == "number" then
                    n = raw
                elseif kind == "string" then
                    n = tonumber(raw)
                end
                local userId = n ~= nil and math.tointeger(n) or nil
                if userId == nil or userId < 0 or userId > 0xffffffff then
                    unknown = unknown + 1
                else
                    if distinct[userId] == nil then
                        distinct[userId] = true
                        userIds[#userIds + 1] = userId
                    end
                end
            end
        end)
        if not okScan then unknown = unknown + 1 end
    else
        unknown = unknown + 1
    end

    local soleWhy = nil
    if unknown == 0 and #userIds == 1 then
        local userId = userIds[1]
        local ownsHost, why = Targeting.CanUserControl(userId, host)
        if ownsHost then return true, "sole-host-user" end
        soleWhy = why or "ownership-unknown"
    end

    local okHostOnly, hostOnly = pcall(function()
        if type(MCM) ~= "table" or type(MCM.Get) ~= "function" then
            error("cross-mod MCM.Get unavailable")
        end
        return MCM.Get("host-only_mode", BG3MCM_UUID)
    end)
    if okHostOnly and hostOnly == true then return true, "mcm-host-only" end
    if not okHostOnly then
        Warn("MCM tattoo authority: host-only_mode read unavailable/failed: " .. tostring(hostOnly))
    end

    if unknown > 0 then return false, "unknown-client-control-user" end
    if #userIds == 0 then return false, "zero-client-control-users" end
    if #userIds > 1 then return false, "multiple-client-control-users" end
    return false, "sole-user-not-host:" .. tostring(soleWhy)
end

local function RestoreMcmTattooPolicy()
    local labels = { match = "Match Vanilla", always_hide = "Hide on SBBF/BCB" }
    local policy = PersistentVars.BodyTattooPolicy
    local label = labels[policy]
    local ok, setResult = pcall(function()
        if type(MCM) ~= "table" or type(MCM.Set) ~= "function" then
            error("cross-mod non-emitting MCM.Set unavailable")
        end
        return MCM.Set("body_tattoo_policy", label, ModuleUUID, false)
    end)
    if not ok or setResult ~= true then
        Warn("MCM tattoo policy radio restore unavailable/failed: " .. tostring(setResult))
        return false
    end
    return true
end

local function GetEntity(char)
    local ok, ent = pcall(function() return Ext.Entity.Get(char) end)
    if ok then return ent end
    return nil
end

-- ---------------------------------------------------------------------------
-- Visuals helpers. CharacterCreationAppearance.Visuals is a userdata array of
-- GUID strings; assigning a Lua array of strings + Replicate is the proven
-- write path.
-- ---------------------------------------------------------------------------
local function GetCCA(entity)
    if entity == nil then return nil end
    local cca
    pcall(function() cca = entity.CharacterCreationAppearance end)
    return cca
end

local function ReadVisuals(cca)
    local out = {}
    if cca == nil or cca.Visuals == nil then return out, false end
    local ok = pcall(function()
        for _, g in ipairs(cca.Visuals) do out[#out + 1] = tostring(g) end
    end)
    return out, ok
end

local function VisualArraysEqual(a, b)
    if type(a) ~= "table" or type(b) ~= "table" or #a ~= #b then return false end
    for index, value in ipairs(a) do
        if tostring(value):lower() ~= tostring(b[index]):lower() then return false end
    end
    return true
end

-- Remove the given GUIDs (set, lowercased keys) from the character's Visuals and
-- push the change to the client. Returns the new list, and how many were removed.
local function StripVisuals(char, dropSet)
    local entity = GetEntity(char)
    local cca = GetCCA(entity)
    if cca == nil then
        Warn("StripVisuals: no CharacterCreationAppearance on " .. tostring(char))
        return nil, 0, false, nil
    end
    local cur, readOk = ReadVisuals(cca)
    if not readOk then
        Warn("StripVisuals: initial live read failed for " .. tostring(char))
        return nil, 0, false, nil
    end
    local keep, removed = {}, 0
    for _, g in ipairs(cur) do
        if dropSet[tostring(g):lower()] then
            removed = removed + 1
        else
            keep[#keep + 1] = g
        end
    end
    if removed > 0 then
        local okW = pcall(function()
            cca.Visuals = keep
            entity:Replicate("CharacterCreationAppearance")
        end)
        if not okW then
            Warn("StripVisuals: write/Replicate failed for " .. tostring(char))
            return nil, 0, false, nil
        end
    end
    local after, afterOk = ReadVisuals(cca)
    if not afterOk or not VisualArraysEqual(after, keep) then
        Warn("StripVisuals: live readback mismatch for " .. tostring(char))
        return nil, removed, false, after
    end
    return keep, removed, true, after
end

-- Strip whatever CCSV we previously recorded for this character (if any).
local function StripOurOverride(char, retirement, targetGuid)
    if not R1CanWrite("body-strip", char) then return false end
    local pv = EnsurePV()
    local rec = pv.Bodies[char]
    if rec == nil then return true end
    local target = targetGuid or rec.AppliedCcsv
    if target == nil or target == "" then return true end
    local claim
    for guid,value in pairs(rec.OwnedCcsvs or {}) do
        if tostring(guid):lower()==tostring(target):lower() then claim=value end
    end
    if claim==nil or tostring(claim.AddedForCvGuid):lower()~=tostring(rec.CvGuid):lower() then
        return false,"ccsv-not-owned"
    end
    local liveCv
    pcall(function() liveCv=GetEntity(char).ServerCharacter.Template.CharacterVisualResourceID end)
    if tostring(liveCv):lower()~=tostring(rec.CvGuid):lower() then return false,"body-cv-mismatch" end
    local dropSet = { [tostring(target):lower()] = true }
    local _, removed, verified, after = StripVisuals(char, dropSet)
    if not verified then return false end
    if rec.AppliedCcsv ~= nil
        and tostring(rec.AppliedCcsv):lower() == tostring(target):lower() then
        rec.AppliedCcsv = nil
    end
    if retirement == "permanent" then
        local live = {}
        for _, guid in ipairs(after or {}) do live[tostring(guid):lower()] = true end
        for ownedGuid in pairs(rec.OwnedCcsvs or {}) do
            local ownedKey = tostring(ownedGuid):lower()
            if ownedKey == tostring(target):lower() and not live[ownedKey] then
                rec.OwnedCcsvs[ownedGuid] = nil
            end
        end
    end
    Log(("StripOurOverride(%s): removed %d entr(y/ies) of %s from %s")
        :format(tostring(retirement), removed, tostring(target), tostring(char)))
    return true
end

-- ---------------------------------------------------------------------------
-- ApplyCcsv(char, ccsv): strip our previous override, then apply ccsv and record
-- it. This is the low-level switch primitive (raw CCSV GUID).
-- ---------------------------------------------------------------------------
local function ApplyCcsv(char, ccsv, choiceLabel)
    if not R1CanWrite("body-ccsv", char) then return false end
    if char == nil or ccsv == nil or ccsv == "" then
        Warn("ApplyCcsv: missing char/ccsv"); return false
    end
    local pv = EnsurePV()
    local rec = pv.Bodies[char] or {}
    if rec.CvGuid == nil or rec.CvGuid == "" then
        Warn("ApplyCcsv: no saved CvGuid; refusing an unbindable CCSV write")
        return false
    end
    local liveCv
    pcall(function()
        local entity = GetEntity(char)
        liveCv = tostring(entity.ServerCharacter.Template.CharacterVisualResourceID)
    end)
    if liveCv == nil or liveCv == "" or liveCv == "nil"
        or liveCv:lower() ~= tostring(rec.CvGuid):lower() then
        Warn("ApplyCcsv: live CvGuid mismatch; refusing an incorrectly bound CCSV write")
        return false
    end
    local providerClaim, providerClaimWhy
    if R1Runtime ~= nil and R1Runtime.ProviderRegistry ~= nil then
        providerClaim, providerClaimWhy = R1Runtime.ProviderRegistry:ClaimForCcsv(
            ccsv, rec.CvGuid, "body_ccsv")
        if providerClaim == nil and providerClaimWhy ~= "CCSV_OWNER_NOT_REGISTERED" then
            Warn("ApplyCcsv: provider ownership is ambiguous or invalid; refusing CCSV write")
            return false, providerClaimWhy
        end
    end
    if not StripOurOverride(char, "permanent", rec.AppliedCcsv) then
        Warn("ApplyCcsv: prior CCSV retirement failed; refusing to stack a new write")
        return false, "ccsv-retirement-failed"
    end
    local before, readable = ReadVisuals(GetCCA(GetEntity(char)))
    if not readable then return false,"ccsv-before-read-failed" end
    for _,visual in ipairs(before) do
        if tostring(visual):lower()==tostring(ccsv):lower() then
            return false,"ccsv-already-present-unowned"
        end
    end
    local okApply = pcall(function() Osi.AddCustomVisualOverride(char, ccsv) end)
    if not okApply then
        Warn("ApplyCcsv: AddCustomVisualOverride failed " .. tostring(ccsv))
        return false
    end
    local after, afterReadable=ReadVisuals(GetCCA(GetEntity(char)))
    if not afterReadable or #after~=#before+1 or tostring(after[#after]):lower()~=tostring(ccsv):lower() then
        return false,"ccsv-add-readback-failed"
    end
    for i,visual in ipairs(before) do
        if tostring(after[i]):lower()~=tostring(visual):lower() then return false,"ccsv-add-readback-failed" end
    end
    -- Update fields IN PLACE (v4: the record also carries ClothedChoice /
    -- OrigEquipRace for the EquipmentRace half - do not wipe them).
    rec.OwnedCcsvs = rec.OwnedCcsvs or {}
    rec.OwnedCcsvs[ccsv] = providerClaim or OwnershipLedger.LegacyRuntimeClaim(rec.CvGuid)
    rec.Choice, rec.AppliedCcsv, rec.DesiredCcsv = choiceLabel or "custom", ccsv, ccsv
    pv.Bodies[char] = rec
    Log(("ApplyCcsv: %s -> %s (choice=%s)")
        :format(tostring(char), tostring(ccsv), tostring(choiceLabel or "custom")))
    return true
end

-- ===========================================================================
-- v4.15 BASE-BODY MECHANISM ("Outcome C"; probe-verified in-game 2026-07-24).
-- Re-points the character's CharacterVisual resource field
--     VisualSet.BodySetVisual
-- at the chosen body VisualResource, so the BASE body itself becomes the
-- chosen shape (single-body render; garments always sit over the body they
-- were fitted to; revealing-garment bookkeeping becomes unnecessary).
-- Probe facts baked in:
--   * Ext.Resource.Get(cv, "CharacterVisual") is live in both Lua states and
--     they share ONE resource object in single-player -> a server-side write
--     is sufficient locally.
--   * ONE-STEP nested writes only (r.VisualSet.BodySetVisual = g). NEVER
--     assign r.VisualSet itself: the shallow copy wipes Slots and
--     MaterialOverrides (headless character until relaunch).
--   * Writes survive rebuilds AND save reloads within one game process and
--     reset on relaunch -> re-apply once per process (idempotent), restore
--     on cross-save loads (RestoreAllBaseWrites).
--   * World model re-renders after the CCA touch+Replicate rebuild
--     (ForceVisualRebuild; the probe's 'replicate' trigger). Paperdoll is
--     immediate.
-- MECHANISM: "C" = base-body primary with CCSV fallback; "CCSV" = wholesale
-- v4.13 behavior (single-line rollback).
-- ===========================================================================
local MECHANISM = "C"

-- Process-level record of CV edits. Resources reset per game process, so this
-- must NOT live in PersistentVars: [cvGuid] = { orig=<vr>, cur=<vr>, char=g }.
local BaseWrites = {}

local function GetCharCV(char)
    local cv
    pcall(function()
        local e = GetEntity(char)
        cv = tostring(e.ServerCharacter.Template.CharacterVisualResourceID)
    end)
    if cv == "" or cv == "nil" then cv = nil end
    return cv
end

local function GetCVRes(cv)
    local r
    pcall(function() r = Ext.Resource.Get(cv, "CharacterVisual") end)
    return r
end

local function ReadBaseBody(cv)
    local v
    pcall(function()
        local r = GetCVRes(cv)
        if r ~= nil then v = tostring(r.VisualSet.BodySetVisual) end
    end)
    if v == "" or v == "nil" then v = nil end
    return v
end

-- choice -> target body VisualResource, by unwrapping the SAME CCSV the
-- registry already resolves (CCSV.VisualResource; the CheckBody read path).
-- Returns vr, ccsv, tattooHandled. tattooHandled is true once an in-scope
-- HUM_F tuple reaches pair validation, including terminal fail-open exhaustion.
-- Callers must not resurrect the original CCSV when that status is true.
local function ResolveBodyVr(choice, race, bt, bs)
    local ccsv = Shared.ResolveCcsv(choice, race, bt, bs)
    if ccsv == nil then return nil, nil, false end
    local vr
    pcall(function()
        local obj = Ext.StaticData.Get(ccsv, "CharacterCreationSharedVisual")
        if obj ~= nil then vr = tostring(obj.VisualResource) end
    end)
    if vr == "" or vr == "nil" then vr = nil end
    if not TattooPolicy.IsHumF(race, bt, bs) then return vr, ccsv, false end
    local tattooPolicy = PersistentVars.BodyTattooPolicy == "always_hide" and "hide" or "match"
    local environment = TattooPolicy.DetectEnvironment(function(uuid) return Ext.Mod.GetMod(uuid) end)
    local function resourceExists(guid, kind)
        local found = nil
        if kind == "ccsv" then
            pcall(function() found = Ext.StaticData.Get(guid, "CharacterCreationSharedVisual") end)
        else
            pcall(function() found = Ext.Resource.Get(guid, "Visual") end)
        end
        return found ~= nil
    end
    local variantVr, vrReason = TattooPolicy.Resolve(choice, race, bt, bs, tattooPolicy, environment, resourceExists)
    local variantCcsv, ccsvReason = TattooPolicy.ResolveCcsv(choice, race, bt, bs, tattooPolicy, environment, resourceExists)
    if variantVr == nil or variantCcsv == nil then
        Warn(("ResolveBodyVr: tattoo pair unavailable choice=%s env=%s policy=%s vr=%s ccsv=%s")
            :format(tostring(choice), environment, tattooPolicy, tostring(vrReason), tostring(ccsvReason)))
        return nil, nil, true
    end
    if vrReason ~= "selected-primary:" .. environment .. ":" .. tattooPolicy
       or ccsvReason ~= "selected-primary:" .. environment .. ":" .. tattooPolicy then
        Warn(("ResolveBodyVr: tattoo policy fail-open choice=%s vr=%s ccsv=%s")
            :format(tostring(choice), tostring(vrReason), tostring(ccsvReason)))
    end
    return variantVr, variantCcsv, true
end

-- v4.19 HOTFIX (2026-07-29): minted TRUE-VANILLA HUM_F body.
-- Vanilla mode used to RESTORE the install's original body; on body-replacer
-- installs (Unique Tav / BCB-UT) the original is not vanilla-shaped, so
-- "vanilla" rendered a modded body (field report + visdump 2026-07-29:
-- VR 53715306 -> BCBUniqueTav GR2). Vanilla now FORCES this minted VR, exactly
-- like sbbf/bcb force theirs. Bank: ClothMorphRuntime
-- [PAK]_CM_Vanilla_Female_Body/_merged.lsf; GR2 = Larian's vanilla
-- HUM_F_NKD_Body_A (SHA256 00103976f4...) at .../_Female/Resources_Vanilla/.
-- VR guid = uuid5(NAMESPACE_URL, "clothmorph:vanilla:HUM_F_NKD_Body_A").
local VANILLA_BODY_VR = "3bc12bd9-6c5e-5067-a20f-b17e45647a10"
-- Gate: the bcb CCSV a character resolves to identifies its BODY FAMILY, and
-- each family maps to its own minted TRUE-VANILLA VR (v4.20, Alan 2026-07-30:
-- Githyanki added; was HUM_F-only in v4.19). The Ext.Resource.Get check makes
-- a stale/missing pak degrade to the v4.18 restore-original behavior for that
-- family only, instead of writing an unresolvable VR (invisible body).
local HUM_F_BCB_CCSV = "fe01f8f7-814e-5c2e-9829-a0467fd5a6ce"
local GTY_BCB_CCSV   = "3d93f1a0-22bc-5938-951b-fe8b639be26b"
local VANILLA_BODY_BY_BCB_CCSV = {
    -- HUM_F (7 races): ClothMorphRuntime v1.2.0+
    [HUM_F_BCB_CCSV] = VANILLA_BODY_VR,
    -- GTY_F (Githyanki, Lae'zel): ships in this main pak from v1.3
    -- (was the standalone Githyanki add-on, retired in v1.3).
    -- uuid5(NAMESPACE_URL, "clothmorph:gty:vanilla:GTY_F_NKD_Body_A").
    [GTY_BCB_CCSV]   = "a4891ad7-53b0-5448-8d9c-9fabfdb067b6",
}
local function ResolveVanillaBodyVr(entity)
    local vr = nil
    pcall(function()
        local race, bt, bs = Shared.ReadCharStats(entity)
        local ccsv = Shared.ResolveCcsv("bcb", race, bt, bs)
        local target = nil
        if ccsv ~= nil then target = VANILLA_BODY_BY_BCB_CCSV[ccsv] end
        if target == nil then return end
        if Ext.Resource.Get(target, "Visual") == nil then return end
        vr = target
    end)
    return vr
end

-- Full visual rebuild: touch CCA.Visuals + Replicate (probe 'replicate').
local function ForceVisualRebuild(char)
    local ok = pcall(function()
        local e = GetEntity(char)
        local cca = e.CharacterCreationAppearance
        local cur = {}
        for _, g in ipairs(cca.Visuals or {}) do cur[#cur + 1] = tostring(g) end
        cca.Visuals = cur
        e:Replicate("CharacterCreationAppearance")
    end)
    if not ok then Warn("ForceVisualRebuild failed for " .. tostring(char)) end
    return ok
end

-- Write the base-body VR into the char's CV (one-step) with readback verify.
-- targetVr == nil restores the recorded original (vanilla choice).
local function SetBaseBody(char, choice, targetVr)
    if not R1CanWrite("body-base", char) then return false, "write-gate-closed" end
    if MECHANISM ~= "C" then return false, "mechanism-off" end
    local cv = GetCharCV(char)
    if cv == nil then return false, "no-cv" end
    local cur = ReadBaseBody(cv)
    if cur == nil then return false, "cv-unreadable" end
    local pv = EnsurePV()
    local rec = pv.Bodies[char] or {}; pv.Bodies[char] = rec
    -- SF-3 (review 2026-07-24): if the char's CV changed since the original
    -- was recorded (template swap / appearance mod), the stale orig belongs
    -- to ANOTHER CV - drop it and re-record against the current CV.
    if rec.CvGuid ~= nil and rec.CvGuid ~= cv then
        Warn(("SetBaseBody: %s CV changed %s -> %s; re-recording original")
            :format(tostring(char), tostring(rec.CvGuid), cv))
        rec.OrigBodySetVisual, rec.CvGuid = nil, nil
    end
    local bw = BaseWrites[cv]
    -- Record the pristine original ONCE per save record. Prefer the process
    -- map's orig (cur may already be a same-process edit from another save).
    if rec.OrigBodySetVisual == nil then
        local candidate = (bw and bw.orig) or cur
        if not IsTrustedSchema6BodyOriginal(candidate, cv, rec, char) then
            Warn(("SetBaseBody: refusing untrusted original %s for %s"):format(
                tostring(candidate), tostring(char)))
            return false, "untrusted-original"
        end
        rec.OrigBodySetVisual = candidate
        rec.CvGuid = cv
    end
    local orig = (bw and bw.orig) or rec.OrigBodySetVisual or cur
    local target = targetVr
    if target == nil then target = orig end
    local claims={[char]=target}
    local sharedConflict=false
    for other,otherRecord in pairs(pv.Bodies) do
        if other~=char and otherRecord.CvGuid==cv and GetEntity(other)~=nil then
            local otherTarget
            if otherRecord.Choice~="external" and otherRecord.RestoreState=="clean"
                and otherRecord.Transition==nil and otherRecord.ProviderTransition==nil then
                local entity=GetEntity(other)
                local race,bt,bs=Shared.ReadCharStats(entity)
                local family=BodyFamilyRegistry.ResolveOfficialFamily(race,bt,bs)
                if family then
                    local profile=BodyFamilyRegistry.ResolveProfile(family,otherRecord.Choice)
                    otherTarget=profile and profile.visual
                elseif otherRecord.Choice=="vanilla" then otherTarget=ResolveVanillaBodyVr(entity)
                else otherTarget=ResolveBodyVr(otherRecord.Choice,race,bt,bs) end
            end
            claims[other]=otherTarget or "external"
            if otherTarget~=target then sharedConflict=true end
        end
    end
    if sharedConflict then
        if cur~=orig then
            local wrote=pcall(function() GetCVRes(cv).VisualSet.BodySetVisual=orig end)
            if not wrote or ReadBaseBody(cv)~=orig then return false,"shared-cv-restore-failed" end
        end
        BaseWrites[cv]={orig=orig,cur=orig,char=char,claims=claims}
        if SharedReapplyDepth==0 and SetDesiredBody then
            SharedReapplyDepth=1
            local failed=false
            for other,otherRecord in pairs(pv.Bodies) do
                if other~=char and otherRecord.CvGuid==cv
                    and R1Runtime:CanManagedWrite("shared-cv-peer",other)
                    and claims[other]~="external" then
                    local call,ok=pcall(SetDesiredBody,other,otherRecord.Choice)
                    if not call or ok~=true then failed=true end
                end
            end
            SharedReapplyDepth=0
            if failed then return false,"shared-cv-conflict-fallback-failed" end
        end
        return false,"shared-cv-fallback-required"
    end
    if cur == target then
        BaseWrites[cv] = { orig = orig, cur = cur, char = char, claims=claims }
        return true, "already"
    end
    local okW = pcall(function()
        local r = GetCVRes(cv)
        r.VisualSet.BodySetVisual = target   -- ONE-STEP nested write ONLY
    end)
    local after = ReadBaseBody(cv)
    if (not okW) or after ~= target then
        Warn(("SetBaseBody: write REJECTED for %s (cv=%s want=%s got=%s)")
            :format(tostring(char), cv, tostring(target), tostring(after)))
        return false, "write-rejected"
    end
    BaseWrites[cv] = { orig = orig, cur = target, char = char, claims=claims }
    ForceVisualRebuild(char)
    Log(("SetBaseBody: %s cv=%s %s -> %s (choice=%s)")
        :format(tostring(char), cv, tostring(cur), tostring(target), tostring(choice)))
    return true, "written"
end

-- Cross-save hygiene: put every process-level CV edit back to its original.
-- Runs at SavegameLoaded BEFORE the per-save re-apply, so a save that never
-- managed a character cannot inherit another save's body edit.
local function RestoreAllBaseWrites(reason, token)
    if token~=BaseRestoreToken then return false,"internal-restore-required" end
    local n = 0
    for cv, bw in pairs(BaseWrites) do
        if bw.cur ~= bw.orig then
            if ReadBaseBody(cv)~=bw.cur then goto continue end
            local okW = pcall(function()
                local r = GetCVRes(cv)
                r.VisualSet.BodySetVisual = bw.orig
            end)
            if okW then
                bw.cur = bw.orig; n = n + 1
                -- SF-1: re-render the restored character NOW (no-op warn if
                -- that char does not exist in the loaded save).
                if bw.char ~= nil then pcall(function() ForceVisualRebuild(bw.char) end) end
            end
        end
        ::continue::
    end
    if n > 0 then
        Log(("RestoreAllBaseWrites(%s): restored %d CV(s)"):format(tostring(reason), n))
    end
end

-- Re-apply the loaded save's recorded choices (idempotent; resources reset
-- per process). Also migrates legacy v4.13 records off the CCSV overlay once
-- the base write holds (the overlay CCSV persists in old saves' CCA).
local ReapplyBaseBodies  -- forward decl; body assigned after StripOurOverride exists

-- RevertChar(char): strip our override, record vanilla. No Osiris remove needed.
-- v4.3: also reverts the CLOTHED half (EquipmentRace) so !cm_revert restores the
-- WHOLE character (nude + armor). Was nude-only before; Alan expected a full
-- revert. The clothed revert is a no-op-safe pcall (does nothing if the char was
-- never flipped / has no recoverable original).
local function RevertChar(char)
    if char == nil then return false end
    if R1Runtime ~= nil then
        local result = R1Runtime:SetExternal(char)
        return result ~= nil and result.ok == true
    end
    local pv = EnsurePV()
    if MECHANISM == "C" then pcall(function() SetBaseBody(char, "vanilla", nil) end) end
    if not StripOurOverride(char, "permanent", (pv.Bodies[char] or {}).AppliedCcsv) then
        return false
    end
    local rec = pv.Bodies[char] or {}
    rec.Choice, rec.AppliedCcsv, rec.DesiredCcsv = "vanilla", nil, nil
    rec.UnavailableFamilyChoice = nil
    rec.Reverted = true  -- v4.19: revert = mod-off (restore ORIGINAL body), NOT the forced true-vanilla body
    pv.Bodies[char] = rec
    if rec.BodyFamilyId ~= nil then
        pcall(function() BodyFamilyEquipRace.Restore(char, rec) end)
    else
        pcall(function() EquipRace.SetClothed(char, "off", rec) end)  -- clothed half: restore ORIGINAL ER (2026-07-15: "off", not "vanilla" which is now a minted flip)
    end
    Log("RevertChar: " .. tostring(char) .. " reverted to vanilla body + clothing")
    return true
end

-- ---------------------------------------------------------------------------
-- Clothed/nude auto-toggle.
--   Desired body (when nude) = rec.DesiredCcsv (nil => vanilla). When a torso
--   item is worn we STRIP the nude override (the equipped SBBF-refit outfit
--   carries the SBBF shape + occludes the body); when the torso is bare we
--   (re-)apply the desired CCSV. Proven 2026-06-26: nude override punches
--   through clothing, so the two states must be mutually exclusive.
-- ---------------------------------------------------------------------------
local TORSO_SLOTS = { "Breast", "VanityBody" }

local function SlotOccupied(char, slot)
    local occ = false
    pcall(function()
        local it = Osi.GetEquippedItem(char, slot)
        if it ~= nil and it ~= "" then occ = true end
    end)
    return occ
end

-- Which armour set the engine currently RENDERS: "Normal" (Breast slot) or
-- "Vanity" (camp clothes / VanityBody). Ground truth = entity.ArmorSetState
-- .State (eoc::armor_set::StateComponent; same enum as Osi Get/SetArmourSet,
-- values Normal=0 / Vanity=1). nil component = Normal (component can be absent).
local function CurrentArmourSet(char)
    local set = "Normal"
    pcall(function()
        local e = GetEntity(char)
        local s = e ~= nil and e.ArmorSetState or nil
        if s ~= nil then
            local v = s.State
            if v == "Vanity" or v == 1 then set = "Vanity" end
        end
    end)
    return set
end

-- v4.4 camp-clothes fix (2026-07-07, confirmed via slotcheck): camp clothes
-- equipped-but-HIDDEN (armour set Normal, Breast empty, VanityBody occupied)
-- previously counted as covered, so Reconcile stripped the nude override while
-- the character rendered nude. Only the slot belonging to the ACTIVE armour
-- set can visually cover the torso: Vanity -> VanityBody, Normal -> Breast.
-- (Edge assumed, flagged for in-game check: Vanity set + empty VanityBody is
-- treated as bare.)
local function IsTorsoCovered(char)
    if CurrentArmourSet(char) == "Vanity" then
        return SlotOccupied(char, "VanityBody")
    else
        return SlotOccupied(char, "Breast")
    end
end

-- ---------------------------------------------------------------------------
-- v4.11 (2026-07-20): REVEALING-GARMENT body coupling.
-- The strip-on-cover rule (above) assumes every worn torso item OCCLUDES the
-- body. True for normal armor/robes, but NOT for revealing vanity garments
-- (BCB camp clothes with open chest / high slits, or garments carrying no body
-- of their own): stripping the nude override there leaves the character's BASE
-- (vanilla) body showing through an SBBF/BCB-cut outfit -> the "too big /
-- doesn't match / clipping" mismatch (diagnosed in-game 2026-07-20 via
-- cm_visdump: Rich Dress = SBBF-cut dress over the vanilla base body; Full
-- Metal Dress = its own baked SBBF body PLUS the vanilla base = double-body).
-- Fix: for garments KNOWN to be revealing, KEEP the selected body applied so it
-- matches the outfit. SAFE BY DEFAULT: anything NOT listed here still occludes
-- (strip), so all ordinary armor is unchanged.
-- Keyed by the item's carried template id OR its parent template id OR its
-- Human-Female source VisualResource id (match on ANY marks it revealing).
-- Seeded with the two in-game-VERIFIED pilot torso garments; extend as more
-- BCB vanity garments are confirmed.
-- ---------------------------------------------------------------------------
local REVEALING_TORSO = {
    -- Rich Dress - Short: carried template + Human-F source VR
    ["19bf6831-84ff-42d1-aa18-a97dc3f96a6a"] = true,
    ["81c7c8bb-32e0-4549-9066-f61c6affc78b"] = true,
    ["9396ed3b-74e9-4977-9dfb-412fb7d7bbea"] = true,   -- Mizora DressLong (revealing) 2026-07-20
    ["9296ed3b-74e9-4977-9dfb-412fb7d7bbea"] = true,   -- Mizora Dress (short) revealing
    -- v4.12 (2026-07-20): Full Metal Dress (CorsetSkirtArm, 20bf6831 / 44c0132d)
    -- REMOVED from the revealing set. It bakes its OWN body (see EquipRace
    -- M.BAKED_EXCLUDE), so it is left untouched: it now OCCLUDES here (nude
    -- override stripped under it) and its flip is verbatim (raw Sindae mesh),
    -- i.e. it renders exactly as the original BCB mod. Add future baked-body
    -- garments to M.BAKED_EXCLUDE, NOT here.
}

-- Human-Female source race (same GUID the blanket pass copies from; used to
-- read an item's source visual array). See EquipRace SOURCE_RACE.
local HUMAN_F_RACE = "71180b76-5752-4a97-b71f-911a69197f58"

-- Read an equipped item's template id, parent template id, and its Human-F
-- source VisualResource ids; return true if ANY is tagged REVEALING_TORSO.
-- Fully pcall-guarded and read-only; unknown/absent fields -> false (occludes).
local function ItemIsRevealing(itemGuid)
    if itemGuid == nil or itemGuid == "" then return false end
    local hit = false
    pcall(function()
        local e = Ext.Entity.Get(itemGuid)
        local t = e ~= nil and e.ServerItem ~= nil and e.ServerItem.Template or nil
        if t == nil then return end
        local tid = tostring(t.Id or ""):lower()
        if REVEALING_TORSO[tid] then hit = true; return end
        local pid = tostring(t.ParentTemplateId or ""):lower()
        if pid ~= "" and REVEALING_TORSO[pid] then hit = true; return end
        if t.Equipment ~= nil and t.Equipment.Visuals ~= nil then
            local arr = t.Equipment.Visuals[HUMAN_F_RACE]
            if arr ~= nil then
                for _, v in ipairs(arr) do
                    if REVEALING_TORSO[tostring(v):lower()] then hit = true; return end
                end
            end
        end
    end)
    return hit
end

-- Does the currently-rendered torso garment OCCLUDE the body (=> strip is
-- correct)? Default TRUE (safe: strip) unless the ACTIVE-set torso item is a
-- known revealing garment. Only consulted when IsTorsoCovered(char) is true.
local function TorsoOccludesBody(char)
    local slot = (CurrentArmourSet(char) == "Vanity") and "VanityBody" or "Breast"
    local it
    pcall(function() it = Osi.GetEquippedItem(char, slot) end)
    if it == nil or it == "" then return true end
    return not ItemIsRevealing(it)
end

-- Idempotent: brings the override in line with desire + torso coverage.
local function Reconcile(char, reason)
    if not R1CanWrite("equip-reconcile", char) then return false end
    local pv = EnsurePV()
    local rec = pv.Bodies[char]
    if rec == nil then return end
    local desired = rec.DesiredCcsv
    if desired == nil then
        if rec.AppliedCcsv then
            if StripOurOverride(char, "permanent", rec.AppliedCcsv) then
                Log(("Reconcile(%s): desired vanilla -> stripped"):format(tostring(reason)))
            else
                return false
            end
        end
        return true
    end
    -- v4.11: hide the body ONLY when the torso is covered by an OCCLUDING
    -- garment. A revealing vanity garment keeps the selected body so it matches
    -- the outfit's cut (see REVEALING_TORSO above). Ordinary armor is unchanged.
    if IsTorsoCovered(char) and TorsoOccludesBody(char) then
        if rec.AppliedCcsv then
            if StripOurOverride(char, "temporary", rec.AppliedCcsv) then
                Log(("Reconcile(%s): torso covered by occluding armor -> stripped nude body"):format(tostring(reason)))
            else
                return false
            end
        end
    else
        if rec.AppliedCcsv ~= desired then
            local applied, failure = ApplyCcsv(char, desired, rec.Choice or "custom")
            if not applied then return false, failure end
            Log(("Reconcile(%s): torso bare or revealing garment -> applied %s"):format(tostring(reason), tostring(desired)))
        end
    end
    return true
end

-- v4.15: body of the forward-declared re-apply walk (needs StripOurOverride).
ReapplyBaseBodies = function(reason)
    local pv = EnsurePV()
    local n = 0
    for char, rec in pairs(pv.Bodies or {}) do
        if not R1CanWrite("load-body-reapply", char) then goto continue end
        local choice = rec.UnavailableFamilyChoice or rec.Choice
        -- v4.19 HOTFIX: vanilla is now a FORCED body too (true-vanilla VR), so
        -- recorded vanilla picks re-apply on load like sbbf/bcb. rec.Reverted
        -- (set by !cm_revert) means mod-off -> keep restore-original, skip.
        if choice == "sbbf" or choice == "bcb"
           or (choice == "vanilla" and rec.Reverted ~= true) then
            local entity = GetEntity(char)
            if entity == nil then
                Log(("ReapplyBaseBodies: %s not instantiated yet (choice=%s) - will retry at the other load event")
                    :format(tostring(char), tostring(choice)))
            end
            if entity ~= nil then
                local vr
                local race, bt, bs
                pcall(function() race, bt, bs = Shared.ReadCharStats(entity) end)
                local familyId = BodyFamilyRegistry.ResolveOfficialFamily(race, bt, bs)
                if familyId ~= nil then
                    local profile, why = BodyFamilyRegistry.ResolveProfile(familyId, choice)
                    if profile ~= nil then
                        vr = profile.visual
                        rec.BodyFamilyId = familyId
                        if rec.UnavailableFamilyChoice ~= nil then
                            rec.Choice = choice
                            rec.FamilyClothedChoice = choice
                            rec.UnavailableFamilyChoice = nil
                            rec.Reverted = nil
                            Log(("ReapplyBaseBodies: provider restored for %s; scheduling retained choice=%s")
                                :format(tostring(char), tostring(choice)))
                        end
                    else
                        local recovered = false
                        pcall(function()
                            recovered = BodyFamilyEquipRace.RecoverUnavailable(char, rec, choice, function()
                                if not StripOurOverride(char, "permanent", rec.AppliedCcsv or rec.DesiredCcsv) then
                                    error("ccsv-retirement-failed")
                                end
                                if MECHANISM == "C" then
                                    local okBase = SetBaseBody(char, "vanilla", nil)
                                    if not okBase then error("base-body-restore-failed") end
                                end
                            end)
                        end)
                        Warn(("ReapplyBaseBodies: %s choice=%s body-family profile unavailable (%s); safe recovery=%s")
                            :format(tostring(char), tostring(choice), tostring(why), tostring(recovered)))
                    end
                elseif choice == "vanilla" then
                    -- nil (non-HUM_F race / stale Content) = keep the v4.18
                    -- restore-original behavior for this char; no warn.
                    vr = ResolveVanillaBodyVr(entity)
                else
                    vr = ResolveBodyVr(choice, race, bt, bs)
                    if vr == nil then
                        Warn(("ReapplyBaseBodies: %s choice=%s has no resolvable body VR (race=%s) - base body left vanilla")
                            :format(tostring(char), tostring(choice), tostring(race)))
                    end
                end
                if vr ~= nil then
                    local retirementTarget = rec.AppliedCcsv or rec.DesiredCcsv
                    local retired = retirementTarget == nil
                        or StripOurOverride(char, "permanent", retirementTarget)
                    if not retired then
                        Warn("ReapplyBaseBodies: CCSV retirement readback failed for " .. tostring(char))
                    else
                        local ok = SetBaseBody(char, choice, vr)
                        if ok then
                            n = n + 1
                            if retirementTarget ~= nil then
                                rec.DesiredCcsv = nil
                                Log(("ReapplyBaseBodies: migrated %s off the legacy CCSV overlay")
                                    :format(tostring(char)))
                            end
                        end
                    end
                end
            end
        end
        ::continue::
    end
    if n > 0 then Log(("ReapplyBaseBodies(%s): %d character(s)"):format(tostring(reason), n)) end
end

local function ShouldRenderNakedBody(char)
    return not IsTorsoCovered(char) or not TorsoOccludesBody(char)
end

-- Apply only the resolved naked-body half. The full SetDesiredBody path remains
-- responsible for clothing and torso reconciliation. For policy refreshes,
-- use the caller's read-only visibility result to write an immediately visible
-- CCSV fallback or defer it until existing equip/unequip reconciliation next
-- exposes the naked body.
local function ApplyNakedBody(char, choice, rec, vr, ccsv, tattooHandled, bodyShouldRender)
    local okNude = false
    if MECHANISM == "C" and vr ~= nil then
        local retirementTarget = rec.AppliedCcsv or rec.DesiredCcsv
        if retirementTarget ~= nil
            and not StripOurOverride(char, "permanent", retirementTarget) then
            return false, "ccsv-retirement-failed", tattooHandled
        end
        local okBase, baseResult = SetBaseBody(char, choice, vr)
        if okBase then
            rec.Choice = choice
            if retirementTarget ~= nil then rec.DesiredCcsv = nil end
            if baseResult == "written" then return true, "base-written", tattooHandled end
            return true, "base-current", tattooHandled
        end
    end
    if not okNude and ccsv ~= nil and bodyShouldRender ~= nil then
        rec.Choice = choice
        rec.DesiredCcsv = ccsv
        if not bodyShouldRender then
            return false, "deferred", tattooHandled
        end
        if ApplyCcsv(char, ccsv, choice) then
            return true, "ccsv-written", tattooHandled
        end
        return false, "ccsv-failed", tattooHandled
    end
    return false, tattooHandled and "unavailable" or "not-applied", tattooHandled
end

local function ReapplyTattooPolicy(reason)
    local pv = EnsurePV()
    local refreshed, deferred, current = 0, 0, 0
    for char, rec in pairs(pv.Bodies or {}) do
        if not R1CanWrite("tattoo-reapply", char) then goto continue end
        local choice = rec.Choice
        if choice == "sbbf" or choice == "bcb" then
            local entity = GetEntity(char)
            if entity == nil then
                Log(("ReapplyTattooPolicy: %s unavailable (choice=%s); record retained for load reconciliation.")
                    :format(tostring(char), tostring(choice)))
            else
                local race, bt, bs
                pcall(function() race, bt, bs = Shared.ReadCharStats(entity) end)
                if TattooPolicy.IsHumF(race, bt, bs) then
                    local vr, ccsv, tattooHandled = ResolveBodyVr(choice, race, bt, bs)
                    local bodyShouldRender = ShouldRenderNakedBody(char)
                    local _, result = ApplyNakedBody(
                        char, choice, rec, vr, ccsv, tattooHandled, bodyShouldRender)
                    if result == "base-written" or result == "ccsv-written" then
                        refreshed = refreshed + 1
                    elseif result == "deferred" then
                        deferred = deferred + 1
                    elseif result == "base-current" then
                        current = current + 1
                    elseif result == "ccsv-failed" then
                        Warn(("ReapplyTattooPolicy: validated tattoo CCSV application failed for %s (choice=%s).")
                            :format(tostring(char), tostring(choice)))
                    elseif result == "unavailable" then
                        Warn(("ReapplyTattooPolicy: validated tattoo pair unavailable for %s (choice=%s).")
                            :format(tostring(char), tostring(choice)))
                    end
                end
            end
        end
        ::continue::
    end
    Log(("ReapplyTattooPolicy(%s): refreshed=%d deferred=%d current=%d."):format(
        tostring(reason), refreshed, deferred, current))
    return refreshed, deferred
end

local function SetBodyTattooPolicy(policy, source)
    if policy ~= "match" and policy ~= "always_hide" then
        Warn(("Body tattoo policy rejected: invalid enum '%s' from %s."):format(
            tostring(policy), tostring(source)))
        return false
    end
    local pv = EnsurePV()
    local old = pv.BodyTattooPolicy
    if old == policy then
        Log(("Body tattoo policy unchanged at '%s' (%s); no reapply."):format(
            tostring(policy), tostring(source)))
        return false
    end
    PersistentVars.BodyTattooPolicy = policy
    Log(("Body tattoo policy: '%s' -> '%s' (%s)."):format(
        tostring(old), tostring(policy), tostring(source)))
    ReapplyTattooPolicy(source)
    return true
end

-- SetDesiredBody(char, choice): record the player's pick (what to show when
-- nude) then Reconcile so it only renders if the torso is bare. This is the
-- clothing-aware path used by !cm_setbody.
-- v4: ALSO drives the clothed half (EquipmentRace flip) so one command sets
-- the whole character. The two halves stay mutually exclusive via Reconcile
-- (nude CCSV only when torso bare; ER only affects worn gear).
local function SetDesiredBodyManaged(char, choice)
    if not R1CanWrite("set-desired-body", char) then return false end
    local pv = EnsurePV()
    pv.Bodies[char] = pv.Bodies[char] or { Choice = "vanilla" }
    local rec = pv.Bodies[char]
    local priorDesiredCcsv = rec.DesiredCcsv
    local entity = GetEntity(char)
    local race, bt, bs
    pcall(function() race, bt, bs = Shared.ReadCharStats(entity) end)
    local familyId = BodyFamilyRegistry.ResolveOfficialFamily(race, bt, bs)
    if familyId ~= nil then
        local profile, why = BodyFamilyRegistry.ResolveProfile(familyId, choice)
        if profile == nil then
            local currentEquipRace = BodyFamilyEquipRace.ReadEquipRace(char)
            local managed = rec.BodyFamilyId ~= nil
                or BodyFamilyRegistry.IsMintedEquipmentRace(currentEquipRace)
            local recovered = false
            if managed then
                pcall(function()
                    recovered = BodyFamilyEquipRace.RecoverUnavailable(char, rec, choice, function()
                        if not StripOurOverride(char, "permanent", rec.AppliedCcsv or rec.DesiredCcsv) then
                            error("ccsv-retirement-failed")
                        end
                        if MECHANISM == "C" then
                            local okBase = SetBaseBody(char, "vanilla", nil)
                            if not okBase then error("base-body-restore-failed") end
                        end
                    end)
                end)
            else
                rec.UnavailableFamilyChoice = choice
            end
            Warn(("SetDesiredBody: ordinary Tiefling BT1 profile unavailable for %s (%s); managed=%s recovery=%s")
                :format(tostring(choice), tostring(why), tostring(managed), tostring(recovered)))
            return false
        end
        rec.UnavailableFamilyChoice = nil
        rec.Reverted = nil
        rec.BodyFamilyId = familyId
        local okNude, nudeResult = ApplyNakedBody(char, choice, rec, profile.visual, profile.ccsv, false,
            ShouldRenderNakedBody(char))
        if nudeResult == "ccsv-retirement-failed" then return false end
        local okClothed = false
        pcall(function() okClothed = BodyFamilyEquipRace.SetClothed(char, choice, rec) == true end)
        if okClothed and not okNude then rec.Choice = choice end
        return okNude or okClothed
    end
    if choice == "vanilla" then
        local retirementTarget = rec.AppliedCcsv or priorDesiredCcsv
        if retirementTarget ~= nil
            and not StripOurOverride(char, "permanent", retirementTarget) then
            Warn("SetDesiredBody(vanilla): CCSV retirement readback failed")
            return false
        end
        pv.Bodies[char].Choice = "vanilla"
        pv.Bodies[char].DesiredCcsv = nil
        pv.Bodies[char].Reverted = nil  -- v4.19: an explicit pick, not a revert
        -- v4.19 HOTFIX: FORCE the true vanilla body (minted VR) instead of the
        -- v4.15 restore-original, which on body-replacer installs is not
        -- vanilla-shaped. Unmapped race / unresolvable bank / failed write all
        -- fall back to the v4.18 restore-original (no-op if never written).
        if MECHANISM == "C" then
            local forced = false
            local ventity = GetEntity(char)
            if ventity ~= nil then
                local vvr = ResolveVanillaBodyVr(ventity)
                if vvr ~= nil then
                    local okBase = SetBaseBody(char, "vanilla", vvr)
                    forced = (okBase == true)
                end
            end
            if not forced then
                pcall(function() SetBaseBody(char, "vanilla", nil) end)
            end
        end
        pcall(function() EquipRace.SetClothed(char, "vanilla", pv.Bodies[char]) end)
        return true
    end
    -- The two halves are INDEPENDENT: a missing nude CCSV mapping must not
    -- block the clothed flip (bug found in-game 2026-07-04: Shadowheart's
    -- unmapped race key aborted before SetClothed ever ran).
    local okNude, okClothed = false, false
    local vr, ccsv, tattooHandled = ResolveBodyVr(choice, race, bt, bs)
    local mapKey
    if ccsv == nil and not tattooHandled then ccsv, mapKey = Shared.ResolveCcsv(choice, race, bt, bs) end
    -- v4.15 PRIMARY: re-point the base body (Outcome C). On success the CCSV
    -- overlay is retired for this character (single-body render).
    local nakedResult
    okNude, nakedResult = ApplyNakedBody(char, choice, rec, vr, ccsv, tattooHandled, nil)
    if nakedResult == "ccsv-retirement-failed" then return false end
    -- FALLBACK (mechanism off / no CV / write rejected / unmapped): the proven
    -- v4.13 CCSV overlay path, unchanged.
    if not okNude then
        if ccsv == nil then
            if tattooHandled then
                Warn(("SetDesiredBody: validated tattoo pair unavailable; nude half skipped "
                    .. "(choice=%s race=%s bt=%s bs=%s); attempting clothed half."):format(
                    tostring(choice), tostring(race), tostring(bt), tostring(bs)))
            else
                Warn(("SetDesiredBody: no CCSV mapped for key '%s' (race=%s bt=%s bs=%s) - "
                    .. "nude half SKIPPED; attempting clothed half."):format(
                    tostring(mapKey), tostring(race), tostring(bt), tostring(bs)))
            end
        else
            if rec.AppliedCcsv == nil and priorDesiredCcsv ~= nil
                and tostring(priorDesiredCcsv):lower() ~= tostring(ccsv):lower()
                and not StripOurOverride(char, "permanent", priorDesiredCcsv) then
                Warn("SetDesiredBody: superseded concealed CCSV retirement failed")
                return false
            end
            rec.Choice = choice
            rec.DesiredCcsv = ccsv
            local reconciled, reconcileFailure = Reconcile(char, "setbody")
            okNude = reconciled == true
            if reconcileFailure == "ccsv-retirement-failed" then return false end
        end
    end
    -- Clothed half: flip EquipmentRace if this choice has minted clothed assets
    -- (sbbf only in v1).
    if EquipRace.MINTED[choice] ~= nil then
        local okC
        pcall(function() okC = EquipRace.SetClothed(char, choice, rec) end)
        okClothed = (okC == true)
    else
        Log(("SetDesiredBody: '%s' has no clothed (EquipmentRace) assets yet; nude half only."):format(tostring(choice)))
    end
    if okClothed and not okNude then rec.Choice = choice end  -- record intent
    return okNude or okClothed
end

SetDesiredBody = function(char, choice)
    if R1Runtime == nil then return SetDesiredBodyManaged(char, choice) end
    char = NormGuid(char)
    if type(choice) ~= "string" or not Shared.IsValidBodyChoice(choice) then
        return false, "invalid-choice"
    end
    R1Runtime:RefreshState()
    if R1Runtime.schemaFailure ~= nil then return false, R1Runtime.schemaFailure end
    if PersistentVars.CleanupState ~= "idle" then return false, "cleanup-state" end
    if choice == "external" then
        if PersistentVars.Bodies[char]==nil then
            local rec={Choice="external",PreferredChoice="vanilla",OriginalVisuals={},OwnedCcsvs={},
                RemovedOriginalVisuals={},HistoricalOriginals={},RestoreFailures={},RestoreState="clean"}
            local captured,why=R1Runtime.deps.captureBaseline(char,rec,false)
            if not captured then return false,why end
            PersistentVars.Bodies[char]=rec
            return true,"external-baseline-captured"
        end
        local result = R1Runtime:SetExternal(char)
        return result ~= nil and result.ok == true, result and result.status
    end
    if PersistentVars.CleanupState ~= "idle" then return false, "cleanup-state" end
    if PersistentVars.MasterEnabled == false then
        local rec = PersistentVars.Bodies[char]
        if rec == nil then return false, "character-not-tracked" end
        rec.Choice, rec.PreferredChoice = choice, choice
        return true, "deferred: master disabled"
    end
    local ok = R1Runtime:RunExplicitManaged(char, choice, function()
        return R1WithCapability("explicit_managed", char, function()
            return SetDesiredBodyManaged(char, choice)
        end)
    end)
    return ok == true, ok and "applied" or "managed-apply-failed"
end

R1Runtime = R1Foundation.Install(MOD, EnsurePV(), {
    schema = SCHEMA_DEPS,
    getState = function() return EnsurePV() end,
    persist = function() end,
    afterRestore = function(char,record)
        if PersistentVars.MasterEnabled~=true or PersistentVars.MasterState~="enabled" then return true end
        for other,otherRecord in pairs(PersistentVars.Bodies or {}) do
            if other~=char and otherRecord.CvGuid==record.CvGuid
                and R1Runtime:CanManagedWrite("shared-cv-peer",other) then
                if not SetDesiredBody(other,otherRecord.Choice) then return false end
            end
        end
        return true
    end,
    captureBaseline = function(char, rec, wasManaged)
        local entity = GetEntity(char)
        local cv = GetCharCV(char)
        local cca = GetCCA(entity)
        if entity == nil or cv == nil or cca == nil then return false,"character-unavailable" end
        if rec.CvGuid ~= nil and rec.CvGuid ~= cv then return false,"body-cv-mismatch" end
        local body = wasManaged and rec.OrigBodySetVisual or ReadBaseBody(cv)
        local equipment = wasManaged and (rec.FamilyOrigEquipRace or rec.OrigEquipRace) or EquipRace.ReadEquipRace(char)
        if not IsTrustedSchema6BodyOriginal(body,cv) then return false,"base-original-untrusted" end
        if not IsTrustedSchema6EquipOriginal(equipment,rec,char) then return false,"equipment-original-untrusted" end
        local visuals, readable = ReadVisuals(cca)
        if not readable then return false,"visuals-unreadable" end
        local originalVisuals={}
        for _,visual in ipairs(visuals) do
            if not (rec.OwnedCcsvs or {})[visual] then originalVisuals[#originalVisuals+1]=visual end
        end
        rec.CvGuid,rec.OrigBodySetVisual=cv,body
        rec.OrigEquipRace=equipment
        local race,bt,bs=Shared.ReadCharStats(entity)
        if race==nil or bt==nil or bs==nil then return false,"character-tuple-unreadable" end
        if BodyFamilyRegistry.ResolveOfficialFamily(race,bt,bs)~=nil then rec.FamilyOrigEquipRace=equipment end
        rec.OriginalVisuals=originalVisuals
        return true
    end,
    applyManaged = function(char, _record, choice)
        local capability=PersistentVars.MasterState=="enabling" and "ordinary_reenable" or "explicit_managed"
        return R1WithCapability(capability, char, function()
            return SetDesiredBodyManaged(char, choice)
        end)
    end,
    isCharacterAvailable = function(char) return GetEntity(char) ~= nil end,
    readVisuals = function(char)
        local cca = GetCCA(GetEntity(char))
        if cca == nil then return nil end
        return ReadVisuals(cca)
    end,
    writeVisuals = function(char, visuals)
        local entity = GetEntity(char)
        local cca = GetCCA(entity)
        if entity == nil or cca == nil then return false end
        local ok = pcall(function()
            cca.Visuals = visuals
            entity:Replicate("CharacterCreationAppearance")
        end)
        return ok
    end,
    readCvGuid = GetCharCV,
    validateBodyOriginal = function(guid, cvGuid)
        return IsTrustedSchema6BodyOriginal(guid, cvGuid)
    end,
    writeBodySetVisual = function(char, cvGuid, guid)
        local ok = pcall(function()
            local resource = GetCVRes(cvGuid)
            resource.VisualSet.BodySetVisual = guid
        end)
        if ok then ForceVisualRebuild(char) end
        return ok
    end,
    readBodySetVisual = function(_char, cvGuid) return ReadBaseBody(cvGuid) end,
    validateEquipRaceOriginal = IsTrustedSchema6EquipOriginal,
    writeEquipRace = function(char, guid)
        local ok = pcall(function()
            local entity = GetEntity(char)
            entity.ServerCharacter.Template.EquipmentRace = guid
        end)
        return ok
    end,
    readEquipRace = EquipRace.ReadEquipRace,
    validateProviderClaim = function(guid, claim)
        local descriptor = PersistentVars.ProviderDescriptors
            and PersistentVars.ProviderDescriptors[claim.ProviderId] or nil
        if type(descriptor) ~= "table" then return false end
        local owner = descriptor.ownerModuleUuid or descriptor.OwnerModuleUuid
        local digest = descriptor.canonicalDigest or descriptor.ProviderDigest
        if tostring(owner or ""):lower() ~= tostring(claim.OwnerModuleUuid or ""):lower()
            or tostring(digest or ""):upper() ~= tostring(claim.ProviderDigest or ""):upper() then
            return false
        end
        local resources = descriptor.bodyCcsvs or descriptor.BodyCcsvs or {}
        for _, value in ipairs(resources) do
            if tostring(value):lower() == tostring(guid):lower() then return true end
        end
        return false
    end,
    activateProvider = function(descriptor)
        local payload = descriptor.canonicalPayload or {}
        if descriptor.kind == "external_refits" then
            return EquipRace.RegisterExternalRefits(
                payload.sourceName or descriptor.providerId, payload.maps, {
                    ownerModuleUuid = descriptor.ownerModuleUuid,
                    canonicalDigest = descriptor.canonicalDigest,
                })
        end
        return false
    end,
    providerResourceExists = function(guid)
        local resource
        pcall(function() resource = Ext.Resource.Get(guid, "Visual") end)
        return resource ~= nil
    end,
    providerExistingTarget = function(choice, source)
        local maps = EquipRace.REFIT_BY_VR and EquipRace.REFIT_BY_VR[choice]
        return maps and maps[tostring(source):lower()] or nil
    end,
    isModuleLoaded = function(uuid)
        local wanted, found = tostring(uuid):lower(), false
        pcall(function()
            for _, loaded in ipairs(Ext.Mod.GetLoadOrder() or {}) do
                if tostring(loaded):lower() == wanted then found = true; break end
            end
        end)
        return found
    end,
})

Ext.Require("PassThroughState.lua").BindModules({
    EquipRace=EquipRace, BodyFamilyEquipRace=BodyFamilyEquipRace,
}, R1CanWrite)

MOD.SetCharacterMode = function(characterGuid, choice, source)
    if type(characterGuid) ~= "string" or Targeting.NormGuid(characterGuid) == nil then
        return false, "invalid-character"
    end
    return SetDesiredBody(Targeting.NormGuid(characterGuid), choice)
end
MOD.GetOwnershipStatus = function(characterGuid)
    local pv = EnsurePV()
    local rec = pv.Bodies and pv.Bodies[NormGuid(characterGuid)] or nil
    local failures = {}
    for i,code in ipairs(rec and rec.RestoreFailures or {}) do failures[i]=code end
    local allowed = R1Runtime:CanManagedWrite("status",NormGuid(characterGuid))
    return {configuredChoice=rec and rec.Choice, preferredChoice=rec and rec.PreferredChoice,
        effectiveMode=allowed and rec and rec.Choice or "external", masterEnabled=pv.MasterEnabled,
        restoreState=rec and rec.RestoreState or "untracked",failureCodes=failures}
end

-- ---------------------------------------------------------------------------
-- ApplyBody(char, choice): map choice (sbbf|bcb|vanilla) -> CCSV via Shared and
-- apply it. "vanilla"/unmapped -> revert. Needs CCSV_MAP populated (and, for our
-- own bodies, the ClothMorphRuntime VisualBank pak loaded so the CCSV resolves).
-- ---------------------------------------------------------------------------
local function ApplyBody(char, choice)
    -- DEBUG-only nude-CCSV helper (exposed as MOD.ApplyBody); NOT wired to any
    -- command/MCM/net path. Its "vanilla"=full-revert semantic is intentional here
    -- and is DISTINCT from the mainline body pick (SetDesiredBody -> minted-vanilla
    -- flip that overrides BCB, 2026-07-15). Do not re-wire user paths to this.
    if char == nil then Warn("ApplyBody: no character"); return false end
    if choice == "vanilla" then return RevertChar(char) end

    local entity = GetEntity(char)
    local race, bt, bs
    pcall(function() race, bt, bs = Shared.ReadCharStats(entity) end)
    local ccsv, mapKey = Shared.ResolveCcsv(choice, race, bt, bs)
    if ccsv == nil then
        Warn(("ApplyBody: no CCSV mapped for key '%s' (race=%s bt=%s bs=%s). "
            .. "Populate CCSV_MAP / load ClothMorphRuntime."):format(
            tostring(mapKey), tostring(race), tostring(bt), tostring(bs)))
        return false
    end
    return ApplyCcsv(char, ccsv, choice)
end

-- ===========================================================================
-- STATUS / DIAGNOSTICS
-- ===========================================================================
local function DumpStatus(char)
    local pv = EnsurePV()
    if char == nil then Log("Status: no host character."); return end
    local entity = GetEntity(char)
    local race, bt, bs
    pcall(function() race, bt, bs = Shared.ReadCharStats(entity) end)
    local rec = pv.Bodies[char] or {}
    local cca = GetCCA(entity)
    local vis = ReadVisuals(cca)
    Log("---- cm_status ----")
    Log("  Character : " .. tostring(char))
    Log("  Race      : " .. tostring(race))
    Log("  BodyType  : " .. tostring(bt) .. "  BodyShape: " .. tostring(bs))
    Log("  Choice    : " .. tostring(rec.Choice or "vanilla"))
    Log("  OurCcsv   : " .. tostring(rec.AppliedCcsv or "(none)"))
    Log("  Desired   : " .. tostring(rec.DesiredCcsv or "(vanilla)"))
    Log("  Clothed   : " .. tostring(rec.ClothedChoice or "vanilla"))
    if MECHANISM == "C" then
        local cv = GetCharCV(char)
        Log("  BaseCV    : " .. tostring(cv or "(none)"))
        if cv ~= nil then
            Log("  BaseBody  : " .. tostring(ReadBaseBody(cv) or "?")
                .. "  (orig " .. tostring(rec.OrigBodySetVisual or "unrecorded") .. ")")
        end
    end
    Log("  Visuals (" .. tostring(#vis) .. "):")
    for i, g in ipairs(vis) do Log("    " .. i .. "  " .. tostring(g)) end
    Log("-------------------")
end

-- CCSV chain check (StaticData CCSV -> Ext.Resource Visual mesh).
local function CheckBody(char, ccsvArg)
    if char == nil then Log("cm_checkbody: no host character."); return end
    local pv = EnsurePV()
    local rec = pv.Bodies[char] or {}
    local ccsv = ccsvArg or rec.AppliedCcsv or "c0ffeeb0-d100-4b0d-9e57-5bbf00000001"
    Log("---- cm_checkbody ----  CCSV: " .. tostring(ccsv))
    local obj
    pcall(function() obj = Ext.StaticData.Get(ccsv, "CharacterCreationSharedVisual") end)
    if obj == nil then
        Warn("  CCSV did NOT resolve (StaticData). Engine has no such shared-visual.")
    else
        local vr
        pcall(function() vr = obj.VisualResource end)
        Log("  CCSV ok; wrapped VisualResource: " .. tostring(vr))
        if vr and tostring(vr) ~= "" then
            local mesh
            pcall(function() mesh = Ext.Resource.Get(tostring(vr), "Visual") end)
            if mesh == nil then
                Warn("  Visual mesh NOT registered -> body will not render. "
                    .. "(Need the VisualBank that defines this resource.)")
            else
                local sf
                pcall(function() sf = mesh.SourceFile end)
                Log("  Visual mesh ok; SourceFile: " .. tostring(sf))
            end
        end
    end
    Log("----------------------")
end

-- Find which component holds a GUID (discovery; see Shared.FindOverride).
local function FindOverride(char, search)
    local e = GetEntity(char)
    Log(("---- cm_findoverride char=%s search=%s ----"):format(tostring(char), tostring(search)))
    Shared.FindOverride(e, search, function(m) Log(m) end)
    Log("----------------------------------------")
end

-- ===========================================================================
-- CONSOLE COMMANDS (invoke with leading "!", e.g. !cm_status). Mirrored in
-- BootstrapClient.lua so they work from either console context.
-- ===========================================================================
local function Cmd_SetBody(_cmd, choice, charArg)
    choice = choice and tostring(choice):lower() or nil
    if not Shared.IsValidBodyChoice(choice) then
        Warn("!cm_setbody usage: !cm_setbody <vanilla|sbbf|bcb|external> [charGuid]"); return
    end
    local char = ResolveCommandChar(charArg); if not char then Warn("no character target"); return end
    local ok = SetDesiredBody(char, choice)
    DumpStatus(char)
    return ok
end

-- Server->client "applied" feedback (v4.13). Forward-declared here; ASSIGNED
-- after the net Channel is created (it needs Channel:Broadcast). Called by the
-- hotkey/net paths to sync the MCM radio on the controlling client.
local NotifyApplied

-- !cm_cyclebody [charGuid]  -- cycle vanilla->sbbf->bcb on the target (v4.13).
-- Lean path (no verbose DumpStatus, review m1); the client prints one cm_applied
-- line. Reads the current choice from the PV record (rec.Choice).
local function Cmd_CycleBody(_cmd, charArg)
    local char = ResolveCommandChar(charArg); if not char then Warn("no character target"); return end
    local pv = EnsurePV()
    local cur = (pv.Bodies[char] or {}).Choice or "vanilla"
    local nxt = Shared.NextBodyChoice(cur)
    Log(("CycleBody: %s '%s' -> '%s'"):format(tostring(char), tostring(cur), tostring(nxt)))
    local ok = SetDesiredBody(char, nxt)
    if NotifyApplied then NotifyApplied(char, nxt, ok ~= false) end
end

-- !cm_applyccsv <ccsvGuid>  -- apply ANY CCSV by GUID (testing w/ vanilla CCSVs)
local function Cmd_ApplyCcsv(_cmd, ccsv, charArg)
    local char=ResolveCommandChar(charArg)
    if not char or not R1CanWrite("debug-ccsv",char) then return false,"write-gate-closed" end
    local entity=GetEntity(char)
    local race,bt,bs=Shared.ReadCharStats(entity)
    local family=BodyFamilyRegistry.ResolveOfficialFamily(race,bt,bs)
    local choice
    for _,candidate in ipairs({"vanilla","sbbf","bcb"}) do
        local known
        if family then
            local profile=BodyFamilyRegistry.ResolveProfile(family,candidate)
            known=profile and profile.ccsv
        else
            local _,resolved=ResolveBodyVr(candidate,race,bt,bs)
            known=resolved
        end
        if known and tostring(known):lower()==tostring(ccsv):lower() then choice=candidate end
    end
    if not choice then return false,"ccsv-unowned-or-wrong-profile" end
    return R1Runtime:RunExplicitManaged(char,choice,function()
        return R1WithCapability("explicit_managed",char,function()
            local rec=PersistentVars.Bodies[char]
            local restored,why=SetBaseBody(char,choice,nil)
            if not restored and why~="shared-cv-fallback-required" then return false end
            if not ApplyCcsv(char,ccsv,choice) then return false end
            if family then return BodyFamilyEquipRace.SetClothed(char,choice,rec) end
            return EquipRace.SetClothed(char,choice,rec)
        end)
    end)
end

-- !cm_revert  -- strip our override, back to original body
local function Cmd_Revert(_cmd, charArg)
    local char = ResolveCommandChar(charArg); if not char then Warn("no character target"); return end
    RevertChar(char); DumpStatus(char)
end

local function Cmd_Status(_cmd, charArg)    DumpStatus(ResolveCommandChar(charArg)) end
local function Cmd_CheckBody(_cmd, a, charArg) CheckBody(ResolveCommandChar(charArg), a) end
local function Cmd_FindOverride(_cmd, a, b)
    local char, search
    if b ~= nil and b ~= "" then char, search = a, b else char, search = GetHostChar(), a end
    if not char or char == "" then Warn("!cm_findoverride [charGuid] <searchGuid>"); return end
    FindOverride(char, search)
end

-- !cm_slotcheck  -- diagnostic: print which item occupies each equipment slot,
-- so we can confirm the torso slot string the toggle keys on ("Breast").
local function Cmd_SlotCheck(_cmd, charArg)
    local char = ResolveCommandChar(charArg); if not char then Warn("no character target"); return end
    Log("---- cm_slotcheck ----  char: " .. tostring(char))
    for _, slot in ipairs({ "Breast", "VanityBody", "Cloak", "Helmet",
                            "Gloves", "Boots", "Underwear", "Amulet" }) do
        local it
        pcall(function() it = Osi.GetEquippedItem(char, slot) end)
        Log(("  %-12s = %s"):format(slot, tostring(it)))
    end
    Log(("  ArmourSet      = %s"):format(CurrentArmourSet(char)))
    Log(("  IsTorsoCovered = %s"):format(tostring(IsTorsoCovered(char))))
    Log("----------------------")
end

-- !cm_reconcile  -- manually re-run the clothed/nude toggle for the host.
local function Cmd_Reconcile(_cmd, charArg)
    local char = ResolveCommandChar(charArg); if not char then Warn("no character target"); return end
    Reconcile(char, "manual"); DumpStatus(char)
end

-- ---------------------------------------------------------------------------
-- EquipmentRace clothed-half commands (v4). !cm_setclothed flips ONLY the
-- clothed half (testing granularity); production path is !cm_setbody.
-- ---------------------------------------------------------------------------
local function Cmd_SetClothed(_cmd, choice, charArg)
    choice = choice and tostring(choice):lower() or nil
    if choice ~= "vanilla" and EquipRace.MINTED[choice] == nil then
        Warn("!cm_setclothed usage: !cm_setclothed <vanilla|sbbf> [charGuid]"); return
    end
    local char = ResolveCommandChar(charArg); if not char then Warn("no character target"); return end
    if not R1CanWrite("set-clothed", char) then return false end
    local pv = EnsurePV()
    -- v4.19: default record carries Reverted=true so a clothed-only pick never
    -- makes the char eligible for the forced true-vanilla BODY at load.
    pv.Bodies[char] = pv.Bodies[char] or { Choice = "vanilla", Reverted = true }
    EquipRace.SetClothed(char, choice, pv.Bodies[char])
    EquipRace.DumpStatus(char, pv.Bodies[char])
end

-- !cm_erpass [force]  -- run the blanket shared-mesh injection pass manually.
local function Cmd_ErPass(_cmd, forceArg)
    if not R1CanWrite("equipment-blanket-pass", nil) then return false end
    EquipRace.RunBlanketPass("sbbf", forceArg == "force")
end

-- !cm_erstatus  -- clothed-half diagnostics for the host.
local function Cmd_ErStatus(_cmd, charArg)
    local char = ResolveCommandChar(charArg); if not char then Warn("no character target"); return end
    local pv = EnsurePV()
    EquipRace.DumpStatus(char, pv.Bodies[char])
end

-- !cm_refresh  -- unequip/re-equip the host's visual slots (force re-render).
local function Cmd_Refresh(_cmd, charArg)
    local char = ResolveCommandChar(charArg); if not char then Warn("no character target"); return end
    if not R1CanWrite("equipment-refresh", char) then return false end
    EquipRace.RefreshEquipment(char)
end

-- !cm_seterace <equipmentRaceGuid>  -- MANUAL RECOVERY. Write an EquipmentRace
-- onto the selected character, record it as the original, mark clothed=vanilla,
-- and refresh. Use to un-stick a character whose original ER was lost, or to
-- verify a candidate original before trusting it. (Tav: ad21d837-...; SH: 76217761-...)
local function Cmd_SetERace(_cmd, guid, charArg)
    local char=ResolveCommandChar(charArg)
    if not char or not R1CanWrite("debug-recovery-er",char) then return false,"write-gate-closed" end
    local normalized=Targeting.NormGuid(guid)
    if not normalized or normalized~=tostring(guid):lower() then return false,"equipment-guid-invalid" end
    local rec=PersistentVars.Bodies[char]
    local entity=GetEntity(char)
    local race,bt,bs=Shared.ReadCharStats(entity)
    local family=BodyFamilyRegistry.ResolveOfficialFamily(race,bt,bs)
    if not IsTrustedSchema6EquipOriginal(normalized,rec,char)
        or (family and normalized~=BodyFamilyRegistry.SafeSourceEquipmentRace()) then
        return false,"equipment-original-untrusted-or-wrong-family"
    end
    return R1Runtime:RunExplicitManaged(char,rec.Choice,function()
        return R1WithCapability("explicit_managed",char,function()
            if not EquipRace.ForceSetEquipRace(char,normalized,rec) then return false end
            if family then rec.FamilyOrigEquipRace=normalized end
            return EquipRace.ReadEquipRace(char)==normalized
        end)
    end)
end

-- !cm_optout [off]  -- exclude the host's equipped torso item from vanilla-VR
-- remapping (hybrid modded outfits keep their authored look on flipped bodies).
-- "!cm_optout" turns it ON for the equipped torso item; "!cm_optout off" undoes.
local function Cmd_Optout(_cmd, arg, charArg)
    local on = (arg ~= "off")
    local char = ResolveCommandChar(charArg); if not char then Warn("no character target"); return end
    if not R1CanWrite("mcm-optout", char) then return false end
    local item
    for _, slot in ipairs(TORSO_SLOTS) do
        pcall(function()
            local it = Osi.GetEquippedItem(char, slot)
            if item == nil and it ~= nil and it ~= "" then item = it end
        end)
    end
    if item == nil then
        Warn("!cm_optout: nothing equipped in a torso slot - equip the item first, then run !cm_optout")
        return
    end
    local id = EquipRace.SetOptout(item, on)
    if id ~= nil then
        local pv = EnsurePV()
        pv.OptoutTemplates[id:lower()] = (on and true) or nil
        Log(("cm_optout: item %s template %s optout=%s (persisted)"):format(tostring(item), id, tostring(on)))
        EquipRace.RefreshEquipment(char)
    end
end

local function ExpectedEquipRace(char, choice)
    choice = choice and tostring(choice):lower() or nil
    if choice == nil or choice == "" then return nil end
    if EquipRace.MINTED[choice] ~= nil then return EquipRace.MINTED[choice] end
    if choice == "off" then  -- 2026-07-15: "off" = restore-original expectation; "vanilla" is now minted (handled above)
        local rec = EnsurePV().Bodies[char] or {}
        return rec.OrigEquipRace
    end
    return Targeting.NormGuid(choice) or choice
end

local function RunSharedProbe(charA, expectedA, charB, expectedB)
    charA, charB = Targeting.NormGuid(charA), Targeting.NormGuid(charB)
    if charA == nil or charB == nil then
        Warn("!cm_sharedprobe <charA> <expectedA> <charB> <expectedB>")
        return
    end
    local snapA = SharedTemplateProbe.ReadSnapshot(charA, { getEntity = GetEntity })
    local snapB = SharedTemplateProbe.ReadSnapshot(charB, { getEntity = GetEntity })
    local report = SharedTemplateProbe.CompareSnapshots({
        a = snapA,
        b = snapB,
        expectedA = ExpectedEquipRace(charA, expectedA),
        expectedB = ExpectedEquipRace(charB, expectedB),
    })
    Log("---- cm_sharedprobe ----")
    Log("  expectedA : " .. tostring(report.expectedA or expectedA))
    Log("  expectedB : " .. tostring(report.expectedB or expectedB))
    Log("  " .. SharedTemplateProbe.FormatReport(report))
    if report.sameTemplate and report.equipmentRaceLeak then
        Warn("cm_sharedprobe: FAIL - shared-template characters collapsed to the same EquipmentRace state.")
    elseif report.sameTemplate then
        Log("cm_sharedprobe: PASS - shared-template characters kept distinct EquipmentRace states.")
    else
        Warn("cm_sharedprobe: characters do not report the same template; this is not the shared-template isolation case.")
    end
    Log("------------------------")
end

-- !cm_sharedprobe <charA> <expectedA> <charB> <expectedB>
-- expected values can be vanilla, sbbf, bcb, or an EquipmentRace GUID.
local function Cmd_SharedProbe(_cmd, charA, expectedA, charB, expectedB)
    if not charA or not expectedA or not charB or not expectedB then
        Warn("!cm_sharedprobe <charA> <expectedA> <charB> <expectedB>")
        return
    end
    RunSharedProbe(charA, expectedA, charB, expectedB)
end

-- !cm_sharedapply <charA> <choiceA> <charB> <choiceB>
-- Applies two choices, then runs the shared-template isolation report.
local function Cmd_SharedApply(_cmd, charA, choiceA, charB, choiceB)
    charA, charB = Targeting.NormGuid(charA), Targeting.NormGuid(charB)
    choiceA = choiceA and tostring(choiceA):lower() or nil
    choiceB = choiceB and tostring(choiceB):lower() or nil
    if charA == nil or charB == nil or not Shared.IsValidBodyChoice(choiceA) or not Shared.IsValidBodyChoice(choiceB) then
        Warn("!cm_sharedapply <charA> <vanilla|sbbf|bcb> <charB> <vanilla|sbbf|bcb>")
        return
    end
    SetDesiredBody(charA, choiceA)
    SetDesiredBody(charB, choiceB)
    RunSharedProbe(charA, choiceA, charB, choiceB)
end

-- !cm_bcbpak          -> report detected state
-- !cm_bcbpak on|off   -> force the gate and re-run the vanilla pass
-- !cm_bcbpak auto     -> clear the override and re-probe the load order
-- NOTE: SERVER console only (no client mirror / net-channel arm yet). The
-- canonical Session-2 test is still "disable BCBPak in BG3MM and restart" --
-- this command is a convenience for spot-checks, NOT a substitute for it.
local function Cmd_BcbPak(_, arg)
    if not R1CanWrite("equipment-content-gate", nil) then return false end
    local a = arg and tostring(arg):lower() or nil
    if     a == "on"  or a == "1" or a == "true"  then EquipRace.SetBCBPakPresent(true)
    elseif a == "off" or a == "0" or a == "false" then EquipRace.SetBCBPakPresent(false)
    elseif a == "auto" or a == "nil"              then EquipRace.SetBCBPakPresent(nil)
    end
    local present = EquipRace.HasBCBPak()
    Log(("BCBPak present = %s  (base vanilla-VR remap %s; sbbf/bcb + external refits always on)")
        :format(tostring(present), present and "ENABLED" or "DISABLED"))
end

local function Cmd_Master(_cmd, arg)
    local value = arg and tostring(arg):lower() or nil
    if value=="status" then
        local result=MOD.GetStateDiagnostics()
        Log("MasterEnabled: "..tostring(result.MasterEnabled).." MasterState: "..tostring(result.MasterState))
        return result
    end
    if value ~= "on" and value ~= "off" then
        Warn("!cm_master <on|off>")
        return false
    end
    local accepted, result = MOD.SetMasterEnabled(value == "on", "server-console")
    Log(("Master state: status=%s state=%s gate=%s passThrough=%s"):format(
        tostring(result and result.status), tostring(PersistentVars.MasterState),
        tostring(PersistentVars.MutationGateClosed),
        tostring(PersistentVars.PassThroughRestoreComplete)))
    return accepted == true
end

local function Cmd_State()
    local diagnostics = MOD.GetStateDiagnostics()
    Log(("State: schema=%s master=%s state=%s gate=%s passThrough=%s cleanup=%s external=%d partial=%d blocked=%d"):format(
        tostring(diagnostics.PersistentSchema), tostring(diagnostics.MasterEnabled),
        tostring(diagnostics.MasterState), tostring(diagnostics.MutationGateClosed),
        tostring(diagnostics.PassThroughRestoreComplete), tostring(diagnostics.CleanupState),
        #diagnostics.ExternalGuids, #diagnostics.PartialGuids, #diagnostics.BlockedGuids))
    return diagnostics
end

local function Cmd_ProviderRegistry()
    return MOD.GetProviderRegistrySnapshot()
end

local function Cmd_PrepareRollback(_cmd, targetArtifactId, mode)
    return MOD.PrepareRuntimeRollbackV1(targetArtifactId, mode)
end

Ext.RegisterConsoleCommand("cm_bcbpak",       Cmd_BcbPak)
Ext.RegisterConsoleCommand("cm_optout",       Cmd_Optout)
Ext.RegisterConsoleCommand("cm_setbody",      Cmd_SetBody)
Ext.RegisterConsoleCommand("cm_cyclebody",    Cmd_CycleBody)
Ext.RegisterConsoleCommand("cm_applyccsv",    Cmd_ApplyCcsv)
Ext.RegisterConsoleCommand("cm_revert",       Cmd_Revert)
Ext.RegisterConsoleCommand("cm_status",       Cmd_Status)
Ext.RegisterConsoleCommand("cm_checkbody",    Cmd_CheckBody)
Ext.RegisterConsoleCommand("cm_findoverride", Cmd_FindOverride)
Ext.RegisterConsoleCommand("cm_slotcheck",    Cmd_SlotCheck)
Ext.RegisterConsoleCommand("cm_reconcile",    Cmd_Reconcile)
Ext.RegisterConsoleCommand("cm_setclothed",   Cmd_SetClothed)
Ext.RegisterConsoleCommand("cm_erpass",       Cmd_ErPass)
Ext.RegisterConsoleCommand("cm_erstatus",     Cmd_ErStatus)
Ext.RegisterConsoleCommand("cm_refresh",      Cmd_Refresh)
Ext.RegisterConsoleCommand("cm_seterace",     Cmd_SetERace)
Ext.RegisterConsoleCommand("cm_sharedprobe",  Cmd_SharedProbe)
Ext.RegisterConsoleCommand("cm_sharedapply",  Cmd_SharedApply)
Ext.RegisterConsoleCommand("cm_master",       Cmd_Master)
Ext.RegisterConsoleCommand("cm_state",        Cmd_State)
Ext.RegisterConsoleCommand("cm_providerregistry", Cmd_ProviderRegistry)
Ext.RegisterConsoleCommand("cm_prepare_rollback", Cmd_PrepareRollback)

local function MakeTattooProbeDeps()
    return {
        getEntity = GetEntity,
        getStaticData = function(guid, kind) return Ext.StaticData.Get(guid, kind) end,
        getAllStaticData = function(kind) return Ext.StaticData.GetAll(kind) end,
        getResource = function(guid, kind) return Ext.Resource.Get(guid, kind) end,
        getLoadedMod = function(uuid) return Ext.Mod.GetMod(uuid) end,
        readCharStats = Shared.ReadCharStats,
        getBodyChoice = function(char)
            local bodies = type(PersistentVars) == "table" and PersistentVars.Bodies or nil
            local rec = type(bodies) == "table" and bodies[char] or nil
            return type(rec) == "table" and rec.Choice or nil
        end,
        getPolicy = function()
            return type(PersistentVars) == "table" and PersistentVars.BodyTattooPolicy or nil
        end,
        detectEnvironment = function()
            return TattooPolicy.DetectEnvironment(function(uuid) return Ext.Mod.GetMod(uuid) end)
        end,
        getVariantRows = TattooPolicy.DescribeVariants,
        vanillaRows = {
            {
                key = "vanilla|forced|match", bodyChoice = "vanilla",
                environment = "forced", policy = "match",
                vr = "3bc12bd9-6c5e-5067-a20f-b17e45647a10", ccsv = nil,
            },
        },
    }
end

TattooDiagnostics.Register({
    register = function(name, handler) Ext.RegisterConsoleCommand(name, handler) end,
    resolveCharacter = ResolveCommandChar,
    log = Log,
    warn = Warn,
    policy = TattooPolicy,
    probe = TattooStateProbe,
    makeProbeDeps = MakeTattooProbeDeps,
})

-- ===========================================================================
-- NET CHANNEL -- client-context console commands forward intent to the server.
-- ===========================================================================
-- The client sends one-way messages via Channel:SendToServer, so the server must
-- register a MESSAGE handler with :SetHandler (NOT :SetRequestHandler, which only
-- catches RequestToServer). Using SetRequestHandler was the "no message handler
-- was registered" bug that made client-console (C >>) commands silently no-op.
local Channel = Ext.Net.CreateChannel(MOD.ModuleUUID or "ClothMorphRuntime", "ClothMorphRuntime_Cmd")
local function NetMessageArgs(a, b, c)
    if type(a) == "table" and a.cmd ~= nil then return a, b end
    if type(b) == "table" and b.cmd ~= nil then return b, c end
    return a, b
end

local function DispatchNetCmd(a, b, c)
    local data, user = NetMessageArgs(a, b, c)
    data = data or {}
    local cmd = data.cmd
    if cmd == "master" or cmd == "mcm_setmaster" then
        if not AuthorizeTattooPolicyUser(user) then
            pcall(function() MCM.Set("master_enabled", PersistentVars.MasterEnabled, ModuleUUID, false) end)
            return
        end
        return Cmd_Master("cm_master", data.arg)
    end
    if cmd == "mcm_set_tattoo_policy" then
        if not AuthorizeTattooPolicyUser(user) then return end
        if data.arg == "hide" then data.arg = "always_hide" end
        if data.arg ~= "match" and data.arg ~= "always_hide" then
            Warn(("Tattoo policy network update denied: invalid enum '%s'."):format(
                tostring(data.arg)))
            return
        end
        SetBodyTattooPolicy(data.arg, "network")
        return
    end
    if cmd == "prepare_rollback" then
        if not AuthorizeTattooPolicyUser(user) then return end
        local request = type(data.arg) == "table" and data.arg or {}
        Cmd_PrepareRollback("cm_prepare_rollback", request.targetArtifactId, request.mode)
        return
    end
    local char = nil
    if cmd ~= "erpass" then
        char = ResolveNetTarget(data, user)
        if char == nil then return end
    end
    if     cmd == "setbody"   then
        local ok = Cmd_SetBody("cm_setbody", data.arg, char)
        if NotifyApplied then NotifyApplied(char, data.arg, ok == true) end
    elseif cmd == "cyclebody" then Cmd_CycleBody("cm_cyclebody", char)
    elseif cmd == "mcm_setbody" then  -- MCM change forwarded from the client leg (deduped vs the server-side event); never NotifyApplied here (review m1: echo loop)
        McmGlue.NetApply({ Log = Log, Warn = Warn, IsValid = Shared.IsValidBodyChoice,
                           SetDesiredBody = SetDesiredBody }, data.arg, char)
    elseif cmd == "mcm_setmaster" then Cmd_Master("cm_master", data.arg)
    elseif cmd == "master" then Cmd_Master("cm_master", data.arg)
    elseif cmd == "state" then Cmd_State()
    elseif cmd == "providerregistry" then Cmd_ProviderRegistry()
    elseif cmd == "applyccsv" then Cmd_ApplyCcsv("cm_applyccsv", data.arg, char)
    elseif cmd == "revert"    then Cmd_Revert("cm_revert", char)
    elseif cmd == "status"    then Cmd_Status("cm_status", char)
    elseif cmd == "checkbody" then Cmd_CheckBody("cm_checkbody", data.arg, char)
    elseif cmd == "slotcheck" then Cmd_SlotCheck("cm_slotcheck", char)
    elseif cmd == "reconcile" then Cmd_Reconcile("cm_reconcile", char)
    elseif cmd == "setclothed" then Cmd_SetClothed("cm_setclothed", data.arg, char)
    elseif cmd == "erpass"    then Cmd_ErPass("cm_erpass", data.arg)
    elseif cmd == "erstatus"  then Cmd_ErStatus("cm_erstatus", char)
    elseif cmd == "refresh"   then Cmd_Refresh("cm_refresh", char)
    elseif cmd == "seterace"  then Cmd_SetERace("cm_seterace", data.arg, char)
    elseif cmd == "optout"    then Cmd_Optout("cm_optout", data.arg, char)
    else Warn("Net channel: unknown cmd '" .. tostring(cmd) .. "'") end
end
Channel:SetHandler(DispatchNetCmd)
-- Also accept request-style calls, in case a future client uses RequestToServer.
pcall(function()
    Channel:SetRequestHandler(function(a, b, c) DispatchNetCmd(a, b, c); return { ok = true } end)
end)

-- Assign the forward-declared NotifyApplied now that Channel exists (v4.13).
-- Broadcast (not SendToUser): the SP loopback makes per-user sends unreliable
-- here, so we broadcast and let the CLIENT filter to its own controlled char
-- (review M1). pcall-guarded: if Broadcast is unavailable the body switch still
-- works, only the MCM radio sync/console feedback is skipped.
NotifyApplied = function(char, choice, ok)
    -- Arm the B1 dedupe belt: mark this value applied so that IF an MCM radio
    -- echo (mcm_setbody) still reaches NetApply, it dedupes instead of
    -- double-applying. (Primary B1 defense is client-side MCM.Set(...,false).)
    if ok == true then
        pcall(function() McmGlue.NoteApplied(choice) end)
    end
    pcall(function()
        Channel:Broadcast({ cmd = "cm_applied", char = tostring(char),
                            choice = tostring(choice), ok = ok ~= false })
    end)
end

-- Expose for debugging.
MOD.ApplyBody = ApplyBody
MOD.ApplyCcsv = function()
    Warn("Mods.ClothMorphRuntime.ApplyCcsv is disabled in schema 7")
    return false
end
MOD.RevertChar = RevertChar
MOD.DumpStatus = DumpStatus
MOD.StripOurOverride = StripOurOverride
MOD.Reconcile = Reconcile
MOD.SetDesiredBody = function(char, choice, source)
    return MOD.SetCharacterMode(char, choice, source)
end
MOD.SetBaseBody = SetBaseBody
MOD.ReapplyBaseBodies = function(r) ReapplyBaseBodies(r or "manual") end
MOD.RestoreAllBaseWrites = RestoreAllBaseWrites

-- ===========================================================================
-- EQUIP / UNEQUIP AUTO-TOGGLE
--   Only chars we track (have a record in PV.Bodies) are managed. On any
--   torso equip change we Reconcile: covered -> strip nude override, bare ->
--   re-apply the desired CCSV. The Equip/Unequip event itself re-renders the
--   character, which avoids the strip-while-clothed stale-render problem seen
--   with a bare !cm_revert. Arg order is handled defensively (either may be the
--   character). Osi only exists server-side, so this lives here.
-- ===========================================================================
local function OnEquipChange(a, b, ev)
    local pv = EnsurePV()
    -- Normalize BOTH args before lookup: Osiris passes "Name_guid" forms here,
    -- while PV.Bodies is keyed by bare lowercase GUIDs (see NormGuid).
    local na, nb = NormGuid(a), NormGuid(b)
    local char, item = nil, nil
    if pv.Bodies[na] then char, item = na, b elseif pv.Bodies[nb] then char, item = nb, a end
    if char == nil then return end
    if not R1CanWrite("equip-event", char) then return end
    pcall(function() Reconcile(char, ev) end)
    -- Clothed half: a flipped char equipping an item whose template lacks our
    -- minted key (modded item / child template) would render INVISIBLE (P3).
    -- Late-inject + re-equip that item.
    if ev == "Equipped" and item ~= nil then
        if pv.Bodies[char].BodyFamilyId ~= nil then
            pcall(function() BodyFamilyEquipRace.OnEquipped(item, char, pv.Bodies[char]) end)
        else
            pcall(function() EquipRace.OnEquipped(item, char, pv.Bodies[char]) end)
        end
    end
end

pcall(function()
    Ext.Osiris.RegisterListener("Equipped", 2, "after",
        function(item, char) OnEquipChange(item, char, "Equipped") end)
    Ext.Osiris.RegisterListener("Unequipped", 2, "after",
        function(item, char) OnEquipChange(item, char, "Unequipped") end)
    Log("Equip/Unequip auto-toggle listeners registered.")
end)

-- v4.4: re-reconcile when the armour set flips (camp arrival/departure). All
-- vanilla set changes route through the story PROC_SetArmourSet(_Char, _Set);
-- user-defined PROCs ARE capturable by BG3SE (built-in SetArmourSet is NOT,
-- per API.md). Defensive pcall: if the PROC name ever changes, the Equipped/
-- Unequipped listeners still cover most transitions.
pcall(function()
    Ext.Osiris.RegisterListener("PROC_SetArmourSet", 2, "after",
        function(char, _set)
            local pv = EnsurePV()
            local n = NormGuid(char)
            if pv.Bodies[n] ~= nil then
                pcall(function() Reconcile(n, "armourset") end)
            end
        end)
    Log("PROC_SetArmourSet reconcile listener registered.")
end)

-- ===========================================================================
-- LIFECYCLE
--   Overrides PERSIST in the save, so we do NOT re-apply on load (that would
--   stack). We only normalize PersistentVars here.
-- ===========================================================================
Ext.Events.SessionLoaded:Subscribe(function()
    -- v1.3: one-shot check for the retired standalone Githyanki add-on.
    pcall(function() EquipRace.HasLegacyGithyankiPak() end)
    EnsurePV()
    -- BCBPak presence probe (2026-07-26, Alan's rule). Resolved ONCE here inside
    -- the existing handler -- no new subscription, no per-tick cost. Must run
    -- BEFORE RunBlanketPass below, which consults it for the `vanilla` choice.
    -- Gates ONLY the BASE vanilla-VR remap: sbbf/bcb are base Content, and
    -- externally merged vanilla entries (ClothMorphSCO's, which defend against
    -- BCBScantily) are deliberately exempt. Rationale: EquipRace.lua header.
    pcall(function() EquipRace.HasBCBPak() end)
    -- Seed the remap opt-out set from the save (persisted by !cm_optout).
    local nOpt = 0
    for tid, v in pairs(PersistentVars.OptoutTemplates or {}) do
        if v then EquipRace.OPTOUT[tostring(tid):lower()] = true; nOpt = nOpt + 1 end
    end
    if nOpt > 0 then Log(("SessionLoaded: seeded %d remap opt-out template(s)."):format(nOpt)) end
    local n, nClothed = 0, 0
    local choices = {}
    for _, rec in pairs(R1Runtime:FilterManagedBodies()) do
        n = n + 1
        if rec.ClothedChoice ~= nil and EquipRace.MINTED[rec.ClothedChoice] ~= nil then  -- 2026-07-15: gate on MINTED (incl. vanilla), not ~="vanilla"
            nClothed = nClothed + 1
            choices[rec.ClothedChoice] = true
        end
        -- C2 companion (2026-07-06): a character flagged NeedsRecovery (or with a
        -- recorded orig) may still carry a persisted minted ER even though its
        -- ClothedChoice reads vanilla - keep the pass alive so gear stays visible.
        if rec.NeedsRecovery and rec.ClothedChoice ~= nil and EquipRace.MINTED[rec.ClothedChoice] ~= nil then  -- 2026-07-15: gate on MINTED
            choices[rec.ClothedChoice] = true
        elseif rec.NeedsRecovery then
            choices["sbbf"] = true  -- unknown choice: sbbf pass is the safe default
        end
    end
    Log(("SessionLoaded: schema v%d, %d recorded choice(s) (%d clothed). Nude overrides "
        .. "persist in the save; not re-applying those."):format(PersistentVars.Version or 0, n, nClothed))
    -- Clothed half: template writes are NOT save-persistent -> run the blanket
    -- injection pass now for EVERY distinct persisted choice (C1 fix 2026-07-06:
    -- was hardcoded "sbbf", which left bcb-flipped characters invisible on reload).
    for choice in pairs(choices) do
        if R1CanWrite("session-blanket-pass", nil) then
            pcall(function() EquipRace.RunBlanketPass(choice, false) end)
        end
    end
end)

-- Re-apply clothed flips once characters exist / after a save is loaded.
-- (EquipRace.ReapplyAll is idempotent: it skips chars already on the minted GUID.)
local MCM_DEPS = { Log = Log, Warn = Warn, IsValid = Shared.IsValidBodyChoice,
                   ResolveMcmTarget = function() return nil end,
                   SetDesiredBody = SetDesiredBody,
                   AuthorizeTattooPolicy = AuthorizeMcmTattooPolicy,
                   RestoreTattooPolicy = RestoreMcmTattooPolicy,
                   SetBodyTattooPolicy = SetBodyTattooPolicy,
                   SetMasterEnabled = function(enabled)
                       if AuthorizeMcmTattooPolicy() ~= true then
                           pcall(function() MCM.Set("master_enabled",PersistentVars.MasterEnabled,ModuleUUID,false) end)
                           return false,"unauthorized-master"
                       end
                       return MOD.SetMasterEnabled(enabled,"mcm-server")
                   end,
                   CanApplyOnLoad = function()
                       return R1CanWrite("mcm-apply-on-load", nil)
                   end }
pcall(function()
    Ext.Osiris.RegisterListener("LevelGameplayStarted", 2, "after", function(_level, _isEditor)
        local pv = EnsurePV()
        -- v4.15 SF-2: restore-then-reapply here too - a NEW GAME in the same
        -- process fires LevelGameplayStarted without SavegameLoaded, and must
        -- not inherit another save's CV edits (origin CVs are shared pak
        -- resources). Idempotent churn on act transitions is acceptable.
        pcall(function()
            R1WithCapability("maintenance_restore", nil, function()
                RestoreAllBaseWrites("LevelGameplayStarted", BaseRestoreToken)
            end)
        end)
        R1Runtime:ResumePending()
        pcall(function() ReapplyBaseBodies("LevelGameplayStarted") end)
        -- v4.10: flush any queued external (add-on) refit entries BEFORE reapply.
        if R1CanWrite("load-provider-retry", nil) then
            pcall(function() EquipRace.RetryPendingExternalRefits() end)
        end
        -- v4.13 F1: verify the ClothMorphRuntime VisualBank is actually present.
        -- If absent, base-map refits would resolve to nothing (invisible gear);
        -- CheckContentPresence flips a safe pass-through flag + forces a re-pass
        -- so gear renders vanilla-shaped (visible) instead, and warns loudly.
        if R1CanWrite("load-content-check", nil) then
            pcall(function() EquipRace.CheckContentPresence() end)
        end
        -- v4.13 provenance: warn if a registered add-on's source mod is absent or
        -- has drifted since its refits were generated (log-only; never blocks).
        pcall(function() EquipRace.CheckExternalSources() end)
        local managedBodies = R1Runtime:FilterManagedBodies()
        pcall(function() EquipRace.ReapplyAll(managedBodies, "LevelGameplayStarted") end)
        pcall(function() BodyFamilyEquipRace.ReapplyAll(managedBodies, "LevelGameplayStarted") end)
        -- no-op unless MCM present and apply_on_load enabled:
        McmGlue.ApplyOnLoad(MCM_DEPS)
    end)
    Ext.Osiris.RegisterListener("SavegameLoaded", 0, "after", function()
        local pv = EnsurePV()
        -- v4.15: cross-save hygiene THEN re-apply this save's choices.
        pcall(function()
            R1WithCapability("maintenance_restore", nil, function()
                RestoreAllBaseWrites("SavegameLoaded", BaseRestoreToken)
            end)
        end)
        R1Runtime:ResumePending()
        pcall(function() ReapplyBaseBodies("SavegameLoaded") end)
        -- v4.10: flush queued external (add-on) refit entries here too (S1).
        if R1CanWrite("load-provider-retry", nil) then
            pcall(function() EquipRace.RetryPendingExternalRefits() end)
        end
        local managedBodies = R1Runtime:FilterManagedBodies()
        pcall(function() EquipRace.ReapplyAll(managedBodies, "SavegameLoaded") end)
        pcall(function() BodyFamilyEquipRace.ReapplyAll(managedBodies, "SavegameLoaded") end)
        McmGlue.ApplyOnLoad(MCM_DEPS)
    end)
    Log("Clothed-half re-apply listeners registered (LevelGameplayStarted/SavegameLoaded).")
end)

-- MCM bridge: live body_choice changes from the MCM UI (hard dependency as of
-- v4.7; guards still degrade to a logged no-op if MCM is missing/failed).
McmGlue.InstallServer(MCM_DEPS)

-- v4.10: external refit registration hook for optional content paks (first
-- consumer: ClothMorphSCO). Exposed as a ModTable global so an add-on's SE
-- module can call Mods.ClothMorphRuntime.RegisterExternalRefits(name, maps).
RegisterExternalRefits = function(sourceName, maps, info)
    return R1Runtime.ProviderRegistry:RegisterExternalRefits(sourceName, maps, info)
end

-- Test-only body-family provider hooks. The registry accepts only the exact
-- ordinary female Tiefling BT1 definition; missing resources fail closed.
MOD.BodyFamilyApiVersion = 1
RegisterBodyFamily = function(sourceName, spec)
    if not R1CanWrite("register-body-family", nil) then return false end
    return BodyFamilyRegistry.RegisterBodyFamily(sourceName, spec)
end
RegisterFamilyRefits = function(sourceName, familyId, maps, info)
    if not R1CanWrite("register-family-refits", nil) then return false end
    return BodyFamilyEquipRace.RegisterFamilyRefits(sourceName, familyId, maps, info)
end
MOD.RegisterBodyFamily = RegisterBodyFamily
MOD.RegisterFamilyRefits = RegisterFamilyRefits
ReapplyBodyFamilies = function(reason)
    local pv = EnsurePV()
    reason = tostring(reason or "provider-register")
    ReapplyBaseBodies(reason)
    return BodyFamilyEquipRace.ReapplyAll(R1Runtime:FilterManagedBodies(), reason)
end
MOD.ReapplyBodyFamilies = ReapplyBodyFamilies

-- 2026-07-22: external revealing-garment registration. An add-on whose garments
-- are revealing (open chest / sheer / high-cut, so the body shows through) calls
-- Mods.ClothMorphRuntime.RegisterExternalRevealing({ ids }) to KEEP the selected
-- body under them instead of stripping it (otherwise a body-cut garment sits over
-- the vanilla base body -> mismatch). ids may be a carried template id, parent
-- template id, OR a Human-F source VisualResource id -- the same keys
-- ItemIsRevealing() matches on. Additive; safe to call at SessionLoaded.
RegisterExternalRevealing = function(ids)
    if not R1CanWrite("register-revealing", nil) then return false end
    if type(ids) ~= "table" then
        Warn("RegisterExternalRevealing: ids is not a table"); return false
    end
    local n = 0
    for _, id in ipairs(ids) do
        local k = tostring(id):lower()
        if k ~= "" and REVEALING_TORSO[k] == nil then REVEALING_TORSO[k] = true; n = n + 1 end
    end
    Log(("RegisterExternalRevealing: added %d revealing id(s)."):format(n))
    return n > 0
end

Log("BootstrapServer v4.22-s7-foundation loaded (schema 7 + ordinary master state + per-character External + ownership ledger + common mutation gate). Commands: !cm_setbody <vanilla|sbbf|bcb|external> | !cm_master <on|off> | !cm_state | !cm_cyclebody |"
    .. "!cm_setclothed <vanilla|sbbf> | !cm_seterace <guid> | !cm_erpass [force] | !cm_erstatus | !cm_refresh | "
    .. "!cm_applyccsv <ccsvGuid> | !cm_revert | !cm_status | !cm_checkbody | !cm_findoverride | !cm_tattootest | "
    .. "!cm_tattoodump [character-guid] (server only). Hotkeys: bind in MCM (unbound by default).")
