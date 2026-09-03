-- A known unresolved design boundary, not an acceptance waiver.
local script=debug.getinfo(1,'S').source:sub(2):gsub('\\','/')
local F=dofile(script:match('^(.*)/[^/]+$')..'/production_engine.lua')
local root=assert(arg[1],'explicit Runtime stage required')
local failed,count=0,0
for _,moduleName in ipairs({'EquipRace.lua','BodyFamilyEquipRace.lua'}) do
    for _,switch in ipairs({'external','master-off'}) do
        count=count+1
        local ok,why=pcall(function()
            local w=F.Boot(root,{simulateInventory=true})
            w.equipped={[F.ids.a]={Breast='external-body-item'}}
            w.modules[moduleName].RefreshEquipment(F.ids.a)
            assert(w.equipped[F.ids.a].Breast==nil,'fixture did not model the actual unequip window')
            if switch=='external' then assert(w.mod.SetDesiredBody(F.ids.a,'external'),'External refused')
            else assert(w.mod.SetMasterEnabled(false,'fixture'),'master off refused') end
            w.resetSpies();w.flushTimers()
            assert(#w.writes==0,'gated delayed callback wrote equipment')
            assert(w.equipped[F.ids.a].Breast=='external-body-item',
                'PENDING_REFRESH_ITEM_STATE_UNRESOLVED: gated re-equip left the owned unequip unresolved')
        end)
        if ok then print('PASS '..moduleName..' '..switch)
        else failed=failed+1;print('FAIL '..moduleName..' '..switch..' '..tostring(why)) end
    end
end
print(('R1_PENDING_REFRESH_RESULT %d/%d'):format(count-failed,count))

-- Live 2s notify is not hit by the 4 inventory cases: fixture MonotonicTime is
-- constant (10000). Extra coverage advances a captured clock; not a rewrite of
-- production_engine. This is not part of the 4/4 inventory gate.
local extraFailed = 0
local extraOk, extraWhy = pcall(function()
    local clock = 8000
    local w = F.Boot(root, {simulateInventory=true})
    w.env.Ext.Utils.MonotonicTime = function() return clock end
    w.equipped = {[F.ids.a]={Breast='external-body-item'}}
    w.modules['EquipRace.lua'].RefreshEquipment(F.ids.a)
    clock = 10000
    assert(w.mod.SetDesiredBody(F.ids.a,'external'), 'External refused')
    local seen = false
    for _, line in ipairs(w.logs) do
        if tostring(line):find('Please Wait for Body Morph', 1, true) then seen = true end
    end
    for _, payload in ipairs(w.broadcasts) do
        if type(payload)=='table' and (payload.cmd=='cm_wait' or tostring(payload.message or ''):find('Please Wait for Body Morph', 1, true)) then
            seen = true
        end
    end
    assert(seen, '2s wait notice was not shown')
    assert(w.equipped[F.ids.a].Breast=='external-body-item', '2s wait path left item unequipped')
end)
if extraOk then print('PASS pending-refresh 2s wait notice')
else extraFailed = 1; print('FAIL pending-refresh 2s wait notice '..tostring(extraWhy)) end
print(('R1_PENDING_REFRESH_WAIT_NOTIFY %s'):format(extraFailed==0 and 'PASS' or 'FAIL'))

if failed>0 or extraFailed>0 then os.exit(1) end
