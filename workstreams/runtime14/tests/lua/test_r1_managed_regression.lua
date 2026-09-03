-- Real R0 body-key resolution and qualified control paths, synthetic engine
-- resource objects. This does not assert mesh geometry or gameplay acceptance.
local script=debug.getinfo(1,'S').source:sub(2):gsub('\\','/')
local F=dofile(script:match('^(.*)/[^/]+$')..'/production_engine.lua')
local root=assert(arg[1],'explicit Runtime stage required')
local races={'0eb594cb-8820-4be6-a58d-8be7a1a98fba','6c038dcb-7eb5-431d-84f8-cecfaf1c0c5a',
    '45f4ac10-3c89-4fb2-b37d-f973bb9110c0','4f5d1434-5175-4fa9-b7dc-ab24fba37929',
    'c5f8ebdd-f4a5-4d2d-9eab-4a8d1b1dd724','4d30b4f9-7bb2-4fc2-a7bc-080f116e325a',
    'e966f47f-998a-41df-ad86-d83b44299efb','bdf9b779-002c-4077-b377-8ea7c1faa795'}
local choices={'vanilla','sbbf','bcb'}
local failed,count=0,0
for _,race in ipairs(races) do for _,choice in ipairs(choices) do
    count=count+1
    local ok,why=pcall(function()
        local w=F.Boot(root)
        w.entities[F.ids.a].CharacterCreationStats.Race=race
        local expected={vanilla='3bc12bd9-6c5e-5067-a20f-b17e45647a10',sbbf=F.ids.sbbf,bcb=F.ids.bcb}
        if race=='bdf9b779-002c-4077-b377-8ea7c1faa795' then
            expected={vanilla='a4891ad7-53b0-5448-8d9c-9fabfdb067b6',
                sbbf='77777777-7777-4777-8777-777777777777',bcb='88888888-8888-4888-8888-888888888888'}
            w.statics['a8819ee1-8c30-5d9c-87e5-d6c1d1589b96']={VisualResource=expected.sbbf}
            w.statics['3d93f1a0-22bc-5938-951b-fe8b639be26b']={VisualResource=expected.bcb}
            for _,vr in pairs(expected) do w.resources[vr]={SourceFile='Generated/Public/ClothMorphRuntime/fixture-gith.GR2'} end
        end
        assert(w.mod.SetCharacterMode(F.ids.a,choice,'regression'),'managed request failed')
        assert(w.resources[F.ids.cv].VisualSet.BodySetVisual==expected[choice],'wrong body family target')
        assert(w.entities[F.ids.a].ServerCharacter.Template.EquipmentRace==w.modules['EquipRace.lua'].MINTED[choice],'wrong managed equipment race')
        assert(w.mod.SetCharacterMode(F.ids.a,'external','regression'),'External restore failed')
        assert(w.resources[F.ids.cv].VisualSet.BodySetVisual==F.ids.body,'original body lost')
        assert(w.entities[F.ids.a].ServerCharacter.Template.EquipmentRace==F.ids.er,'original equipment race lost')
        assert(w.mod.SetCharacterMode(F.ids.a,choice,'regression'),'managed resume failed')
    end)
    if ok then print('PASS '..race..' '..choice) else failed=failed+1;print('FAIL '..race..' '..choice..' '..tostring(why)) end
end end
print(('R1_MANAGED_REGRESSION_RESULT %d/%d'):format(count-failed,count))
if failed>0 then os.exit(1) end
