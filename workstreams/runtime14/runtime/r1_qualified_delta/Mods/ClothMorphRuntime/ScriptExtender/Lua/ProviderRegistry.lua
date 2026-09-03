local M = {}
local Registry = {}
Registry.__index = Registry

local CHOICES = { "vanilla", "sbbf", "bcb" }

local function copy(value, seen)
    if type(value) ~= "table" then return value end
    seen = seen or {}
    if seen[value] ~= nil then return seen[value] end
    local out = {}
    seen[value] = out
    for key, item in pairs(value) do out[copy(key, seen)] = copy(item, seen) end
    return out
end

local function sorted(values)
    local out = {}
    for _, value in ipairs(type(values) == "table" and values or {}) do
        out[#out + 1] = tostring(value)
    end
    table.sort(out)
    return out
end

local function mapKeys(value)
    local out = {}
    for key in pairs(type(value) == "table" and value or {}) do out[#out + 1] = key end
    table.sort(out, function(a, b) return tostring(a) < tostring(b) end)
    return out
end

local function jsonString(value)
    local escaped = tostring(value):gsub('[%z\1-\31\\"]', function(char)
        local replacements = { ['"'] = '\\"', ['\\'] = '\\\\', ['\b'] = '\\b',
            ['\f'] = '\\f', ['\n'] = '\\n', ['\r'] = '\\r', ['\t'] = '\\t' }
        return replacements[char] or string.format("\\u%04x", string.byte(char))
    end)
    return '"' .. escaped .. '"'
end

local function isArray(value)
    local count, highest = 0, 0
    for key in pairs(value) do
        if type(key) ~= "number" or key < 1 or key % 1 ~= 0 then return false end
        count, highest = count + 1, math.max(highest, key)
    end
    return count > 0 and highest == count
end

local function canonicalJson(value)
    local kind = type(value)
    if kind == "nil" then return "null" end
    if kind == "boolean" then return value and "true" or "false" end
    if kind == "number" then
        if value ~= value or value == math.huge or value == -math.huge then error("non-finite number") end
        return string.format("%.17g", value)
    end
    if kind == "string" then return jsonString(value) end
    if kind ~= "table" then error("unsupported canonical value") end
    local parts = {}
    if isArray(value) then
        for index = 1, #value do parts[index] = canonicalJson(value[index]) end
        return "[" .. table.concat(parts, ",") .. "]"
    end
    for _, key in ipairs(mapKeys(value)) do
        parts[#parts + 1] = jsonString(key) .. ":" .. canonicalJson(value[key])
    end
    return "{" .. table.concat(parts, ",") .. "}"
end

local SHA256_K = {
    0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
    0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
    0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
    0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
    0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
    0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
    0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
    0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2,
}

local function ror(value, amount)
    return ((value >> amount) | (value << (32 - amount))) & 0xffffffff
end

local function sha256(message)
    local bytes = { string.byte(message, 1, #message) }
    local bitLength = #bytes * 8
    bytes[#bytes + 1] = 0x80
    while (#bytes % 64) ~= 56 do bytes[#bytes + 1] = 0 end
    local high, low = math.floor(bitLength / 0x100000000), bitLength % 0x100000000
    for shift = 24, 0, -8 do bytes[#bytes + 1] = (high >> shift) & 0xff end
    for shift = 24, 0, -8 do bytes[#bytes + 1] = (low >> shift) & 0xff end
    local h = { 0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,
        0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19 }
    for offset = 1, #bytes, 64 do
        local w = {}
        for index = 0, 15 do
            local pos = offset + index * 4
            w[index] = ((bytes[pos] << 24) | (bytes[pos+1] << 16)
                | (bytes[pos+2] << 8) | bytes[pos+3]) & 0xffffffff
        end
        for index = 16, 63 do
            local x, y = w[index-15], w[index-2]
            local s0 = ror(x,7) ~ ror(x,18) ~ (x >> 3)
            local s1 = ror(y,17) ~ ror(y,19) ~ (y >> 10)
            w[index] = (w[index-16] + s0 + w[index-7] + s1) & 0xffffffff
        end
        local a,b,c,d,e,f,g,hh = h[1],h[2],h[3],h[4],h[5],h[6],h[7],h[8]
        for index = 0, 63 do
            local s1 = ror(e,6) ~ ror(e,11) ~ ror(e,25)
            local ch = (e & f) ~ ((~e) & g)
            local t1 = (hh + s1 + ch + SHA256_K[index+1] + w[index]) & 0xffffffff
            local s0 = ror(a,2) ~ ror(a,13) ~ ror(a,22)
            local maj = (a & b) ~ (a & c) ~ (b & c)
            local t2 = (s0 + maj) & 0xffffffff
            hh,g,f,e,d,c,b,a = g,f,e,(d+t1)&0xffffffff,c,b,a,(t1+t2)&0xffffffff
        end
        h[1]=(h[1]+a)&0xffffffff; h[2]=(h[2]+b)&0xffffffff
        h[3]=(h[3]+c)&0xffffffff; h[4]=(h[4]+d)&0xffffffff
        h[5]=(h[5]+e)&0xffffffff; h[6]=(h[6]+f)&0xffffffff
        h[7]=(h[7]+g)&0xffffffff; h[8]=(h[8]+hh)&0xffffffff
    end
    local out = {}
    for index, value in ipairs(h) do out[index] = string.format("%08X", value) end
    return table.concat(out)
end

local function validUuid(value)
    return tostring(value or ""):lower():match(
        "^[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]%-"
        .. "[0-9a-f][0-9a-f][0-9a-f][0-9a-f]%-[0-9a-f][0-9a-f][0-9a-f][0-9a-f]%-"
        .. "[0-9a-f][0-9a-f][0-9a-f][0-9a-f]%-[0-9a-f][0-9a-f][0-9a-f][0-9a-f]"
        .. "[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]$") ~= nil
end

local function result(descriptor, status, ok, failures)
    return {
        ok = ok == true, status = status,
        providerId = descriptor and descriptor.providerId or nil,
        ownerModuleUuid = descriptor and descriptor.ownerModuleUuid or nil,
        canonicalDigest = descriptor and descriptor.canonicalDigest or nil,
        activationState = descriptor and descriptor.activationState or "rejected",
        failureCodes = failures or {}, restartRequired = descriptor ~= nil and descriptor.restartRequired == true or false,
    }
end

local function normalizeMaps(maps, allowEmpty)
    if type(maps) ~= "table" then return nil, "MAPS_INVALID" end
    local normalized, sourceSet, targets = {}, {}, {}
    for _, choice in ipairs(CHOICES) do normalized[choice], targets[choice] = {}, {} end
    local count = 0
    for choice, values in pairs(maps) do
        if normalized[tostring(choice)] == nil or type(values) ~= "table" then
            return nil, "CHOICE_INVALID"
        end
        for source, target in pairs(values) do
            local sourceKey = tostring(source or ""):lower()
            local targetKey = tostring(target or "")
            if sourceKey == "" then return nil, "SOURCE_INVALID" end
            if targetKey == "" then return nil, "TARGET_INVALID" end
            normalized[choice][sourceKey] = targetKey
            sourceSet[sourceKey] = true
            targets[choice][#targets[choice] + 1] = targetKey
            count = count + 1
        end
    end
    if count == 0 and not allowEmpty then return nil, "MAPS_EMPTY" end
    local sources = mapKeys(sourceSet)
    for _, choice in ipairs(CHOICES) do table.sort(targets[choice]) end
    return normalized, nil, sources, targets
end

local function normalizeUuidArray(values)
    local out = {}
    for _, value in ipairs(type(values) == "table" and values or {}) do
        if not validUuid(value) then return nil end
        out[#out + 1] = tostring(value):lower()
    end
    table.sort(out)
    return out
end

local function hasDuplicateBodyCcsv(values)
    local seen = {}
    for _, value in ipairs(values) do
        local key = tostring(value):lower()
        if seen[key] then return true end
        seen[key] = true
    end
    return false
end

function Registry:SetState(state)
    if self.state==state then return end
    self.state = state
    if type(self.state.RollbackPrepared) == "table"
        and self.state.RollbackPrepared.status == "PREPARED" then
        return
    end
    -- State validation belongs to Schema7. Diagnostics and registry binding
    -- must never repair malformed persistence into a subsequently writable save.
    if type(state.ProviderDescriptors)=="table" and state.CleanupState=="idle"
        and next(self.processDescriptors)~=nil then self:AttachProcessDescriptors() end
end

function Registry:MutationBlocked()
    return self.restartRequired==true or self.attaching==true
end

function Registry:AttachProcessDescriptors()
    if self.attaching or self.restartRequired then return false end
    self.attaching=true
    local candidates=copy(self.state.ProviderDescriptors)
    local failure
    for id,descriptor in pairs(self.processDescriptors) do
        local saved=candidates[id]
        if saved and (saved.ownerModuleUuid~=descriptor.ownerModuleUuid or saved.canonicalDigest~=descriptor.canonicalDigest) then
            failure=descriptor;break
        end
        if not saved then candidates[id]=copy(descriptor) end
    end
    if not failure then
        for _,id in ipairs(mapKeys(self.processDescriptors)) do
            local descriptor=self.processDescriptors[id]
            local called,valid=pcall(self._preflight,self,descriptor,candidates)
            if not called or not valid then failure=descriptor;break end
        end
    end
    if failure then
        self.restartRequired=true
        self:_failure(copy(failure),"PROVIDER_PROFILE_RESTART_REQUIRED")
        self.attaching=false
        return false
    end
    self.state.ProviderDescriptors=candidates
    self.sequence=self.sequence+1
    self.attaching=false
    return true
end

function Registry:_buildExternal(sourceName, maps, info)
    info = type(info) == "table" and info or {}
    sourceName = tostring(sourceName or "")
    if sourceName == "" then return nil, "SOURCE_NAME_INVALID" end
    local providerId = tostring(info.providerId or ("legacy.external." .. sourceName:lower():gsub("[^%w]+", ".")))
    if providerId == "" then return nil, "PROVIDER_ID_INVALID" end
    local explicitOwner = info.ownerModuleUuid
    local owner = explicitOwner or ""
    if explicitOwner ~= nil and not validUuid(owner) then return nil, "OWNER_INVALID" end
    local normalized, failure, sources, targets = normalizeMaps(maps)
    if normalized == nil then return nil, failure end
    local required = normalizeUuidArray(info.requiredModuleUuids)
    local forbidden = normalizeUuidArray(info.forbiddenModuleUuids)
    if required == nil or forbidden == nil then return nil, "MODULE_UUID_INVALID" end
    if explicitOwner then
        local ownerKey=tostring(explicitOwner):lower()
        local found=false;for _,uuid in ipairs(required) do if uuid==ownerKey then found=true end end
        if not found then required[#required+1]=ownerKey;table.sort(required) end
    end
    if info.sourceModUuid~=nil then
        if not validUuid(info.sourceModUuid) then return nil,"SOURCE_MODULE_UUID_INVALID" end
        local source=info.sourceModUuid:lower()
        local found=false;for _,uuid in ipairs(required) do if uuid==source then found=true end end
        if not found then required[#required+1]=source;table.sort(required) end
    end
    local bodyCcsvs = sorted(info.bodyCcsvs)
    if explicitOwner==nil and #bodyCcsvs>0 then return nil,"BODY_CCSV_OWNER_UNRESOLVED" end
    if hasDuplicateBodyCcsv(bodyCcsvs) then return nil, "BODY_CCSV_DUPLICATE" end
    local canonicalInfo=copy(info)
    canonicalInfo.canonicalDigest=nil
    local payload = {
        kind = "external_refits", providerId = providerId, familyId = "", sourceName=sourceName,
        apiGeneration = "legacy_v1", ownerModuleUuid = tostring(owner):lower(),
        ownerUnresolved = explicitOwner == nil, requiredModuleUuids = required,
        sourceModUuid=info.sourceModUuid,sourceModVersion=info.sourceModVersion or info.sourceVersion,
        credit=info.credit,info=canonicalInfo,
        forbiddenModuleUuids = forbidden, maps = normalized,
        sourceKeys = sources, targetKeysByChoice = targets,
        revealingKeys = sorted(info.revealingKeys), exclusions = sorted(info.exclusions),
        bodyCcsvs = bodyCcsvs, bodyVisualResources = sorted(info.bodyVisualResources),
        mintedEquipmentRaces = sorted(info.mintedEquipmentRaces),
        resourceManifestDigest = tostring(info.resourceManifestDigest or ""), restartRequired = false,
    }
    local digest = sha256(canonicalJson(payload))
    if info.canonicalDigest ~= nil and tostring(info.canonicalDigest):upper() ~= digest then
        return nil, "DIGEST_MISMATCH"
    end
    local descriptor = copy(payload)
    descriptor.canonicalPayload = copy(payload)
    descriptor.canonicalDigest = digest
    descriptor.activationState = "pending"
    return descriptor
end

function Registry:_failure(descriptor, code)
    descriptor = descriptor or { activationState = "rejected" }
    descriptor.restartRequired=self.restartRequired==true
    descriptor.activationState = "rejected"
    self.sequence = self.sequence + 1
    self.rejected[#self.rejected + 1] = {
        providerId = descriptor.providerId, ownerModuleUuid = descriptor.ownerModuleUuid,
        ownerUnresolved=descriptor.ownerUnresolved==true,
        canonicalDigest = descriptor.canonicalDigest, status = code,
        activationState = "rejected", failureCodes = { code }, restartRequired = descriptor.restartRequired,
    }
    return result(descriptor, code, false, { code })
end

function Registry:_preflight(descriptor, descriptorPool)
    descriptorPool=descriptorPool or self.state.ProviderDescriptors
    if sha256(canonicalJson(descriptor.canonicalPayload)) ~= descriptor.canonicalDigest then
        return false, "DIGEST_DRIFT"
    end
    if descriptor.kind=="body_family" and self.deps.validateLegacyFamily then
        local valid,why=self.deps.validateLegacyFamily(descriptor.canonicalPayload.spec,true)
        if not valid then return false,why or "BODY_PROFILE_INVALID" end
    end
    if descriptor.kind=="family_refits" then
        local body=descriptorPool["legacy.body."..descriptor.familyId]
        if not body or body.activationState~="active"
            or body.ownerModuleUuid~=descriptor.ownerModuleUuid
            or self.activated[body.providerId]~=body.canonicalDigest then return false,"BODY_PROVIDER_NOT_ACTIVE" end
    end
    for _, uuid in ipairs(descriptor.requiredModuleUuids) do
        if self.deps.isModuleLoaded ~= nil and not self.deps.isModuleLoaded(uuid) then
            return false, "REQUIRED_MODULE_UNAVAILABLE"
        end
    end
    for _, uuid in ipairs(descriptor.forbiddenModuleUuids) do
        if self.deps.isModuleLoaded ~= nil and self.deps.isModuleLoaded(uuid) then
            return false, "FORBIDDEN_MODULE_PRESENT"
        end
    end
    for _, bodyCcsv in ipairs(descriptor.bodyCcsvs) do
        local wanted = tostring(bodyCcsv):lower()
        for providerId, existing in pairs(descriptorPool) do
            if providerId ~= descriptor.providerId
                and (existing.activationState == "active" or existing.activationState == "queued") then
                for _, owned in ipairs(existing.bodyCcsvs or {}) do
                    if tostring(owned):lower() == wanted then
                        return false, "BODY_CCSV_OWNER_COLLISION"
                    end
                end
            end
        end
    end
    for _, choice in ipairs(CHOICES) do
        for source, target in pairs(descriptor.canonicalPayload.maps[choice]) do
            if self.deps.resourceExists ~= nil and not self.deps.resourceExists(target) then
                return false, "TARGET_UNAVAILABLE"
            end
            if descriptor.kind=="external_refits" and self.deps.existingTarget ~= nil then
                local existing = self.deps.existingTarget(choice, source)
                if existing ~= nil and tostring(existing):lower() ~= tostring(target):lower() then
                    return false, "SOURCE_COLLISION"
                end
            end
        end
    end
    return true
end

function Registry:_activate(descriptor)
    local ok, failure = self:_preflight(descriptor)
    if not ok then return self:_failure(descriptor, failure) end
    local called, accepted = pcall(self.deps.activate, copy(descriptor))
    if not called or accepted ~= true then return self:_failure(descriptor, "DELEGATE_REJECTED") end
    descriptor.activationState = "active"
    self.state.ProviderDescriptors[descriptor.providerId] = copy(descriptor)
    self.activated[descriptor.providerId]=descriptor.canonicalDigest
    self.processDescriptors[descriptor.providerId]=copy(descriptor)
    self.sequence = self.sequence + 1
    if self.deps.persist ~= nil then self.deps.persist(self.state, "provider-active") end
    return result(descriptor, "ACTIVE", true)
end

function Registry:RegisterExternalRefits(sourceName, maps, info)
    if type(self.state.RollbackPrepared) == "table"
        and self.state.RollbackPrepared.status == "PREPARED" then
        return result(nil, "REJECTED_ROLLBACK_PREPARED", false, {
            "ROLLBACK_PREPARED_CHECKPOINT_REQUIRED",
        })
    end
    local descriptor, failure = self:_buildExternal(sourceName, maps, info)
    if descriptor == nil then return self:_failure(nil, failure) end
    return self:_submit(descriptor)
end

function Registry:_submit(descriptor)
    if self.restartRequired then return self:_failure(descriptor,"PROVIDER_PROFILE_RESTART_REQUIRED") end
    if self.state.Version~=7 or type(self.state.ProviderDescriptors)~="table" then
        return self:_failure(descriptor,"REJECTED_INVALID_SCHEMA")
    end
    if self.state.RollbackPrepared~=nil then return self:_failure(descriptor,"REJECTED_ROLLBACK_PREPARED") end
    if self.state.CleanupState ~= "idle" then
        return self:_failure(descriptor, "REJECTED_CLEANUP_DISABLED")
    end
    local existing = self.state.ProviderDescriptors[descriptor.providerId]
    if existing ~= nil then
        if tostring(existing.ownerModuleUuid or ""):lower() == descriptor.ownerModuleUuid
            and tostring(existing.canonicalDigest or ""):upper() == descriptor.canonicalDigest then
            if existing.activationState=="active" and self.activated[descriptor.providerId]~=descriptor.canonicalDigest then
                if self.state.MutationGateClosed then
                    descriptor.activationState="queued"
                    self.state.ProviderDescriptors[descriptor.providerId]=copy(descriptor)
                    return result(descriptor,"QUEUED_MASTER_OFF",true)
                end
                return self:_activate(descriptor)
            end
            if existing.activationState == "active" or existing.activationState == "queued" then
                descriptor.activationState = existing.activationState
                return result(descriptor, "IDEMPOTENT", true)
            end
            if existing.activationState == "rejected" then
                self.state.ProviderDescriptors[descriptor.providerId] = nil
            else
                return self:_failure(descriptor, "PROVIDER_STATE_INVALID")
            end
        end
        if self.state.ProviderDescriptors[descriptor.providerId] ~= nil then
            return self:_failure(descriptor, "PROVIDER_COLLISION")
        end
    end
    if self.state.CleanupState ~= "idle" then
        return self:_failure(descriptor, "REJECTED_CLEANUP_DISABLED")
    end
    if self.state.MutationGateClosed == true then
        descriptor.activationState = "queued"
        self.state.ProviderDescriptors[descriptor.providerId] = copy(descriptor)
        self.sequence = self.sequence + 1
        if self.deps.persist ~= nil then self.deps.persist(self.state, "provider-queued") end
        return result(descriptor, "QUEUED_MASTER_OFF", true)
    end
    return self:_activate(descriptor)
end

local function jsonValue(value,seen)
    local kind=type(value)
    if kind=="nil" or kind=="boolean" or kind=="string" then return true end
    if kind=="number" then return value==value and value~=math.huge and value~=-math.huge end
    if kind~="table" then return false end
    seen=seen or {}
    if seen[value] then return false end
    seen[value]=true
    for key,item in pairs(value) do
        if (type(key)~="string" and (type(key)~="number" or key<1 or key%1~=0)) or not jsonValue(item,seen) then
            seen[value]=nil;return false
        end
    end
    seen[value]=nil;return true
end

function Registry:_legacy(kind,sourceName,familyId,maps,owner,extra)
    if type(sourceName)~="string" or sourceName=="" or (not validUuid(owner) and not (kind=="revealing" and owner=="")) or not jsonValue(extra) then
        return nil,"LEGACY_DESCRIPTOR_INVALID"
    end
    local normalized,failure,sources,targets=normalizeMaps(maps,true)
    if not normalized then return nil,failure end
    local id=kind=="body_family" and ("legacy.body."..familyId)
        or kind=="family_refits" and ("legacy.family_refits."..familyId)
        or ("legacy.revealing."..sha256(canonicalJson(extra.revealingKeys)))
    local payload={kind=kind,providerId=id,familyId=familyId,sourceName=sourceName,
        apiGeneration="legacy_v1",ownerModuleUuid=owner:lower(),ownerUnresolved=kind=="revealing",
        maps=normalized,requiredModuleUuids=kind=="revealing" and {} or {owner:lower()},
        forbiddenModuleUuids={},sourceKeys=sources,targetKeysByChoice=targets,revealingKeys={},
        exclusions={},bodyCcsvs={},bodyVisualResources={},mintedEquipmentRaces={},
        resourceManifestDigest="",restartRequired=false}
    for key,value in pairs(extra) do payload[key]=copy(value) end
    local descriptor=copy(payload)
    descriptor.canonicalPayload=copy(payload)
    descriptor.canonicalDigest=sha256(canonicalJson(payload))
    descriptor.activationState="pending"
    return descriptor
end

local function legacyResult(response)
    return response.ok==true,response.status,response
end

function Registry:RegisterBodyFamily(sourceName,spec)
    if self.state.CleanupState~="idle" then return legacyResult(self:_failure(nil,"REJECTED_CLEANUP_DISABLED")) end
    if type(spec)~="table" or not jsonValue(spec) or not self.deps.validateLegacyFamily then
        return legacyResult(self:_failure(nil,"BODY_SPEC_INVALID"))
    end
    local valid,why=self.deps.validateLegacyFamily(spec,false)
    if not valid then return legacyResult(self:_failure(nil,why or "BODY_SPEC_INVALID")) end
    local visuals,ccsvs,races={},{},{}
    for _,choice in ipairs(CHOICES) do
        local profile=spec.profiles[choice]
        visuals[#visuals+1]=profile.visual;ccsvs[#ccsvs+1]=profile.ccsv;races[#races+1]=profile.equipmentRace
    end
    local descriptor,failure=self:_legacy("body_family",sourceName,spec.familyId,
        {vanilla={},sbbf={},bcb={}},spec.moduleUuid,
        {spec=spec,bodyVisualResources=visuals,bodyCcsvs=ccsvs,mintedEquipmentRaces=races})
    if not descriptor then return legacyResult(self:_failure(nil,failure)) end
    return legacyResult(self:_submit(descriptor))
end

function Registry:RegisterFamilyRefits(sourceName,familyId,maps,info)
    if self.state.CleanupState~="idle" then return legacyResult(self:_failure(nil,"REJECTED_CLEANUP_DISABLED")) end
    local body=type(self.state.ProviderDescriptors)=="table" and self.state.ProviderDescriptors["legacy.body."..tostring(familyId)]
    if not body or body.canonicalPayload.sourceName~=sourceName
        or (body.activationState~="queued" and body.activationState~="active") then
        return legacyResult(self:_failure(nil,"BODY_PROVIDER_OWNER_MISMATCH"))
    end
    if type(maps)~="table" then return legacyResult(self:_failure(nil,"MAPS_INVALID")) end
    for _,choice in ipairs(CHOICES) do if type(maps[choice])~="table" then return legacyResult(self:_failure(nil,"CHOICE_INVALID")) end end
    local descriptor,failure=self:_legacy("family_refits",sourceName,familyId,maps,body.ownerModuleUuid,{info=info or {}})
    if not descriptor then return legacyResult(self:_failure(nil,failure)) end
    return legacyResult(self:_submit(descriptor))
end

function Registry:RegisterRevealing(ids)
    if self.state.CleanupState~="idle" then return legacyResult(self:_failure(nil,"REJECTED_CLEANUP_DISABLED")) end
    if type(ids)~="table" or not jsonValue(ids) or #ids==0 then return legacyResult(self:_failure(nil,"REVEALING_IDS_INVALID")) end
    local count=0
    for key,value in pairs(ids) do
        if type(key)~="number" or key<1 or key%1~=0 or key>#ids or not validUuid(value) then
            return legacyResult(self:_failure(nil,"REVEALING_IDS_INVALID"))
        end
        count=count+1
    end
    if count~=#ids then return legacyResult(self:_failure(nil,"REVEALING_IDS_INVALID")) end
    local descriptor,failure=self:_legacy("revealing","legacy.revealing","",{vanilla={},sbbf={},bcb={}},
        "",{revealingKeys=sorted(ids)})
    if not descriptor then return legacyResult(self:_failure(nil,failure)) end
    return legacyResult(self:_submit(descriptor))
end

function Registry:IsFamilyReady(familyId)
    local descriptors=self.state.ProviderDescriptors
    if type(descriptors)~="table" then return false end
    local body,refits=descriptors["legacy.body."..familyId],descriptors["legacy.family_refits."..familyId]
    return body~=nil and refits~=nil and body.activationState=="active" and refits.activationState=="active"
        and body.ownerModuleUuid==refits.ownerModuleUuid
        and self.activated[body.providerId]==body.canonicalDigest
        and self.activated[refits.providerId]==refits.canonicalDigest
end

function Registry:ActivateQueued()
    local results = {}
    for _, providerId in ipairs(mapKeys(self.state.ProviderDescriptors)) do
        local descriptor = self.state.ProviderDescriptors[providerId]
        if descriptor.activationState == "queued" then
            results[#results + 1] = self:_activate(descriptor)
        end
    end
    return results
end

local function snapshotDescriptor(descriptor)
    local out = {}
    for _, field in ipairs({
        "kind", "providerId", "familyId", "apiGeneration", "ownerModuleUuid", "ownerUnresolved",
        "canonicalDigest", "activationState", "requiredModuleUuids",
        "forbiddenModuleUuids", "sourceKeys", "targetKeysByChoice",
        "revealingKeys", "exclusions", "bodyCcsvs", "bodyVisualResources",
        "mintedEquipmentRaces", "resourceManifestDigest", "restartRequired",
    }) do out[field] = copy(descriptor[field]) end
    return out
end

function Registry:GetSnapshot()
    local descriptors = {}
    for _, providerId in ipairs(mapKeys(self.state.ProviderDescriptors)) do
        local descriptor=snapshotDescriptor(self.state.ProviderDescriptors[providerId])
        if self.restartRequired and self.activated[providerId]~=descriptor.canonicalDigest then
            descriptor.activationState="rejected";descriptor.restartRequired=true
        end
        descriptors[#descriptors+1]=descriptor
    end
    if self.restartRequired then
        for _,id in ipairs(mapKeys(self.processDescriptors)) do
            local descriptor=self.processDescriptors[id]
            local saved=self.state.ProviderDescriptors[id]
            if not saved or saved.canonicalDigest~=descriptor.canonicalDigest or saved.ownerModuleUuid~=descriptor.ownerModuleUuid then
                local active=snapshotDescriptor(descriptor);active.restartRequired=true
                descriptors[#descriptors+1]=active
            end
        end
    end
    return copy({
        apiVersion = 1, snapshotSequence = self.sequence,
        PackageVersion64 = self.meta.packageVersion64,
        RuntimeCodeVersion = self.meta.runtimeCodeVersion,
        PersistentSchema = self.state.Version,
        mutationGateClosed = self.state.MutationGateClosed,
        cleanupState = self.state.CleanupState,
        restartRequired = self.restartRequired==true,
        descriptors = descriptors,
        rejectedAttempts = self.rejected,
    })
end

function Registry:ClaimForCcsv(ccsv, cvGuid, resourceKind)
    local wanted = tostring(ccsv or ""):lower()
    local currentCv = tostring(cvGuid or "")
    if wanted == "" or currentCv == "" then return nil, "OWNERSHIP_BINDING_INVALID" end
    local match
    for _, providerId in ipairs(mapKeys(self.state.ProviderDescriptors)) do
        local descriptor = self.state.ProviderDescriptors[providerId]
        if descriptor.activationState == "active" then
            for _, value in ipairs(descriptor.bodyCcsvs or {}) do
                if tostring(value):lower() == wanted then
                    if match ~= nil then return nil, "CCSV_OWNER_COLLISION" end
                    match = descriptor
                end
            end
        end
    end
    if match == nil then return nil, "CCSV_OWNER_NOT_REGISTERED" end
    if match.ownerUnresolved==true or not validUuid(match.ownerModuleUuid) then return nil,"CCSV_OWNER_UNRESOLVED" end
    return {
        ProviderId = match.providerId,
        OwnerModuleUuid = match.ownerModuleUuid,
        ProviderDigest = match.canonicalDigest,
        ResourceKind = resourceKind or "body_ccsv",
        AddedForCvGuid = currentCv,
    }, "ok"
end

function M.New(state, deps, meta)
    local registry = setmetatable({ deps = deps or {}, meta = meta or {}, rejected = {}, sequence = 0,
        activated={},processDescriptors={},restartRequired=false,attaching=false }, Registry)
    registry:SetState(state)
    return registry
end

M.CanonicalJson = canonicalJson
M.Sha256 = sha256
return M
