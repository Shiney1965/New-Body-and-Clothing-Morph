local SOURCE = "ClothMorphTieflingBT1Test"
local PROVIDER_UUID = "b57bab2c-5679-5445-8fee-ca8c282990a5"
local BCB_UUID = "1d24059d-ff23-4a79-8892-57c85d512416"
local FAMILY = "tif_f_bt1"

local BODY = {
    vanilla = {
        ccsv = "f7315508-9afd-522a-867b-96213cc6443e",
        visual = "bfec2869-70cf-51a7-9806-1bbf02ff1bbe",
        equipmentRace = "0f09bfaa-52b2-5ad5-a489-545cdd1a6ce7",
    },
    sbbf = {
        ccsv = "294df7c6-c8d7-529d-9bcc-4122c0182cf3",
        visual = "ed2d8876-26c8-5844-827f-def771068f63",
        equipmentRace = "c4ab884e-1184-5bd7-b67e-ee3a28a883fd",
    },
    bcb = {
        ccsv = "eca05d33-9887-5d5e-868a-8be722c2eb12",
        visual = "eab8e30e-0207-58d8-8764-e3b4477133fa",
        equipmentRace = "e1371ee6-3c97-544b-b644-e3033021d187",
        requiredModUuid = BCB_UUID,
    },
}

local REFITS = {
    vanilla = {
        ["956e11cc-41da-9e43-036b-c59a70c1b945"] = "6cc531d9-a288-50ba-a891-c1917e7d818a",
        ["f29af014-91cb-f1a8-3b6f-d59de4ae8e91"] = "7dfb06bf-e196-575d-b96c-0b39a92a57e8",
    },
    sbbf = {
        ["956e11cc-41da-9e43-036b-c59a70c1b945"] = "d40c4b38-6ccb-52ef-a86b-73da0951f27a",
        ["f29af014-91cb-f1a8-3b6f-d59de4ae8e91"] = "c2e59b63-4efd-5645-8bf1-113488f9fec2",
    },
    bcb = {
        ["956e11cc-41da-9e43-036b-c59a70c1b945"] = "88774d3f-4436-51e9-8f9f-c64cb3a45cd9",
        ["f29af014-91cb-f1a8-3b6f-d59de4ae8e91"] = "c86d4c8d-0dfa-5c12-bc8c-9d4fdef816e2",
    },
}

local registrationComplete = false

local function register()
    if registrationComplete then return true end
    local runtime = Mods.ClothMorphRuntime
    if runtime == nil
       or tonumber(runtime.BodyFamilyApiVersion) ~= 1
       or type(runtime.RegisterBodyFamily) ~= "function"
       or type(runtime.RegisterFamilyRefits) ~= "function" then
        Ext.Utils.PrintWarning("[ClothMorphTieflingBT1Test] paired Runtime body-family API v1 is unavailable; provider disabled")
        return false
    end
    local ok = runtime.RegisterBodyFamily(SOURCE, {
        moduleUuid = PROVIDER_UUID,
        familyId = FAMILY,
        sourceEquipRace = "cf421f4e-107b-4ae6-86aa-090419c624a5",
        bodyType = 1,
        bodyShape = 0,
        profiles = BODY,
    })
    if not ok then return false end
    ok = runtime.RegisterFamilyRefits(SOURCE, FAMILY, REFITS, {
        proofItem = "90a79e46-e327-41f4-a349-8e4dd70b1892",
        proofTemplate = "ARM_Leather_1",
        routing = "exact-source-vr-replacement-only",
    })
    if ok then
        registrationComplete = true
        Ext.Utils.Print("[ClothMorphTieflingBT1Test] ordinary female Tiefling test provider registered")
        if type(runtime.ReapplyBodyFamilies) == "function" then
            pcall(function() runtime.ReapplyBodyFamilies(SOURCE .. "-register") end)
        end
    end
    return ok
end

Ext.Events.SessionLoaded:Subscribe(register)
pcall(function()
    Ext.Osiris.RegisterListener("LevelGameplayStarted", 0, "after", function()
        if not registrationComplete then register() end
    end)
end)



