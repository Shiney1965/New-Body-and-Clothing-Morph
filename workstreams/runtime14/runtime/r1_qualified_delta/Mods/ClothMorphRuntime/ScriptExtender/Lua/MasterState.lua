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
    local record = charGuid ~= nil and state.Bodies and state.Bodies[charGuid] or nil
    if record and record.ProviderTransition ~= nil then return false,"provider-transition-pending" end
    if record and hasFailureCode(record,"CCSV_PROPAGATION_FAILED")
        and capability~="external_restore" and capability~="ordinary_restore"
        and capability~="maintenance_restore" then return false,"ccsv-propagation-pending" end
    if capability == "external_restore" and state.MasterEnabled == false then
        return state.MutationGateClosed == true, "explicit-off-restore"
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
    if charGuid~=nil and record==nil then return false,"character-untracked" end
    if record ~= nil and (record.Transition ~= nil or record.RestoreState ~= "clean") then
        return false, "character-restore-pending"
    end
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
    if status ~= "clean" and status ~= "partial" and status ~= "blocked" and status ~= "pending" then
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
            Direction="disable",Started=true,PendingCharacters={},
            CleanGuids = {}, PartialGuids = {}, BlockedGuids = {},
        }
        for guid,record in pairs(self.state.Bodies) do
            if record.Choice~="external" or record.RestoreState~="clean" or record.Transition~=nil then
                self.state.MasterTransition.PendingCharacters[guid]=true
            end
        end
        persist(self, "master-off-gated")

        local clean, partial, blocked, pending = {}, {}, {}, {}
        for _, guid in ipairs(sortedGuids(self.state.Bodies)) do
            local record = self.state.Bodies[guid]
            if record.Choice=="external" and record.RestoreState=="clean" and record.Transition==nil then
                clean[#clean+1]=guid
                goto continue_disable
            end
            record.Transition={Direction="to_external",Phase="gated",PreserveChoice=true}
            record.RestoreState="pending"
            persist(self,"master-character-gated")
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
            if status == "clean" then record.Transition=nil end
            if status == "clean" then clean[#clean + 1] = guid
            elseif status == "partial" then partial[#partial + 1] = guid
            elseif status == "pending" then pending[#pending+1]=guid
            else blocked[#blocked + 1] = guid end
            ::continue_disable::
        end

        self.state.PassThroughRestoreComplete = recomputeComplete(self.state)
        if self.state.PassThroughRestoreComplete then
            self.state.MasterState = "off_restored"
            self.state.MasterTransition = nil
        elseif #partial > 0 or #clean > 0 then
            self.state.MasterState = "off_partial"
            local unfinished={}
            for guid,record in pairs(self.state.Bodies) do if record.RestoreState~="clean" then unfinished[guid]=true end end
            self.state.MasterTransition = {
                schema = 1, Kind = "master_off", Phase = "complete",
                Direction="disable",Started=true,PendingCharacters=unfinished,
                CleanGuids = clean, PartialGuids = partial, BlockedGuids = blocked,
            }
        else
            self.state.MasterState = "off_blocked"
            local unfinished={}
            for guid,record in pairs(self.state.Bodies) do if record.RestoreState~="clean" then unfinished[guid]=true end end
            self.state.MasterTransition = {
                schema = 1, Kind = "master_off", Phase = "complete",
                Direction="disable",Started=true,PendingCharacters=unfinished,
                CleanGuids = clean, PartialGuids = partial, BlockedGuids = blocked,
            }
        end
        persist(self, "master-off-complete")
        return {
            ok = true, status = "COMPLETE", masterState = self.state.MasterState,
            cleanGuids = clean, partialGuids = partial, blockedGuids = blocked,
            pendingGuids = pending,
        }
    end

    self:ResumePending()
    self.state.MasterEnabled = true
    self.state.MutationGateClosed = true
    self.state.MasterState = "enabling"
    self.state.PassThroughRestoreComplete = false
    self.state.MasterTransition = { schema = 1, Kind = "master_on", Phase = "applying",
        Direction="enable",Started=true,PendingCharacters={},RequestedChoices={} }
    for guid,record in pairs(self.state.Bodies) do
        if record.Choice~="external" then
            self.state.MasterTransition.PendingCharacters[guid]=true
            self.state.MasterTransition.RequestedChoices[guid]=record.Choice
        end
    end
    persist(self, "master-on-gated")
    local providerResults=self.deps.beforeEnable and self.deps.beforeEnable() or {}
    local managed, external, pending = {}, {}, {}
    for _, guid in ipairs(sortedGuids(self.state.Bodies)) do
        local record = self.state.Bodies[guid]
        if record.Choice == "external" then
            external[#external + 1] = guid
        else
            local choice = MANAGED_CHOICES[record.PreferredChoice] and record.PreferredChoice
                or (MANAGED_CHOICES[record.Choice] and record.Choice or nil)
            if self.deps.isCharacterAvailable and self.deps.isCharacterAvailable(guid)~=true then
                record.RestoreState="pending"
                record.Transition={Direction="to_managed",Phase="gated",RequestedChoice=choice,Deferred=true}
                pending[#pending+1]=guid
                persist(self,"master-enable-deferred")
                goto continue_enable
            end
            local okApply = false
            if choice ~= nil then
                local accepted = self:RunExplicitManaged(guid,choice,function()
                    if self.deps.applyManaged == nil then return false end
                    return self.deps.applyManaged(guid, record, choice) == true
                end,"ordinary_reenable")
                okApply = accepted == true
            end
            if okApply then
                record.Choice, record.PreferredChoice = choice, choice
                record.RestoreState, record.RestoreFailures = "clean", {}
                managed[#managed + 1] = guid
            else
                record.Choice = "external"
                -- RunExplicitManaged already classified restoration and bound
                -- any failed rollback to its retained claim/journal. A master
                -- summary must not erase that blocking evidence or downgrade a
                -- blocked/pending record to a generic partial result.
                if choice==nil then record.RestoreState="blocked" end
                record.RestoreFailures=record.RestoreFailures or {}
                local code=choice==nil and "PREFERRED_CHOICE_INVALID" or "MANAGED_REAPPLY_FAILED"
                if not hasFailureCode(record,code) then record.RestoreFailures[#record.RestoreFailures+1]=code end
                external[#external + 1] = guid
            end
            self.state.MasterTransition.PendingCharacters[guid]=nil
        end
        ::continue_enable::
    end
    self.state.MasterState = "enabled"
    self.state.MutationGateClosed = false
    self.state.MasterTransition = nil
    persist(self, "master-on-complete")
    return {
        ok = true, status = "COMPLETE", masterState = "enabled",
        managedGuids = managed, externalGuids = external, pendingGuids=pending,
        providerActivationResults=providerResults,
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
    record.Transition = {Direction="to_external",Phase="gated"}
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
    if record.RestoreState == "clean" then record.Transition=nil end
    persist(self, "external-complete")
    result.ok = record.RestoreState == "clean"
    return result
end

function Runtime:RunExplicitManaged(charGuid, choice, fn, internalCapability, internalVerifier)
    if not MANAGED_CHOICES[choice] then return false, "invalid-choice" end
    local capability=internalCapability or "explicit_managed"
    local allowed, why = M.CheckWriteGate(self.state, capability, charGuid)
    if not allowed then return false, why end
    local record = self.state.Bodies[charGuid] or {
        Choice="external",PreferredChoice=choice,OriginalVisuals={},OwnedCcsvs={},
        RemovedOriginalVisuals={},HistoricalOriginals={},RestoreFailures={},RestoreState="clean"}
    self.state.Bodies[charGuid] = record
    local priorCleanExternal=record.Choice=="external" and record.RestoreState=="clean" and record.Transition==nil
    local priorTransition=deepCopy(record.Transition)
    local wasManaged = MANAGED_CHOICES[record.Choice] == true and M.CheckWriteGate(self.state,"managed",charGuid)==true
    record.PreferredChoice = choice
    record.Choice = "external"
    record.Transition={Direction="to_managed",RequestedChoice=choice,Phase="gated"}
    if internalCapability=="ordinary_reenable" then record.Transition.PreserveChoice=true end
    record.RestoreState, record.RestoreFailures = "pending", {}
    persist(self, "explicit-managed-gated")
    local captured, failure = false,"baseline-capture-unavailable"
    if self.deps.captureBaseline then
        local called,value,why=pcall(self.deps.captureBaseline,charGuid,record,wasManaged)
        captured=called and value==true
        failure=called and why or "baseline-capture-failed"
    end
    if not captured then
        record.RestoreState=priorCleanExternal and "clean" or "blocked"
        record.RestoreFailures={failure or "managed-preflight-failed"}
        record.Transition=priorCleanExternal and nil or priorTransition
        persist(self,"explicit-managed-preflight-blocked")
        return false,failure
    end
    record.Transition.Phase="captured";persist(self,"explicit-managed-captured")
    record.Transition.Phase="applying";persist(self,"explicit-managed-applying")
    local called, result = pcall(fn)
    local ok = called and result == true and not hasFailureCode(record,"CCSV_PROPAGATION_FAILED")
    record.Transition.Phase="verifying";persist(self,"explicit-managed-verifying")
    local verifier=internalVerifier or self.deps.verifyManaged
    if ok and verifier then
        local checked,valid=pcall(verifier,charGuid,record,choice)
        ok=checked and valid==true
    end
    if ok then
        record.Choice,record.PreferredChoice=choice,choice
        record.RestoreState = "clean"
        record.Transition=nil
    else
        record.Choice="external"
        record.Transition={Direction="to_external",Phase="restoring"}
        persist(self,"explicit-managed-rollback-gated")
        local restoreCapability=self.state.MasterState=="enabling" and "maintenance_restore" or "external_restore"
        local restored=self.deps.restoreExternal and self.deps.restoreExternal(charGuid,record,restoreCapability)
        local status=classifyRestore(record,restored)
        record.RestoreFailures[#record.RestoreFailures+1]="managed-apply-failed"
        if status=="clean" then record.Transition=nil else record.RestoreFailures[#record.RestoreFailures+1]=MANAGED_ROLLBACK_FAILURE end
        persist(self,"explicit-managed-rollback-complete")
        return false,"managed-apply-failed"
    end
    persist(self, "explicit-managed-complete")
    return true, "applied"
end

function Runtime:ResumePending()
    if self.schemaFailure or self.state.CleanupState~="idle" then return false end
    local master=self.state.MasterTransition
    local resumeEnable=self.state.MasterState=="enabling" and type(master)=="table"
    local resumeDisable=self.state.MasterEnabled==false and type(master)=="table"
        and (master.Direction=="disable" or master.Kind=="master_off")
    if resumeEnable or resumeDisable then
        for _,guid in ipairs(sortedGuids(self.state.Bodies)) do
            local rec=self.state.Bodies[guid]
            if master.PendingCharacters and master.PendingCharacters[guid] and rec.Transition==nil then
                local choice=master.RequestedChoices and master.RequestedChoices[guid] or rec.Choice
                rec.Transition=resumeEnable
                    and {Direction="to_managed",Phase="gated",RequestedChoice=choice,Deferred=true,PreserveChoice=true}
                    or {Direction="to_external",Phase="gated",PreserveChoice=true}
                rec.RestoreState="pending"
            end
        end
        persist(self,"master-resume-gated")
    end
    local hasPending=false
    for _,guid in ipairs(sortedGuids(self.state.Bodies)) do
        local rec=self.state.Bodies[guid]
        if rec.ProviderTransition==nil and (rec.Transition~=nil or rec.RestoreState=="pending") then
            hasPending=true
            local deferred=rec.Transition and (rec.Transition.Deferred or (resumeEnable and rec.Transition.PreserveChoice))
                and rec.Transition.RequestedChoice
            if rec.Transition and rec.Transition.Direction=="to_managed" and not deferred then rec.Choice="external" end
            local preserve=rec.Transition and rec.Transition.PreserveChoice
            local choice=rec.Choice
            rec.Transition={Direction="to_external",Phase="restoring",PreserveChoice=preserve}
            persist(self,"resume-restore-gated")
            local result=self.deps.restoreExternal and self.deps.restoreExternal(guid,rec,"maintenance_restore")
            local status=classifyRestore(rec,result)
            if preserve then rec.Choice=choice end
            if status=="clean" then
                rec.Transition=nil
                if deferred and self.state.MasterEnabled==true and not resumeEnable then
                    self:RunExplicitManaged(guid,deferred,function()
                        return self.deps.applyManaged and self.deps.applyManaged(guid,rec,deferred)==true
                    end)
                end
            elseif deferred then
                rec.Transition={Direction="to_managed",Phase="gated",RequestedChoice=deferred,Deferred=true}
            end
            persist(self,"resume-restore-result")
        end
    end
    if self.state.MasterEnabled==false and hasPending then
        self.state.PassThroughRestoreComplete=recomputeComplete(self.state)
        self.state.MasterState=self.state.PassThroughRestoreComplete and "off_restored" or "off_partial"
        if self.state.PassThroughRestoreComplete then self.state.MasterTransition=nil end
        persist(self,"resume-master-summary")
    end
    if resumeEnable then
        if self.deps.beforeEnable then self.deps.beforeEnable() end
        for _,guid in ipairs(sortedGuids(master.PendingCharacters or {})) do
            local rec=self.state.Bodies[guid]
            local choice=master.RequestedChoices and master.RequestedChoices[guid]
                or (rec and rec.PreferredChoice)
            if rec and MANAGED_CHOICES[choice] then
                if self.deps.isCharacterAvailable and not self.deps.isCharacterAvailable(guid) then
                    rec.RestoreState="pending"
                    rec.Transition={Direction="to_managed",Phase="gated",RequestedChoice=choice,Deferred=true,PreserveChoice=true}
                elseif rec.RestoreState=="clean" then
                    self:RunExplicitManaged(guid,choice,function()
                        return self.deps.applyManaged and self.deps.applyManaged(guid,rec,choice)==true
                    end,"ordinary_reenable")
                end
            end
        end
        self.state.MasterState="enabled";self.state.MutationGateClosed=false;self.state.MasterTransition=nil
        persist(self,"master-resume-complete")
    end
    return true
end

function Runtime:GetDiagnostics()
    local external, partial, blocked, managed, pending = {}, {}, {}, {}, {}
    for _, guid in ipairs(sortedGuids(self.state.Bodies)) do
        local record = self.state.Bodies[guid]
        if M.CheckWriteGate(self.state,"managed",guid) then managed[#managed+1]=guid
        else external[#external+1]=guid end
        if record.RestoreState=="pending" then pending[#pending+1]=guid end
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
        ManagedGuids = managed,
        PendingGuids = pending,
        PartialGuids = partial,
        BlockedGuids = blocked,
    }
end

function M.New(state, deps)
    return setmetatable({ state = state, deps = type(deps) == "table" and deps or {} }, Runtime)
end

return M
