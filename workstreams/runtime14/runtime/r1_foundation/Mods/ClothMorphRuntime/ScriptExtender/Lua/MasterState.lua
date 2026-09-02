local M = {}
local Runtime = {}
Runtime.__index = Runtime

local MANAGED_CHOICES = { vanilla = true, sbbf = true, bcb = true }
local MANAGED_ROLLBACK_FAILURE = "MANAGED_REAPPLY_ROLLBACK_FAILED"

local function hasFailureCode(record, expected)
    for _, code in ipairs(type(record) == "table" and record.RestoreFailures or {}) do
        if code == expected then return true end
    end
    return false
end

local function deepCopy(value, seen)
    if type(value) ~= "table" then return value end
    seen = seen or {}
    if seen[value] ~= nil then return seen[value] end
    local out = {}
    seen[value] = out
    for key, item in pairs(value) do out[deepCopy(key, seen)] = deepCopy(item, seen) end
    return out
end

local function restoreTable(target, snapshot)
    for key in pairs(target) do target[key] = nil end
    for key, value in pairs(snapshot) do target[deepCopy(key)] = deepCopy(value) end
end

local function visualArraysEqual(a, b)
    if type(a) ~= "table" or type(b) ~= "table" or #a ~= #b then return false end
    for index, value in ipairs(a) do
        if tostring(value):lower() ~= tostring(b[index]):lower() then return false end
    end
    return true
end

local function readVisuals(self, charGuid)
    if self.deps.readVisuals == nil then return nil, false end
    local called, visuals, readOk = pcall(self.deps.readVisuals, charGuid)
    if not called or readOk ~= true or type(visuals) ~= "table" then return nil, false end
    return deepCopy(visuals), true
end

local function rollbackVisuals(self, charGuid, priorVisuals, priorReadable)
    if not priorReadable then return false end
    local current, currentReadable = readVisuals(self, charGuid)
    if currentReadable and visualArraysEqual(current, priorVisuals) then return true end
    if self.deps.writeVisuals == nil then return false end
    local called, wrote = pcall(self.deps.writeVisuals, charGuid, deepCopy(priorVisuals))
    if not called or wrote ~= true then return false end
    local after, afterReadable = readVisuals(self, charGuid)
    return afterReadable and visualArraysEqual(after, priorVisuals)
end

local function sortedGuids(bodies)
    local out = {}
    for guid in pairs(type(bodies) == "table" and bodies or {}) do out[#out + 1] = guid end
    table.sort(out)
    return out
end

local function persist(self, reason)
    if self.deps.persist ~= nil then self.deps.persist(self.state, reason) end
end

function M.CheckWriteGate(state, capability, charGuid)
    if type(state) ~= "table" or state.Version ~= 7 then
        return false, "persistent-schema"
    end
    if state.CleanupState ~= "idle" then
        return false, "cleanup-state"
    end
    if capability == "ordinary_restore" then
        return state.MasterEnabled == false and state.MutationGateClosed == true
            and state.MasterState == "off_restoring", "ordinary-restore-state"
    end
    if capability == "ordinary_reenable" then
        return state.MasterEnabled == true and state.MutationGateClosed == true
            and state.MasterState == "enabling", "ordinary-reenable-state"
    end
    if capability == "maintenance_restore" then return true, "maintenance" end
    local globallyEnabled = state.MasterEnabled == true and state.MutationGateClosed == false
        and state.MasterState == "enabled" and state.MasterTransition == nil
    if not globallyEnabled then return false, "ordinary-gate-closed" end
    local record = charGuid ~= nil and state.Bodies and state.Bodies[charGuid] or nil
    if record ~= nil and record.ProviderTransition ~= nil
        and capability ~= "external_restore" and capability ~= "maintenance_restore" then
        return false, "provider-transition-pending"
    end
    if record ~= nil and hasFailureCode(record, MANAGED_ROLLBACK_FAILURE)
        and capability ~= "external_restore" then
        return false, "managed-rollback-blocked"
    end
    if capability == "explicit_managed" or capability == "external_restore" then
        return true, "explicit-capability"
    end
    if record ~= nil and record.Choice == "external" then return false, "character-external" end
    return true, "managed"
end

function Runtime:WriteGate(capability, charGuid, fn)
    local allowed, why = M.CheckWriteGate(self.state, capability, charGuid)
    if not allowed then return false, why end
    return true, fn()
end

function Runtime:ManagedWrite(entryPoint, charGuid, fn)
    local allowed, why = M.CheckWriteGate(self.state, "managed", charGuid)
    if not allowed then return false, why end
    local result = fn()
    return true, result
end

function Runtime:FilterManagedBodies()
    local out = {}
    for guid, record in pairs(self.state.Bodies or {}) do
        if M.CheckWriteGate(self.state, "managed", guid) then out[guid] = record end
    end
    return out
end

local function classifyRestore(record, result)
    local status = type(result) == "table" and result.status or record.RestoreState
    if status ~= "clean" and status ~= "partial" and status ~= "blocked" then
        status = "blocked"
        record.RestoreFailures = { "RESTORE_RESULT_INVALID" }
    end
    record.RestoreState = status
    record.RestoreFailures = type(record.RestoreFailures) == "table" and record.RestoreFailures or {}
    return status
end

local function recomputeComplete(state)
    if state.MasterEnabled ~= false then return false end
    for _, record in pairs(state.Bodies or {}) do
        if record.RestoreState ~= "clean" then return false end
    end
    return true
end

function Runtime:SetMasterEnabled(enabled)
    enabled = enabled == true
    if self.state.Version ~= 7 then
        return { ok = false, status = "REJECTED_UNSUPPORTED_SCHEMA" }
    end
    if self.state.CleanupState ~= "idle" then
        return { ok = false, status = "REJECTED_CLEANUP_STATE" }
    end
    if enabled and self.state.MasterEnabled == true and self.state.MasterState == "enabled"
        and self.state.MutationGateClosed == false then
        return { ok = true, status = "IDEMPOTENT", masterState = "enabled" }
    end
    if not enabled and self.state.MasterEnabled == false
        and (self.state.MasterState == "off_restored" or self.state.MasterState == "off_partial"
            or self.state.MasterState == "off_blocked") then
        return { ok = true, status = "IDEMPOTENT", masterState = self.state.MasterState }
    end

    if not enabled then
        self.state.MasterEnabled = false
        self.state.MutationGateClosed = true
        self.state.MasterState = "off_restoring"
        self.state.PassThroughRestoreComplete = false
        self.state.CleanupState = "idle"
        self.state.MasterTransition = {
            schema = 1, Kind = "master_off", Phase = "restoring",
            CleanGuids = {}, PartialGuids = {}, BlockedGuids = {},
        }
        persist(self, "master-off-gated")

        local clean, partial, blocked = {}, {}, {}
        for _, guid in ipairs(sortedGuids(self.state.Bodies)) do
            local record = self.state.Bodies[guid]
            local accepted, result = self:WriteGate("ordinary_restore", guid, function()
                if self.deps.restoreExternal == nil then
                    record.RestoreState = "blocked"
                    record.RestoreFailures = { "RESTORE_ADAPTER_UNAVAILABLE" }
                    return { status = "blocked", failureCodes = record.RestoreFailures }
                end
                return self.deps.restoreExternal(guid, record, "ordinary_restore")
            end)
            if not accepted then
                record.RestoreState = "blocked"
                record.RestoreFailures = { "WRITE_GATE_CLOSED" }
                result = { status = "blocked" }
            end
            local status = classifyRestore(record, result)
            if status == "clean" then clean[#clean + 1] = guid
            elseif status == "partial" then partial[#partial + 1] = guid
            else blocked[#blocked + 1] = guid end
        end

        self.state.PassThroughRestoreComplete = recomputeComplete(self.state)
        if self.state.PassThroughRestoreComplete then
            self.state.MasterState = "off_restored"
            self.state.MasterTransition = nil
        elseif #partial > 0 or #clean > 0 then
            self.state.MasterState = "off_partial"
            self.state.MasterTransition = {
                schema = 1, Kind = "master_off", Phase = "complete",
                CleanGuids = clean, PartialGuids = partial, BlockedGuids = blocked,
            }
        else
            self.state.MasterState = "off_blocked"
            self.state.MasterTransition = {
                schema = 1, Kind = "master_off", Phase = "complete",
                CleanGuids = clean, PartialGuids = partial, BlockedGuids = blocked,
            }
        end
        persist(self, "master-off-complete")
        return {
            ok = true, status = "COMPLETE", masterState = self.state.MasterState,
            cleanGuids = clean, partialGuids = partial, blockedGuids = blocked,
        }
    end

    self.state.MasterEnabled = true
    self.state.MutationGateClosed = true
    self.state.MasterState = "enabling"
    self.state.PassThroughRestoreComplete = false
    self.state.MasterTransition = { schema = 1, Kind = "master_on", Phase = "applying" }
    persist(self, "master-on-gated")
    local managed, external = {}, {}
    for _, guid in ipairs(sortedGuids(self.state.Bodies)) do
        local record = self.state.Bodies[guid]
        if record.Choice == "external" then
            external[#external + 1] = guid
        else
            local choice = MANAGED_CHOICES[record.PreferredChoice] and record.PreferredChoice
                or (MANAGED_CHOICES[record.Choice] and record.Choice or nil)
            local okApply = false
            if choice ~= nil then
                local accepted, result = self:WriteGate("ordinary_reenable", guid, function()
                    if self.deps.applyManaged == nil then return false end
                    return self.deps.applyManaged(guid, record, choice) == true
                end)
                okApply = accepted and result == true
            end
            if okApply then
                record.Choice, record.PreferredChoice = choice, choice
                record.RestoreState, record.RestoreFailures = "clean", {}
                managed[#managed + 1] = guid
            else
                record.Choice = "external"
                record.RestoreState = "partial"
                record.RestoreFailures = {
                    choice == nil and "PREFERRED_CHOICE_INVALID" or "MANAGED_REAPPLY_FAILED",
                }
                external[#external + 1] = guid
            end
        end
    end
    self.state.MasterState = "enabled"
    self.state.MutationGateClosed = false
    self.state.MasterTransition = nil
    persist(self, "master-on-complete")
    return {
        ok = true, status = "COMPLETE", masterState = "enabled",
        managedGuids = managed, externalGuids = external,
    }
end

function Runtime:SetExternal(charGuid)
    local record = self.state.Bodies and self.state.Bodies[charGuid] or nil
    if record == nil then return { ok = false, status = "CHARACTER_NOT_TRACKED" } end
    if record.Choice == "external" and record.RestoreState == "clean" then
        return { ok = true, status = "IDEMPOTENT" }
    end
    local allowed = M.CheckWriteGate(self.state, "external_restore", charGuid)
    if not allowed then return { ok = false, status = "WRITE_GATE_CLOSED" } end
    if MANAGED_CHOICES[record.Choice] then record.PreferredChoice = record.Choice end
    record.Choice = "external"
    record.RestoreState = "pending"
    record.RestoreFailures = {}
    persist(self, "external-gated")
    local accepted, result = self:WriteGate("external_restore", charGuid, function()
        if self.deps.restoreExternal == nil then
            return { status = "blocked", failureCodes = { "RESTORE_ADAPTER_UNAVAILABLE" } }
        end
        return self.deps.restoreExternal(charGuid, record, "external_restore")
    end)
    if not accepted then result = { status = "blocked", failureCodes = { "WRITE_GATE_CLOSED" } } end
    result = type(result) == "table" and result or { status = "blocked" }
    record.Choice = "external"
    classifyRestore(record, result)
    persist(self, "external-complete")
    result.ok = record.RestoreState == "clean"
    return result
end

function Runtime:RunExplicitManaged(charGuid, choice, fn)
    if not MANAGED_CHOICES[choice] then return false, "invalid-choice" end
    local allowed, why = M.CheckWriteGate(self.state, "explicit_managed", charGuid)
    if not allowed then return false, why end
    local record = self.state.Bodies[charGuid] or {}
    self.state.Bodies[charGuid] = record
    local prior = deepCopy(record)
    local priorVisuals, priorVisualsReadable = readVisuals(self, charGuid)
    record.Choice, record.PreferredChoice = choice, choice
    record.RestoreState, record.RestoreFailures = "pending", {}
    persist(self, "explicit-managed-gated")
    local called, result = pcall(fn)
    local ok = called and result == true
    if ok then
        record.RestoreState = "clean"
    else
        local rollbackOk = rollbackVisuals(
            self, charGuid, priorVisuals, priorVisualsReadable)
        restoreTable(record, prior)
        if not rollbackOk then
            record.RestoreState = "blocked"
            record.RestoreFailures = { MANAGED_ROLLBACK_FAILURE }
        end
        self.state.Bodies[charGuid] = record
        persist(self, rollbackOk and "explicit-managed-complete"
            or "explicit-managed-rollback-blocked")
        return false, rollbackOk and "prior-state-restored" or "rollback-failed"
    end
    persist(self, "explicit-managed-complete")
    return true, "applied"
end

function Runtime:GetDiagnostics()
    local external, partial, blocked = {}, {}, {}
    for _, guid in ipairs(sortedGuids(self.state.Bodies)) do
        local record = self.state.Bodies[guid]
        if record.Choice == "external" then external[#external + 1] = guid end
        if record.RestoreState == "partial" then partial[#partial + 1] = guid end
        if record.RestoreState == "blocked" then blocked[#blocked + 1] = guid end
    end
    return {
        PersistentSchema = self.state.Version,
        MasterEnabled = self.state.MasterEnabled,
        MutationGateClosed = self.state.MutationGateClosed,
        MasterState = self.state.MasterState,
        PassThroughRestoreComplete = self.state.PassThroughRestoreComplete,
        CleanupState = self.state.CleanupState,
        ExternalGuids = external,
        PartialGuids = partial,
        BlockedGuids = blocked,
    }
end

function M.New(state, deps)
    return setmetatable({ state = state, deps = type(deps) == "table" and deps or {} }, Runtime)
end

return M
