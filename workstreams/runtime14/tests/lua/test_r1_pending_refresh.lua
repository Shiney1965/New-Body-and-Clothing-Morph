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
if failed>0 then os.exit(1) end
