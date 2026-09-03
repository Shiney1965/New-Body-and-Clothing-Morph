local script=debug.getinfo(1,'S').source:sub(2):gsub('\\','/')
local F=dofile(script:match('^(.*)/[^/]+$')..'/production_engine.lua')
local root=assert(arg[1],'explicit Runtime stage required')
local tests={}
local function test(name,fn) tests[#tests+1]={name,fn} end
local function family(w)
    local definition=w.modules['BodyFamilyRegistry.lua'].GetOfficialDefinition()
    local vanilla='77777777-7777-4777-8777-777777777777'
    local vanillaBody='bfec2869-70cf-51a7-9806-1bbf02ff1bbe'
    w.resources[vanillaBody]={SourceFile='Generated/Public/ClothMorphRuntime/fixture-vanilla.GR2'}
    w.statics[vanilla]={VisualResource=vanillaBody}
    local spec={moduleUuid=F.ids.runtime,familyId=definition.id,sourceEquipRace=definition.sourceEquipRace,
        bodyType=1,bodyShape=0,profiles={
            vanilla={ccsv=vanilla,visual=vanillaBody,equipmentRace=definition.minted.vanilla},
            sbbf={ccsv='a22009cd-b9e9-55b1-8295-f89a0ede1bf6',visual=F.ids.sbbf,equipmentRace=definition.minted.sbbf},
            bcb={ccsv='fe01f8f7-814e-5c2e-9829-a0467fd5a6ce',visual=F.ids.bcb,equipmentRace=definition.minted.bcb}}}
    return definition,spec
end
local function item(w,source)
    local id='99999999-9999-4999-8999-999999999999'
    w.entities[id]={ServerItem={Template={Id=id,Equipment={Visuals={[source]={F.ids.body}}}}}}
    w.equipped={[F.ids.a]={Breast=id}}
    return id
end
test('late mature OnEquipped timer is gated after External',function()
    local w=F.Boot(root)
    local rec=w.state.Bodies[F.ids.a];rec.ClothedChoice='sbbf'
    local id=item(w,F.ids.er)
    w.modules['EquipRace.lua'].OnEquipped(id,F.ids.a,rec)
    assert(#w.timers>0,'mature late timer branch not exercised')
    assert(w.mod.SetDesiredBody(F.ids.a,'external'));w.resetSpies();w.flushTimers()
    assert(#w.reads==0 and #w.writes==0,'mature late timer escaped External gate')
end)
test('late family OnEquipped timer is gated after External',function()
    local w=F.Boot(root);local definition,spec=family(w)
    assert(w.mod.RegisterBodyFamily('fixture',spec))
    assert(w.mod.RegisterFamilyRefits('fixture',definition.id,{vanilla={},sbbf={},bcb={}},{}) )
    local rec=w.state.Bodies[F.ids.a]
    rec.BodyFamilyId=definition.id;rec.FamilyClothedChoice='sbbf';rec.FamilyOrigEquipRace=definition.sourceEquipRace
    w.modules['BodyFamilyEquipRace.lua'].RunBlanketPass(definition.id,'sbbf',false)
    local id=item(w,definition.sourceEquipRace)
    w.modules['BodyFamilyEquipRace.lua'].OnEquipped(id,F.ids.a,rec)
    assert(#w.timers>0,'family late timer branch not exercised')
    assert(w.mod.SetDesiredBody(F.ids.a,'external'));w.resetSpies();w.flushTimers()
    assert(#w.reads==0 and #w.writes==0,'family late timer escaped External gate')
end)
test('raw legacy registration modules cannot activate while master off',function()
    local w=F.Boot(root);local definition,spec=family(w)
    w.mod.SetMasterEnabled(false,'test-server');w.resetSpies()
    w.modules['BodyFamilyRegistry.lua'].RegisterBodyFamily('raw-bypass',spec)
    assert(w.modules['BodyFamilyRegistry.lua'].GetProvider(definition.id)==nil,'raw body registry bypassed master-off queue')
    w.modules['EquipRace.lua'].RegisterExternalRefits('raw-bypass',{sbbf={[F.ids.external]=F.ids.sbbf}})
    assert(w.modules['EquipRace.lua'].REFIT_BY_VR.sbbf[F.ids.external]==nil,'raw refits bypassed master-off queue')
    assert(#w.writes==0,'raw registration wrote gameplay')
end)
test('verified External restoration clears only Runtime family routing markers',function()
    local w=F.Boot(root);local definition=family(w)
    local rec=w.state.Bodies[F.ids.a]
    rec.BodyFamilyId=definition.id;rec.FamilyClothedChoice='sbbf';rec.ClothedChoice='sbbf'
    rec.FamilyOrigEquipRace=definition.sourceEquipRace
    assert(w.mod.SetDesiredBody(F.ids.a,'external'))
    assert(rec.BodyFamilyId==nil and rec.FamilyClothedChoice==nil and rec.ClothedChoice==nil,'restored routing markers not released')
    assert(rec.FamilyOrigEquipRace==definition.sourceEquipRace and rec.PreferredChoice=='sbbf','original/preference evidence erased')
end)
local failed=0
for _,row in ipairs(tests) do local ok,why=pcall(row[2]);if ok then print('PASS '..row[1]) else failed=failed+1;print('FAIL '..row[1]..' '..tostring(why)) end end
print(('R1_EVENT_MATRIX_RESULT %d/%d'):format(#tests-failed,#tests))
if failed>0 then os.exit(1) end
