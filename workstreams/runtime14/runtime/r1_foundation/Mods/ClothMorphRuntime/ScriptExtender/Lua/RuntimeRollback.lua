local M = {}
local RuntimeRollback = {}
RuntimeRollback.__index = RuntimeRollback

local function copy(value, seen)
    if type(value) ~= "table" then return value end
    seen = seen or {}
    if seen[value] ~= nil then return seen[value] end
    local out = {}
    seen[value] = out
    for key, item in pairs(value) do out[copy(key, seen)] = copy(item, seen) end
    return out
end

local function replaceTable(target, source)
    for key in pairs(target) do target[key] = nil end
    for key, value in pairs(source) do target[copy(key)] = copy(value) end
end

local function loadModule(name)
    if Ext ~= nil and Ext.Require ~= nil then return Ext.Require(name .. ".lua") end
    return require(name)
end

local ProviderRegistry = loadModule("ProviderRegistry")

local function projectRecord(record)
    local projected = copy(type(record) == "table" and record or {})
    projected.Reverted = false
    projected.PreferredChoice = nil
    projected.OwnedCcsvs = nil
    projected.ProviderTransition = nil
    projected.HistoricalOriginals = nil
    projected.ActiveProvider = nil
    projected.Transition = nil
    return projected
end

function RuntimeRollback:SetState(state)
    self.state = state
end

function RuntimeRollback:ProjectSchema6(targetArtifactId, mode)
    local projection = copy(type(self.state) == "table" and self.state or {})
    projection.Version = 6
    projection.ProviderDescriptors = nil
    projection.Bodies = type(projection.Bodies) == "table" and projection.Bodies or {}
    for charGuid, record in pairs(projection.Bodies) do
        projection.Bodies[charGuid] = projectRecord(record)
    end
    projection.RollbackPrepared = {
        schema = 1,
        status = "PREPARED",
        targetArtifactId = targetArtifactId,
        mode = mode,
        engineSaveCheckpointRequired = true,
    }

    local evidenceDigest = ProviderRegistry.Sha256(ProviderRegistry.CanonicalJson({
        targetArtifactId = targetArtifactId,
        mode = mode,
        projectedState = projection,
    }))
    projection.RollbackPrepared.evidenceDigest = evidenceDigest

    -- This replaces only PersistentVars-backed state. It intentionally performs
    -- no body, CCA, EquipmentRace, or visual-resource operation.
    replaceTable(self.state, projection)
    if self.runtime ~= nil then self.runtime.state = self.state end
    return {
        ok = true,
        status = "PREPARED",
        targetArtifactId = targetArtifactId,
        mode = mode,
        evidenceDigest = evidenceDigest,
        olderPackageReady = false,
        engineSaveCheckpointRequired = true,
    }
end

function RuntimeRollback:Prepare(targetArtifactId, mode)
    if targetArtifactId ~= "R0_CURRENT_BASELINE" then
        return { ok = false, status = "UNKNOWN_TARGET_ARTIFACT",
            failureCodes = { "UNKNOWN_TARGET_ARTIFACT" }, olderPackageReady = false }
    end
    if mode ~= "preserve_managed" then
        return { ok = false, status = "UNSUPPORTED_ROLLBACK_MODE",
            failureCodes = { "UNSUPPORTED_ROLLBACK_MODE" }, olderPackageReady = false }
    end
    return self:ProjectSchema6(targetArtifactId, mode)
end

function M.New(runtime, state, deps)
    return setmetatable({ runtime = runtime, state = state, deps = deps or {} }, RuntimeRollback)
end

return M
