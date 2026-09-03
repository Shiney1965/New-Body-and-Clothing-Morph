local function loadModule(name)
    if Ext ~= nil and Ext.Require ~= nil then return Ext.Require(name .. ".lua") end
    return require(name)
end

local Schema = loadModule("StateSchema7")
local Master = loadModule("MasterState")
local Ledger = loadModule("OwnershipLedger")
local ProviderRegistry = loadModule("ProviderRegistry")
local RuntimeRollback = loadModule("RuntimeRollback")

local M = {}

function M.Install(modTable, state, deps)
    modTable = type(modTable) == "table" and modTable or {}
    deps = type(deps) == "table" and deps or {}
    local migrated, initialSchemaFailure = Schema.Migrate(state, deps.schema)

    local runtime
    local providerRegistry
    local runtimeDeps = {
        persist = deps.persist,
        applyManaged = deps.applyManaged,
        captureBaseline = deps.captureBaseline,
        verifyManaged = deps.verifyManaged,
        isCharacterAvailable = deps.isCharacterAvailable,
        beforeEnable = function()
            return providerRegistry:ActivateQueued()
        end,
        readVisuals = deps.readVisuals,
        writeVisuals = deps.writeVisuals,
        restoreExternal = function(charGuid, record, capability)
            if deps.restoreExternal ~= nil then
                return deps.restoreExternal(charGuid, record, capability)
            end
            local ledgerDeps = {}
            for key, value in pairs(deps) do ledgerDeps[key] = value end
            ledgerDeps.writeGate = function(mode, guid, fn)
                return runtime:WriteGate(mode, guid, fn)
            end
            local result = Ledger.RestoreExternal(charGuid, record, ledgerDeps, {
                capability = capability,
                makeExternal = capability == "external_restore",
            })
            if result and result.status=="clean" and deps.afterRestore then
                local called,ok=pcall(deps.afterRestore,charGuid,record)
                if not called or ok~=true then
                    record.RestoreState="partial"
                    record.RestoreFailures={"shared-cv-conflict-fallback-failed"}
                    return {status="partial",failureCodes=record.RestoreFailures}
                end
            end
            return result
        end,
    }
    runtime = Master.New(migrated or state, runtimeDeps)
    runtime.schemaFailure = initialSchemaFailure
    providerRegistry = ProviderRegistry.New(runtime.state, {
        persist = deps.persist,
        activate = deps.activateProvider,
        resourceExists = deps.providerResourceExists,
        existingTarget = deps.providerExistingTarget,
        isModuleLoaded = deps.isModuleLoaded,
        validateLegacyFamily = deps.validateLegacyFamily,
    }, {
        runtimeUuid = modTable.ModuleUUID,
        packageVersion64 = "36451011631513600",
        runtimeCodeVersion = "v4.22-s7-foundation",
    })
    runtime.ProviderRegistry = providerRegistry
    local runtimeRollback = RuntimeRollback.New(runtime, runtime.state, runtimeDeps)
    runtime.RuntimeRollback = runtimeRollback

    function runtime:RefreshState()
        if deps.getState ~= nil then
            local current = deps.getState()
            if type(current) == "table" then
                if type(current.RollbackPrepared) == "table"
                    and current.RollbackPrepared.status == "PREPARED" then
                    self.state = current
                    self.schemaFailure = "ROLLBACK_PREPARED_CHECKPOINT_REQUIRED"
                    providerRegistry:SetState(self.state)
                    runtimeRollback:SetState(self.state)
                    return self.state
                end
                local refreshed, failure = Schema.Migrate(current, deps.schema)
                self.state = refreshed or current
                self.schemaFailure = failure
                providerRegistry:SetState(self.state)
                runtimeRollback:SetState(self.state)
            end
        end
        return self.state
    end

    local rawWriteGate = runtime.WriteGate
    runtime.WriteGate = function(self, ...)
        self:RefreshState()
        if self.schemaFailure ~= nil then return false, self.schemaFailure end
        if providerRegistry:MutationBlocked() then return false,"PROVIDER_PROFILE_RESTART_REQUIRED" end
        return rawWriteGate(self, ...)
    end
    local rawFilterManagedBodies = runtime.FilterManagedBodies
    runtime.FilterManagedBodies = function(self, ...)
        self:RefreshState()
        if self.schemaFailure ~= nil then return {} end
        if providerRegistry:MutationBlocked() then return {} end
        return rawFilterManagedBodies(self, ...)
    end
    local rawRunExplicitManaged = runtime.RunExplicitManaged
    runtime.RunExplicitManaged = function(self, ...)
        self:RefreshState()
        if self.schemaFailure ~= nil then return false, self.schemaFailure end
        if providerRegistry:MutationBlocked() then return false,"PROVIDER_PROFILE_RESTART_REQUIRED" end
        return rawRunExplicitManaged(self, ...)
    end
    local rawGetDiagnostics = runtime.GetDiagnostics
    runtime.GetDiagnostics = function(self, ...)
        self:RefreshState()
        if self.schemaFailure then
            local blocked={}
            if type(self.state.Bodies)=="table" then for guid in pairs(self.state.Bodies) do blocked[#blocked+1]=tostring(guid) end end
            table.sort(blocked)
            return {PersistentSchema=self.state.Version,MasterEnabled=self.state.MasterEnabled,
                MutationGateClosed=self.state.MutationGateClosed,MasterState=self.state.MasterState,
                PassThroughRestoreComplete=false,CleanupState=self.state.CleanupState,
                SchemaFailure=self.schemaFailure,ManagedGuids={},ExternalGuids=blocked,
                PendingGuids={},PartialGuids={},BlockedGuids=blocked}
        end
        local diagnostics=rawGetDiagnostics(self, ...)
        diagnostics.ProviderRegistryRestartRequired=providerRegistry.restartRequired==true
        if providerRegistry:MutationBlocked() then
            diagnostics.ManagedGuids={};diagnostics.ExternalGuids={}
            for guid in pairs(self.state.Bodies or {}) do diagnostics.ExternalGuids[#diagnostics.ExternalGuids+1]=guid end
            table.sort(diagnostics.ExternalGuids)
        end
        return diagnostics
    end

    modTable.PersistentSchema = 7
    modTable.PackageVersion64 = "36451011631513600"
    modTable.PackageSemver = "1.3.1.0"
    modTable.ScriptExtenderRequiredVersion = 20
    modTable.PassThroughApiVersion = 1
    modTable.ExternalRefitApiVersion = 1
    modTable.BodyFamilyApiVersion = 1
    modTable.ProviderRegistrySnapshotApiVersion = 1
    modTable.CleanupApiVersion = 0
    modTable.RuntimeCodeVersion = "v4.22-s7-foundation"
    modTable.SetMasterEnabled = function(enabled, source)
        if type(enabled) ~= "boolean" then
            return false, {ok=false,status="INVALID_MASTER_VALUE"}
        end
        runtime:RefreshState()
        if runtime.schemaFailure ~= nil then
            return false, { ok = false, status = "REJECTED_INVALID_SCHEMA", failureCode = runtime.schemaFailure }
        end
        if providerRegistry:MutationBlocked() then return false,{ok=false,status="PROVIDER_PROFILE_RESTART_REQUIRED",restartRequired=true} end
        local result = runtime:SetMasterEnabled(enabled)
        if enabled == true and result.ok == true and runtime.state.MutationGateClosed == false
            and result.providerActivationResults == nil then
            result.providerActivationResults = providerRegistry:ActivateQueued()
        end
        return result.ok == true, result
    end
    modTable.SetExternal = function(charGuid)
        runtime:RefreshState()
        if runtime.schemaFailure ~= nil then
            return { ok = false, status = "REJECTED_INVALID_SCHEMA", failureCode = runtime.schemaFailure }
        end
        if providerRegistry:MutationBlocked() then return {ok=false,status="PROVIDER_PROFILE_RESTART_REQUIRED",restartRequired=true} end
        return runtime:SetExternal(charGuid)
    end
    modTable.GetStateDiagnostics = function()
        local diagnostics = runtime:GetDiagnostics()
        diagnostics.PackageVersion64 = modTable.PackageVersion64
        diagnostics.PackageSemver = modTable.PackageSemver
        diagnostics.RuntimeCodeVersion = modTable.RuntimeCodeVersion
        diagnostics.PersistentSchema = runtime.state.Version
        diagnostics.ScriptExtenderRequiredVersion = modTable.ScriptExtenderRequiredVersion
        diagnostics.PassThroughApiVersion = modTable.PassThroughApiVersion
        diagnostics.ExternalRefitApiVersion = modTable.ExternalRefitApiVersion
        diagnostics.BodyFamilyApiVersion = modTable.BodyFamilyApiVersion
        diagnostics.ProviderRegistrySnapshotApiVersion = modTable.ProviderRegistrySnapshotApiVersion
        diagnostics.CleanupApiVersion = modTable.CleanupApiVersion
        return diagnostics
    end
    modTable.GetProviderRegistrySnapshot = function()
        runtime:RefreshState()
        return providerRegistry:GetSnapshot()
    end
    modTable.PrepareRuntimeRollbackV1 = function(targetArtifactId, mode)
        runtime:RefreshState()
        if runtime.schemaFailure ~= nil then
            return { ok = false, status = "REJECTED_INVALID_SCHEMA",
                failureCodes = { runtime.schemaFailure }, olderPackageReady = false }
        end
        return runtimeRollback:Prepare(targetArtifactId, mode)
    end

    function runtime:CanManagedWrite(entryPoint, charGuid)
        local current = self:RefreshState()
        if self.schemaFailure ~= nil then return false, self.schemaFailure end
        if providerRegistry:MutationBlocked() then return false,"PROVIDER_PROFILE_RESTART_REQUIRED" end
        return Master.CheckWriteGate(current, "managed", charGuid)
    end

    return runtime
end

return M
