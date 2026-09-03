local SOURCE_NAME = "SindaeImportedOutfitsRecluseWave2TEST"
local MAPS = Ext.Require("RefitMaps.lua").SINDAE_RECLUSE_REFIT_BY_VR
local REQUIRED = {
    { name = "Body and Clothing Morph Runtime", uuid = "20aca985-e3e9-41d7-bf8f-10f2a3c413e4" },
    { name = "Sindae Imported Outfits", uuid = "096665c7-75aa-4747-9548-6ccafba985c8" },
    { name = "Sindae Texture Pak v1.16", uuid = "873d1b73-6adf-4f0c-9e8f-51a78fc3d9c5" },
}
local function Log(message) Ext.Utils.Print("[ClothMorphSindaeImportedOutfitsRecluseWave2Test] " .. tostring(message)) end
local function Warn(message) Ext.Utils.PrintWarning("[ClothMorphSindaeImportedOutfitsRecluseWave2Test] " .. tostring(message)) end
local function IsLoaded(uuid)
    local ok, loaded = pcall(function() return Ext.Mod.IsModLoaded(uuid) end)
    return ok and loaded == true
end
Ext.Events.SessionLoaded:Subscribe(function()
    for _, dependency in ipairs(REQUIRED) do
        if not IsLoaded(dependency.uuid) then
            Warn(dependency.name .. " is absent; registering zero Recluse Wave 2 routes.")
            return
        end
    end
    local runtime = Mods and Mods.ClothMorphRuntime
    if runtime == nil or type(runtime.RegisterExternalRefits) ~= "function" then
        Warn("compatible Runtime API is absent; registering zero Recluse Wave 2 routes.")
        return
    end
    local ok, result = pcall(function()
        return runtime.RegisterExternalRefits(SOURCE_NAME, MAPS, {
            sourceModUuid = "096665c7-75aa-4747-9548-6ccafba985c8",
            sourceModVersion = "36028797018963968",
            credit = "Sindae Imported Outfits assets by Sindae; isolated compatibility TEST with credit.",
        })
    end)
    if not ok or result ~= true then
        Warn("Runtime rejected Recluse Wave 2 registration; source items remain unchanged.")
        return
    end
    Log("registered 4 exact Recluse Wave 2 refit routes with Runtime")
end)
