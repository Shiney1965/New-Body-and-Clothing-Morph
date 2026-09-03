local script=debug.getinfo(1,'S').source:sub(2):gsub('\\','/')
local F=dofile(script:match('^(.*)/[^/]+$')..'/production_engine.lua')
local root=assert(arg[1],'explicit composed Runtime root required')
local tests={}
local function test(name,fn) tests[#tests+1]={name,fn} end
local function eq(a,b,why) assert(a==b,(why or 'value')..': expected '..tostring(b)..', got '..tostring(a)) end

test('actual required modules are loaded, not mocked',function()
    local w=F.Boot(root)
    for _,name in ipairs({'Shared.lua','EquipRace.lua','BodyFamilyRegistry.lua','BodyFamilyEquipRace.lua','Targeting.lua','TattooPolicy.lua'}) do
        assert(type(w.modules[name])=='table',name)
    end
end)
test('exact public APIs and master return tuple',function()
    local w=F.Boot(root)
    eq(type(w.mod.SetCharacterMode),'function','SetCharacterMode')
    eq(type(w.mod.GetOwnershipStatus),'function','GetOwnershipStatus')
    local ok,summary=w.mod.SetMasterEnabled(true,'test-server')
    eq(type(ok),'boolean','master first result');eq(type(summary),'table','master second result')
end)
test('valid saved original survives a currently managed body during migration',function()
    local w=F.Boot(root,{currentBody=F.ids.sbbf})
    eq(w.state.Bodies[F.ids.a].OrigBodySetVisual,F.ids.body,'trusted original')
end)
test('External restores without any equipment refresh read or write',function()
    local w=F.Boot(root)
    w.equipped={[F.ids.a]={Breast='external-item'}}
    w.resetSpies()
    local ok=w.mod.SetDesiredBody(F.ids.a,'external')
    eq(ok,true,'restore')
    for _,row in ipairs(w.reads) do assert(row[1]~='GetEquippedItem','External read equipment for refresh') end
    for _,row in ipairs(w.writes) do assert(row[1]~='Unequip' and row[1]~='Equip','External refreshed equipment') end
end)
test('guest owning B cannot change global master',function()
    local w=F.Boot(root)
    w.channel.handler({cmd='master',arg='off',target=F.ids.b},0x10002)
    eq(w.state.MasterEnabled,true,'guest master request')
end)
test('master off preferences defer rather than drop',function()
    local w=F.Boot(root)
    w.mod.SetMasterEnabled(false,'test-server')
    w.resetSpies()
    local ok,status=w.mod.SetDesiredBody(F.ids.a,'bcb')
    eq(ok,true,'preference accepted');eq(w.state.Bodies[F.ids.a].Choice,'bcb','saved choice')
    eq(#w.writes,0,'no gameplay writes')
end)
test('pending restore gates direct real EquipRace entry',function()
    local w=F.Boot(root)
    local rec=w.state.Bodies[F.ids.a]
    rec.RestoreState='partial'
    w.resetSpies()
    w.modules['EquipRace.lua'].SetClothed(F.ids.a,'sbbf',rec)
    eq(#w.reads,0,'gated reads');eq(#w.writes,0,'gated writes')
end)
test('real MCM External label maps to External',function()
    local w=F.Boot(root)
    w.channel.handler({cmd='mcm_setbody',arg='External / Pass-through',target=F.ids.a},1)
    eq(w.state.Bodies[F.ids.a].Choice,'external','MCM External')
end)
test('guest cannot take ownership of host or another party member',function()
    local w=F.Boot(root)
    w.channel.handler({cmd='setbody',arg='external',target=F.ids.a},0x10002)
    eq(w.state.Bodies[F.ids.a].Choice,'sbbf','host target preserved')
end)
test('internal capability cannot be borrowed by reentrant External target',function()
    local state={Version=6,Bodies={
        [F.ids.a]={Choice='sbbf',CvGuid=F.ids.cv,OrigBodySetVisual=F.ids.body,OrigEquipRace=F.ids.er},
        [F.ids.b]={Choice='vanilla',Reverted=true,CvGuid='66666666-6666-4666-8666-666666666666',OrigBodySetVisual=F.ids.body,OrigEquipRace=F.ids.er}}}
    local attempted=false
    local w=F.Boot(root,{state=state,onWrite=function(world,kind,guid)
        if world.mod and not attempted and guid==F.ids.a then
            attempted=true
            local before=#world.reads
            world.mod.SetBaseBody(F.ids.b,'bcb',F.ids.bcb)
            eq(#world.reads,before,'reentrant external gameplay reads')
        end
    end})
    assert(w.mod.SetDesiredBody(F.ids.a,'sbbf'),'managed operation must exercise capability')
    assert(attempted,'reentrant boundary not exercised')
    eq(w.resources['66666666-6666-4666-8666-666666666666'].VisualSet.BodySetVisual,F.ids.body,'external body')
end)
test('every managed write has a persisted character transition',function()
    local seen=0
    local w=F.Boot(root,{onWrite=function(world,kind,guid)
        if world.state and guid==F.ids.a then
            seen=seen+1
            local rec=world.state.Bodies[guid]
            assert(type(rec.Transition)=='table','missing journal at '..kind)
            assert(rec.Transition.Direction=='to_managed','wrong transition direction')
        end
    end})
    assert(w.mod.SetDesiredBody(F.ids.a,'bcb'),'managed transition')
    assert(seen>0,'no production writes observed')
    eq(w.state.Bodies[F.ids.a].Transition,nil,'journal committed')
end)
test('External resume captures changed external baseline before managed writes',function()
    local w=F.Boot(root)
    assert(w.mod.SetDesiredBody(F.ids.a,'external'))
    local externalBody='77777777-7777-4777-8777-777777777777'
    w.resources[externalBody]={SourceFile='Generated/Public/AnotherBody/body.GR2'}
    w.resources[F.ids.cv].VisualSet.BodySetVisual=externalBody
    assert(w.mod.SetDesiredBody(F.ids.a,'bcb'))
    eq(w.state.Bodies[F.ids.a].OrigBodySetVisual,externalBody,'refreshed baseline')
    assert(w.mod.SetDesiredBody(F.ids.a,'external'))
    eq(w.resources[F.ids.cv].VisualSet.BodySetVisual,externalBody,'restored new external baseline')
end)
test('late character is not origin-restored on master disable',function()
    local w=F.Boot(root)
    local entity=w.entities[F.ids.a];w.entities[F.ids.a]=nil
    local _,summary=w.mod.SetMasterEnabled(false,'test-server')
    eq(w.state.Bodies[F.ids.a].RestoreState,'clean','Off queued origin restore for unavailable character')
    eq(w.state.Bodies[F.ids.a].Choice,'sbbf','Off converted unavailable character')
    eq(w.state.PassThroughRestoreComplete,true,'completed Off required a restore journal')
    w.entities[F.ids.a]=entity
    w.resetSpies();w.fire('SavegameLoaded')
    eq(w.state.Bodies[F.ids.a].RestoreState,'clean','load origin-restored after Off')
    eq(w.state.PassThroughRestoreComplete,true)
    eq(#w.writes,0,'load after Off performed origin-restore writes')
end)
test('delayed managed refresh is inert after External',function()
    local w=F.Boot(root)
    w.equipped={[F.ids.a]={Breast='external-item'}}
    w.modules['EquipRace.lua'].RefreshEquipment(F.ids.a)
    assert(#w.timers>0,'real delayed callback not scheduled')
    assert(w.mod.SetDesiredBody(F.ids.a,'external'))
    w.resetSpies();w.flushTimers()
    eq(#w.reads,0,'delayed gameplay reads');eq(#w.writes,0,'delayed gameplay writes')
end)
test('MCM origin-free master broadcast does not authorize a multiplayer guest',function()
    local w=F.Boot(root)
    w.env.Ext.Entity.GetAllEntitiesWithComponent=function() return {w.entities[F.ids.a],w.entities[F.ids.b]} end
    w.fire('MCM_Setting_Saved',{modUUID=F.ids.runtime,settingId='master_enabled',value=false})
    eq(w.state.MasterEnabled,true,'origin-free multiplayer master request')
end)
test('delayed family refresh is inert after External',function()
    local w=F.Boot(root)
    w.equipped={[F.ids.a]={Breast='external-item'}}
    w.modules['BodyFamilyEquipRace.lua'].RefreshEquipment(F.ids.a)
    assert(#w.timers>0,'family delayed callback not scheduled')
    assert(w.mod.SetDesiredBody(F.ids.a,'external'))
    w.resetSpies();w.flushTimers()
    eq(#w.writes,0,'delayed family gameplay writes')
end)
test('tattoo preference updates while master off without gameplay access',function()
    local w=F.Boot(root)
    w.mod.SetMasterEnabled(false,'test-server')
    w.resetSpies()
    w.channel.handler({cmd='mcm_set_tattoo_policy',arg='always_hide'},1)
    eq(w.state.BodyTattooPolicy,'always_hide','off tattoo preference')
    eq(#w.writes,0,'off tattoo writes')
end)
test('repeated clean External does not write or refresh body/equipment',function()
    local w=F.Boot(root)
    assert(w.mod.SetDesiredBody(F.ids.a,'external'))
    w.resetSpies()
    assert(w.mod.SetDesiredBody(F.ids.a,'external'))
    eq(#w.writes,0,'idempotent External writes')
end)
test('master off allows explicit retry of failed External restoration',function()
    local w=F.Boot(root)
    local entity=w.entities[F.ids.a];w.entities[F.ids.a]=nil
    w.mod.SetMasterEnabled(false,'test-server')
    w.entities[F.ids.a]=entity
    assert(w.mod.SetDesiredBody(F.ids.a,'external'),'explicit restoration retry rejected')
    eq(w.state.Bodies[F.ids.a].Choice,'external','explicit choice')
end)
test('a shared CV remains baseline for External while managed peer receives owned fallback',function()
    local state={Version=6,Bodies={
        [F.ids.a]={Choice='vanilla',Reverted=true,CvGuid=F.ids.cv,OrigBodySetVisual=F.ids.body,OrigEquipRace=F.ids.er},
        [F.ids.b]={Choice='bcb',CvGuid=F.ids.cv,OrigBodySetVisual=F.ids.body,OrigEquipRace=F.ids.er}}}
    local w=F.Boot(root,{state=state,sharedCv=true})
    assert(w.mod.SetDesiredBody(F.ids.b,'bcb'))
    eq(w.resources[F.ids.cv].VisualSet.BodySetVisual,F.ids.body,'shared baseline')
    local rec=w.state.Bodies[F.ids.b]
    assert(rec.AppliedCcsv and rec.OwnedCcsvs[rec.AppliedCcsv],'managed fallback lacks owned claim')
    eq(#w.entities[F.ids.a].CharacterCreationAppearance.Visuals,1,'external visuals preserved')
end)
test('public retirement cannot delete a third-party CCSV',function()
    local w=F.Boot(root)
    w.mod.StripOurOverride(F.ids.a,'permanent',F.ids.external)
    eq(w.entities[F.ids.a].CharacterCreationAppearance.Visuals[1],F.ids.external,'third-party visual')
end)
test('wrong live CV never strips a saved ownership claim',function()
    local w=F.Boot(root)
    local rec=w.state.Bodies[F.ids.a]
    local owned='a22009cd-b9e9-55b1-8295-f89a0ede1bf6'
    rec.OwnedCcsvs[owned]=w.modules['OwnershipLedger.lua'].LegacyRuntimeClaim(F.ids.cv)
    rec.AppliedCcsv=owned
    w.entities[F.ids.a].CharacterCreationAppearance.Visuals={F.ids.external,owned}
    w.entities[F.ids.a].ServerCharacter.Template.CharacterVisualResourceID='66666666-6666-4666-8666-666666666666'
    w.resetSpies()
    eq(w.mod.SetDesiredBody(F.ids.a,'external'),false,'wrong CV restoration')
    eq(w.entities[F.ids.a].CharacterCreationAppearance.Visuals[2],owned,'wrong-CV owned visual retained')
end)
test('releasing one same-CV claimant gives remaining managed character a fallback',function()
    local state={Version=6,Bodies={
        [F.ids.a]={Choice='bcb',CvGuid=F.ids.cv,OrigBodySetVisual=F.ids.body,OrigEquipRace=F.ids.er},
        [F.ids.b]={Choice='bcb',CvGuid=F.ids.cv,OrigBodySetVisual=F.ids.body,OrigEquipRace=F.ids.er}}}
    local w=F.Boot(root,{state=state,sharedCv=true})
    assert(w.mod.SetDesiredBody(F.ids.b,'bcb'))
    assert(w.mod.SetDesiredBody(F.ids.a,'external'))
    eq(w.resources[F.ids.cv].VisualSet.BodySetVisual,F.ids.body,'released CV')
    assert(w.state.Bodies[F.ids.b].AppliedCcsv,'remaining managed claimant has no fallback')
end)
test('cross-save master-off restores only prior process CV writes',function()
    local w=F.Boot(root)
    assert(w.mod.SetDesiredBody(F.ids.a,'bcb'))
    w.env.PersistentVars={Version=7,MasterEnabled=false,MutationGateClosed=true,MasterState='off_restored',
        PassThroughRestoreComplete=true,CleanupState='idle',Bodies={},OptoutTemplates={},ProviderDescriptors={},BodyTattooPolicy='match'}
    w.fire('SavegameLoaded')
    eq(w.resources[F.ids.cv].VisualSet.BodySetVisual,F.ids.body,'prior save CV restored')
end)
test('invalid schema cannot heal itself through repeated public calls',function()
    local w=F.Boot(root)
    w.state.ProviderDescriptors='malformed'
    w.resetSpies()
    for i=1,3 do
        eq(w.mod.SetDesiredBody(F.ids.a,'bcb'),false,'malformed schema call '..i)
        eq(w.state.ProviderDescriptors,'malformed','read-only rejection must not repair persistence')
    end
    eq(#w.writes,0,'malformed schema writes')
end)
test('an untracked direct module call cannot bypass baseline capture',function()
    local w=F.Boot(root)
    w.resetSpies()
    w.modules['EquipRace.lua'].SetClothed(F.ids.b,'sbbf',{OrigEquipRace=F.ids.er})
    eq(#w.reads,0,'untracked module gameplay reads');eq(#w.writes,0,'untracked module gameplay writes')
end)
test('External can be selected before a character was ever managed',function()
    local w=F.Boot(root)
    w.resetSpies()
    assert(w.mod.SetDesiredBody(F.ids.b,'external'),'new External request refused')
    local rec=w.state.Bodies[F.ids.b]
    eq(rec.Choice,'external','unmanaged External choice')
    eq(rec.OrigBodySetVisual,F.ids.body,'unmanaged External baseline')
    eq(#w.writes,0,'unmanaged External gameplay writes')
end)
test('a deferred but never-added fallback can be superseded without claiming an unowned CCSV',function()
    local reject=true
    local w=F.Boot(root,{onWrite=function(_,kind,_,value)
        if reject and kind=='CV.BodySetVisual' and value~=F.ids.body then error('read-only body') end
    end})
    w.equipped={[F.ids.a]={Breast='opaque-garment'}}
    assert(w.mod.SetDesiredBody(F.ids.a,'bcb'))
    local rec=w.state.Bodies[F.ids.a]
    assert(rec.DesiredCcsv and rec.AppliedCcsv==nil,'deferred path not exercised')
    reject=false;w.equipped={}
    assert(w.mod.SetDesiredBody(F.ids.a,'vanilla'),'absent unowned desired CCSV blocked mode change')
    assert(w.entities[F.ids.a].CharacterCreationAppearance.Visuals[1]==F.ids.external,'unowned visual removed')
end)
test('resolving different shared-CV targets retires the peers obsolete owned fallback',function()
    local state={Version=6,Bodies={
        [F.ids.a]={Choice='sbbf',CvGuid=F.ids.cv,OrigBodySetVisual=F.ids.body,OrigEquipRace=F.ids.er},
        [F.ids.b]={Choice='bcb',CvGuid=F.ids.cv,OrigBodySetVisual=F.ids.body,OrigEquipRace=F.ids.er}}}
    local w=F.Boot(root,{state=state,sharedCv=true})
    assert(w.mod.SetDesiredBody(F.ids.a,'sbbf'))
    assert(w.state.Bodies[F.ids.b].AppliedCcsv,'different-target peer fallback not installed')
    assert(w.mod.SetDesiredBody(F.ids.a,'bcb'))
    assert(w.resources[F.ids.cv].VisualSet.BodySetVisual==F.ids.bcb,'shared target not applied')
    assert(w.state.Bodies[F.ids.b].AppliedCcsv==nil,'obsolete fallback still overlays shared primary body')
end)
local failed=0
for _,row in ipairs(tests) do
    local ok,why=pcall(row[2])
    if ok then print('PASS '..row[1]) else failed=failed+1;print('FAIL '..row[1]..' '..tostring(why)) end
end
print(('R1_PRODUCTION_RESULT %d/%d'):format(#tests-failed,#tests))
if failed>0 then os.exit(1) end
