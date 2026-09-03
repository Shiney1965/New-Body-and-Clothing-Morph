local script=debug.getinfo(1,'S').source:sub(2):gsub('\\','/')
local F=dofile(script:match('^(.*)/[^/]+$')..'/production_engine.lua')
local root=assert(arg[1],'explicit Runtime stage required')
local tests={}
local function test(name,fn) tests[#tests+1]={name,fn} end
local calls={
    {'ApplyBody',function(w,r) w.mod.ApplyBody(F.ids.a,'sbbf') end},
    {'SetBaseBody',function(w,r) w.mod.SetBaseBody(F.ids.a,'sbbf',F.ids.sbbf) end},
    {'Reconcile',function(w,r) w.mod.Reconcile(F.ids.a,'test') end},
    {'StripOurOverride',function(w,r) w.mod.StripOurOverride(F.ids.a,'permanent',F.ids.external) end},
    {'EquipRace.SetClothed',function(w,r) w.modules['EquipRace.lua'].SetClothed(F.ids.a,'sbbf',r) end},
    {'EquipRace.RefreshEquipment',function(w,r) w.modules['EquipRace.lua'].RefreshEquipment(F.ids.a) end},
    {'EquipRace.OnEquipped',function(w,r) w.modules['EquipRace.lua'].OnEquipped('item',F.ids.a,r) end},
    {'EquipRace.ForceSetEquipRace',function(w,r) w.modules['EquipRace.lua'].ForceSetEquipRace(F.ids.a,F.ids.er,r) end},
    {'EquipRace.ReapplyAll',function(w,r) w.modules['EquipRace.lua'].ReapplyAll({[F.ids.a]=r},'test') end},
    {'Family.SetClothed',function(w,r) w.modules['BodyFamilyEquipRace.lua'].SetClothed(F.ids.a,'sbbf',r) end},
    {'Family.RefreshEquipment',function(w,r) w.modules['BodyFamilyEquipRace.lua'].RefreshEquipment(F.ids.a) end},
    {'Family.OnEquipped',function(w,r) w.modules['BodyFamilyEquipRace.lua'].OnEquipped('item',F.ids.a,r) end},
    {'Family.Restore',function(w,r) w.modules['BodyFamilyEquipRace.lua'].Restore(F.ids.a,r) end},
    {'Family.RecoverUnavailable',function(w,r) w.modules['BodyFamilyEquipRace.lua'].RecoverUnavailable(F.ids.a,r,'bcb',function() error('gated callback invoked') end) end},
    {'Family.ReapplyAll',function(w,r) w.modules['BodyFamilyEquipRace.lua'].ReapplyAll({[F.ids.a]=r},'test') end},
}
for _,entry in ipairs(calls) do
    test('External mutator '..entry[1]..' has zero gameplay access',function()
        local w=F.Boot(root);assert(w.mod.SetDesiredBody(F.ids.a,'external'))
        local rec=w.state.Bodies[F.ids.a];w.resetSpies();entry[2](w,rec)
        assert(#w.reads==0 and #w.writes==0,'gated gameplay access')
        assert(rec.Choice=='external','gated callback changed configured choice')
    end)
end
test('MCM dedupe is keyed by character, not shared between users',function()
    local w=F.Boot(root)
    w.channel.handler({cmd='mcm_setbody',arg='external',target=F.ids.a},1)
    w.channel.handler({cmd='mcm_setbody',arg='external',target=F.ids.b},0x10002)
    assert(w.state.Bodies[F.ids.a].Choice=='external')
    assert(w.state.Bodies[F.ids.b] and w.state.Bodies[F.ids.b].Choice=='external','second user action was lost')
end)
test('body feedback distinguishes configured choice from effective External',function()
    local w=F.Boot(root);w.mod.SetMasterEnabled(false,'test-server')
    w.channel.handler({cmd='setbody',arg='bcb',target=F.ids.a},1)
    local feedback=w.broadcasts[#w.broadcasts]
    assert(feedback.choice=='bcb' and feedback.effectiveMode=='external','feedback conflated configured/effective choice')
    assert(feedback.masterEnabled==false and feedback.restoreState=='clean','feedback omitted ownership state')
end)
test('guest can request read-only master status without changing state',function()
    local w=F.Boot(root);w.resetSpies()
    local result=w.channel.handler({cmd='master',arg='status'},0x10002)
    assert(type(result)=='table' and result.MasterEnabled==true,'read-only status was treated as host mutation')
    assert(#w.writes==0,'status wrote gameplay')
end)
local failed=0
for _,row in ipairs(tests) do local ok,why=pcall(row[2]);if ok then print('PASS '..row[1]) else failed=failed+1;print('FAIL '..row[1]..' '..tostring(why)) end end
print(('R1_MUTATOR_INVENTORY_RESULT %d/%d'):format(#tests-failed,#tests))
if failed>0 then os.exit(1) end
