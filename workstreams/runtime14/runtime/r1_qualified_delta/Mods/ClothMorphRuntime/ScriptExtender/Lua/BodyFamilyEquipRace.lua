-- ClothMorphRuntime test-only EquipmentRace bridge for registered body families.
-- Template injection is completed before a character is flipped.  Templates
-- without a family-specific array copy the exact source array; registered VR
-- replacements are applied only when the source VR is an exact map key.

local Registry = Ext.Require("BodyFamilyRegistry.lua")
local EquipRace = Ext.Require("EquipRace.lua")
local M = {}
local PassThrough = Ext.Require("PassThroughState.lua")

local function Log(msg)
    Ext.Utils.Print("[ClothMorphRuntime:BodyFamilyEquipRace] " .. tostring(msg))
end
local function Warn(msg)
    Ext.Utils.PrintWarning("[ClothMorphRuntime:BodyFamilyEquipRace] " .. tostring(msg))
end
local function lc(v) return tostring(v or ""):lower() end

local VISUAL_SLOTS = { "Breast", "VanityBody", "Cloak", "Helmet", "Gloves", "Boots", "Underwear" }
local registrations = {}
local passDone = {}
local passRevision = {}

local function owner(familyId)
    return registrations[tostring(familyId or "")]
end

function M.RegisterFamilyRefits(sourceName, familyId, maps, info)
    sourceName = tostring(sourceName or "")
    familyId = tostring(familyId or "")
    local provider = Registry.GetProvider(familyId)
    if provider == nil or provider.sourceName ~= sourceName then
        Warn("RegisterFamilyRefits: body family must be registered by the same provider first")
        return false
    end
    local function reject(message)
        Warn(message)
        registrations[familyId] = nil
        passDone[familyId] = nil
        passRevision[familyId] = nil
        Registry.UnregisterBodyFamily(sourceName, familyId)
        return false
    end
    if type(maps) ~= "table" then
        return reject("RegisterFamilyRefits: maps missing")
    end
    local normalized = {}
    for _, choice in ipairs({ "vanilla", "sbbf", "bcb" }) do
        normalized[choice] = {}
        if type(maps[choice]) ~= "table" then
            return reject("RegisterFamilyRefits: missing " .. choice .. " map")
        end
        for from, to in pairs(maps[choice]) do
            if lc(from) == "" or lc(to) == "" then
                return reject("RegisterFamilyRefits: blank VR key")
            end
            local target = tostring(to)
            local resolved = false
            pcall(function() resolved = Ext.Resource.Get(target, "Visual") ~= nil end)
            if not resolved then
                return reject("RegisterFamilyRefits: unresolved target VR " .. target)
            end
            normalized[choice][lc(from)] = target
        end
    end
    registrations[familyId] = {
        sourceName = sourceName,
        maps = normalized,
        info = info or {},
    }
    passDone[familyId] = nil
    passRevision[familyId] = nil
    Log("registered exact refit maps for " .. familyId .. " from " .. sourceName)
    return true
end

local function getTemplate(char)
    local template
    pcall(function()
        local entity = Ext.Entity.Get(char)
        if entity ~= nil and entity.ServerCharacter ~= nil then
            template = entity.ServerCharacter.Template
        end
    end)
    return template
end

function M.ReadEquipRace(char)
    local template = getTemplate(char)
    if template == nil then return nil end
    local value
    pcall(function() value = tostring(template.EquipmentRace) end)
    return value
end

local function effectiveVisuals(equipment, sourceRace, fallbackRace)
    local function readArray(race)
        if lc(race) == "" then return nil end
        local array
        pcall(function() array = equipment.Visuals[lc(race)] end)
        if array == nil then return nil end
        local out = {}
        local ok = pcall(function()
            for _, visual in ipairs(array) do out[#out + 1] = tostring(visual) end
        end)
        -- An empty explicit Tiefling array is deliberately absent so the
        -- Human Female fallback can supply the source without concatenation.
        if not ok or #out == 0 then return nil end
        return out
    end
    return readArray(sourceRace) or readArray(fallbackRace)
end

local function buildArray(registration, choice, source)
    local mature, matureChanged = EquipRace.BuildMappedArray(choice, source)
    local map = registration.maps[choice]
    local out, providerChanged = {}, false
    for index, original in ipairs(source) do
        local replacement = map[lc(original)]
        if replacement ~= nil then
            out[index] = replacement
            providerChanged = true
        else
            out[index] = mature[index]
        end
    end
    return out, (matureChanged or providerChanged)
end

local function injectTemplate(familyId, choice, template, overwrite)
    local registration = owner(familyId)
    local definition = Registry.GetOfficialDefinition()
    if registration == nil or definition.id ~= familyId or template == nil then return "skipped" end
    local equipment
    pcall(function() equipment = template.Equipment end)
    if equipment == nil or equipment.Visuals == nil then return "skipped" end
    local minted = definition.minted[choice]
    if minted == nil then return "skipped" end
    local existing
    pcall(function() existing = equipment.Visuals[minted] end)
    if existing ~= nil and not overwrite then return "present" end
    local source = effectiveVisuals(equipment, definition.sourceEquipRace, definition.fallbackEquipRace)
    if source == nil then return "skipped" end
    local array, changed = buildArray(registration, choice, source)
    local ok = pcall(function() equipment.Visuals[minted] = array end)
    if not ok then return "skipped" end
    return changed and "refit" or "injected"
end

function M.RunBlanketPass(familyId, choice, force)
    familyId, choice = tostring(familyId or ""), tostring(choice or "")
    local revision = EquipRace.GetMappingRevision()
    local stale = passDone[familyId] ~= nil and passDone[familyId][choice]
        and passRevision[familyId] ~= nil and passRevision[familyId][choice] ~= revision
    if passDone[familyId] ~= nil and passDone[familyId][choice] and not force and not stale then
        return true, false
    end
    local profile = Registry.ResolveProfile(familyId, choice)
    if profile == nil or owner(familyId) == nil then
        Warn("RunBlanketPass: provider/profile unavailable for " .. familyId .. "/" .. choice)
        return false
    end
    local all
    local ok = pcall(function() all = Ext.Template.GetAllRootTemplates() end)
    if not ok or all == nil then return false end
    local total, refit, copied, skipped = 0, 0, 0, 0
    for _, template in pairs(all) do
        local isItem = false
        pcall(function() isItem = template.TemplateType == "item" end)
        if isItem then
            total = total + 1
            local result = injectTemplate(familyId, choice, template, force or stale)
            if result == "refit" then refit = refit + 1
            elseif result == "injected" then copied = copied + 1
            elseif result == "skipped" then skipped = skipped + 1 end
        end
    end
    passDone[familyId] = passDone[familyId] or {}
    passRevision[familyId] = passRevision[familyId] or {}
    passDone[familyId][choice] = true
    passRevision[familyId][choice] = EquipRace.GetMappingRevision()
    Log(("BlanketPass(%s/%s): total=%d refit=%d copied=%d skipped=%d")
        :format(familyId, choice, total, refit, copied, skipped))
    return true, true
end

local function injectEquipped(familyId, choice, itemGuid)
    local template
    pcall(function()
        local entity = Ext.Entity.Get(itemGuid)
        if entity ~= nil and entity.ServerItem ~= nil then template = entity.ServerItem.Template end
    end)
    return injectTemplate(familyId, choice, template, false)
end

local function sweepEquipped(familyId, choice, char)
    for _, slot in ipairs(VISUAL_SLOTS) do
        local item
        pcall(function() item = Osi.GetEquippedItem(char, slot) end)
        if item ~= nil and item ~= "" then injectEquipped(familyId, choice, item) end
    end
end

function M.RefreshEquipment(char)
    local items = {}
    for _, slot in ipairs(VISUAL_SLOTS) do
        pcall(function()
            local item = Osi.GetEquippedItem(char, slot)
            if item ~= nil and item ~= "" then items[#items + 1] = item end
        end)
    end
    for _, item in ipairs(items) do pcall(function() Osi.Unequip(char, item) end) end
    local function equipAgain()
        if not PassThrough.CanMutate("BodyFamilyEquipRace.DelayedRefresh", char) then return end
        for _, item in ipairs(items) do pcall(function() Osi.Equip(char, item) end) end
    end
    if #items > 0 then
        local timerOk = pcall(function() Ext.Timer.WaitFor(250, equipAgain) end)
        if not timerOk then equipAgain() end
    end
end

local function readFamily(char)
    local race, bodyType, bodyShape
    pcall(function()
        local entity = Ext.Entity.Get(char)
        local stats = entity and entity.CharacterCreationStats or nil
        if stats ~= nil then
            race = tostring(stats.Race)
            bodyType = tostring(stats.BodyType)
            bodyShape = tostring(stats.BodyShape)
        end
    end)
    return Registry.ResolveOfficialFamily(race, bodyType, bodyShape)
end

-- SetClothed writes only after the exact family tuple, provider profile, refit
-- registration, and blanket pass all succeed.
function M.SetClothed(char, choice, record)
    if char == nil or record == nil then return false end
    local familyId = readFamily(char)
    if familyId == nil or owner(familyId) == nil then return false end
    local profile = Registry.ResolveProfile(familyId, choice)
    if profile == nil then return false end
    local template = getTemplate(char)
    if template == nil then return false end
    local current = M.ReadEquipRace(char)
    if record.FamilyOrigEquipRace == nil and not Registry.IsMintedEquipmentRace(current) then
        record.FamilyOrigEquipRace = current
    end
    if record.FamilyOrigEquipRace == nil then
        record.FamilyOrigEquipRace = Registry.SafeSourceEquipmentRace()
        Warn("SetClothed: recovered missing original to canonical ordinary Tiefling EquipmentRace")
    end
    if not M.RunBlanketPass(familyId, choice, false) then return false end
    sweepEquipped(familyId, choice, char)
    local ok = pcall(function() template.EquipmentRace = profile.equipmentRace end)
    if not ok then return false end
    record.BodyFamilyId = familyId
    record.FamilyClothedChoice = choice
    M.RefreshEquipment(char)
    return true
end

function M.Restore(char, record)
    if char == nil or record == nil then return false end
    local template = getTemplate(char)
    if template == nil then return false end
    local target = record.FamilyOrigEquipRace or Registry.SafeSourceEquipmentRace()
    local ok = pcall(function() template.EquipmentRace = target end)
    if not ok then return false end
    record.FamilyClothedChoice = nil
    record.BodyFamilyId = nil
    M.RefreshEquipment(char)
    return true
end

function M.RecoverUnavailable(char, record, requestedChoice, restoreBody)
    if char == nil or record == nil then return false end
    local preferred = tostring(requestedChoice or record.Choice or record.FamilyClothedChoice or "")
    if preferred == "" then preferred = nil end
    local bodyOk = true
    if type(restoreBody) == "function" then
        bodyOk = pcall(restoreBody)
    end
    local clothedOk = M.Restore(char, record)
    record.Choice = "vanilla"
    record.AppliedCcsv = nil
    record.DesiredCcsv = nil
    record.Reverted = true
    record.UnavailableFamilyChoice = preferred
    if not bodyOk then Warn("RecoverUnavailable: base-body cleanup callback failed") end
    return bodyOk and clothedOk
end

function M.ReapplyAll(bodies, reason)
    local count = 0
    for char, record in pairs(bodies or {}) do
        if record.BodyFamilyId ~= nil and record.FamilyClothedChoice ~= nil then
            if M.SetClothed(char, record.FamilyClothedChoice, record) then count = count + 1 end
        end
    end
    if count > 0 then Log("ReapplyAll(" .. tostring(reason) .. "): " .. tostring(count)) end
    return count
end

function M.OnEquipped(item, char, record)
    if record == nil or record.BodyFamilyId == nil or record.FamilyClothedChoice == nil then return end
    local ok, rebuilt = M.RunBlanketPass(record.BodyFamilyId, record.FamilyClothedChoice, false)
    local result = injectEquipped(record.BodyFamilyId, record.FamilyClothedChoice, item)
    if ok and rebuilt then
        M.RefreshEquipment(char)
    elseif result == "refit" or result == "injected" then
        pcall(function() Osi.Unequip(char, item) end)
        local function equipAgain() pcall(function() Osi.Equip(char, item) end) end
        local timerOk = pcall(function() Ext.Timer.WaitFor(250, equipAgain) end)
        if not timerOk then equipAgain() end
    end
end

return M
