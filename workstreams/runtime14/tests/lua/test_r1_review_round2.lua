local script=debug.getinfo(1,'S').source:sub(2):gsub('\\','/')
local F=dofile(script:match('^(.*)/[^/]+$')..'/production_engine.lua')
local root=assert(arg[1],'verified Runtime stage required')
local VANILLA='3bc12bd9-6c5e-5067-a20f-b17e45647a10'
local tests={}
local function test(name,fn) tests[#tests+1]={name,fn} end
local function valid(w,where)
    local state,why=w.modules['StateSchema7.lua'].Migrate(w.state)
    assert(state~=nil,where..': '..tostring(why))
end
local function completedOff(w)
    assert(w.state.MasterEnabled==false and w.state.MutationGateClosed==true)
    assert(w.state.MasterState=='off_restored' and w.state.PassThroughRestoreComplete==true)
    assert(w.state.MasterTransition==nil)
    valid(w,'completed Off')
end
local function off(w)
    assert(w.mod.SetMasterEnabled(false,'test'))
    completedOff(w)
end

test('Off stops driving without origin-restore gameplay writes',function()
    local w=F.Boot(root)
    assert(w.mod.SetDesiredBody(F.ids.a,'bcb'))
    local live=w.resources[F.ids.cv].VisualSet.BodySetVisual
    local er=w.entities[F.ids.a].ServerCharacter.Template.EquipmentRace
    local visuals=#w.entities[F.ids.a].CharacterCreationAppearance.Visuals
    local origin=w.state.Bodies[F.ids.a].OrigBodySetVisual
    assert(live==F.ids.bcb,'fixture did not apply BCB')
    w.resetSpies()
    assert(w.mod.SetMasterEnabled(false,'test'))
    assert(#w.writes==0,'Off performed origin-restore gameplay writes')
    assert(w.resources[F.ids.cv].VisualSet.BodySetVisual==live,'Off rewound live body to origin')
    assert(w.entities[F.ids.a].ServerCharacter.Template.EquipmentRace==er,'Off rewound equipment race')
    assert(#w.entities[F.ids.a].CharacterCreationAppearance.Visuals==visuals,'Off rewound visuals')
    assert(w.state.Bodies[F.ids.a].OrigBodySetVisual==origin,'Off recaptured origin')
    assert(w.state.Bodies[F.ids.a].Choice=='bcb','Off converted managed choice via restore')
    completedOff(w)
end)

test('Off closes mutation gate and refuses ordinary writes',function()
    local w=F.Boot(root)
    off(w)
    w.resetSpies()
    local ok=w.modules['EquipRace.lua'].SetClothed(F.ids.a,'bcb',w.state.Bodies[F.ids.a])
    assert(ok==false and #w.reads==0 and #w.writes==0,'ordinary write authorized while Off')
    w.resetSpies()
    assert(w.mod.SetDesiredBody(F.ids.a,'sbbf'))
    assert(w.state.Bodies[F.ids.a].PreferredChoice=='sbbf')
    assert(#w.writes==0,'off preference performed gameplay writes')
    valid(w,'off preference')
end)

test('completed Off then External then re-enable remains schema valid',function()
    local w=F.Boot(root);off(w)
    assert(w.mod.SetCharacterMode(F.ids.a,'external','test'),'External after completed Off failed')
    valid(w,'External completed')
    assert(w.state.MasterEnabled==false and w.state.MutationGateClosed==true)
    assert(w.state.Bodies[F.ids.a].Choice=='external')
    assert(w.state.PassThroughRestoreComplete==true and w.state.MasterState=='off_restored')
    local ok,summary=w.mod.SetMasterEnabled(true,'test')
    assert(ok,'re-enable rejected producer-created state: '..tostring(summary and summary.status)..' '..tostring(summary and summary.failureCode))
    valid(w,'master re-enabled')
    assert(w.state.Bodies[F.ids.a].Choice=='external' and w.state.MasterState=='enabled')
end)

test('pending External journal while off is valid before restoration writes and grants no ordinary capability',function()
    local inspect,seen=false,false
    local w=F.Boot(root,{onWrite=function(world,kind,guid)
        if inspect and guid==F.ids.a then
            seen=true;valid(world,'before '..kind)
            assert(world.state.MasterEnabled==false and world.state.MutationGateClosed==true)
            assert(world.state.PassThroughRestoreComplete==false)
            assert(world.state.MasterState~='off_restored')
            local reads,writes=#world.reads,#world.writes
            local ok=world.modules['EquipRace.lua'].SetClothed(F.ids.a,'bcb',world.state.Bodies[F.ids.a])
            assert(ok==false and #world.reads==reads and #world.writes==writes,'ordinary write borrowed restoration authority')
        end
    end})
    off(w);inspect=true
    assert(w.mod.SetDesiredBody(F.ids.a,'external'))
    assert(seen,'External restoration boundary was not exercised')
    valid(w,'External finished')
    assert(w.state.Bodies[F.ids.a].Choice=='external')
    completedOff(w)
end)

for _,outcome in ipairs({'partial','blocked'}) do
    test(outcome..' External-while-off keeps a valid global retry journal',function()
        local reject=false
        local w=F.Boot(root,{onWrite=function(_,kind,guid)
            if reject and guid==F.ids.a and (kind=='Template.EquipmentRace'
                or (outcome=='blocked' and kind=='CV.BodySetVisual')) then error('injected restore refusal') end
        end})
        off(w);reject=true
        assert(w.mod.SetDesiredBody(F.ids.a,'external')==false)
        local rec=w.state.Bodies[F.ids.a]
        assert(rec.RestoreState==outcome,'wrong restore classification: '..tostring(rec.RestoreState))
        valid(w,'failed External-while-off')
        assert(w.state.MasterEnabled==false and w.state.MutationGateClosed==true and w.state.PassThroughRestoreComplete==false)
        assert(w.state.MasterState~='off_restored')
        assert(w.state.MasterTransition and w.state.MasterTransition.PendingCharacters[F.ids.a])
        reject=false
        assert(w.mod.SetDesiredBody(F.ids.a,'external'),'explicit External-while-off retry failed')
        valid(w,'retry completed')
        completedOff(w)
        assert(w.state.Bodies[F.ids.a].Choice=='external')
    end)
end

test('unavailable External-while-off remains pending and resumes on load',function()
    local w=F.Boot(root);off(w)
    local entity=w.entities[F.ids.a];w.entities[F.ids.a]=nil
    assert(w.mod.SetDesiredBody(F.ids.a,'external')==false)
    assert(w.state.Bodies[F.ids.a].RestoreState=='pending','unavailable External character not pending')
    valid(w,'unavailable External-while-off')
    assert(w.state.PassThroughRestoreComplete==false and w.state.MasterState~='off_restored')
    w.entities[F.ids.a]=entity;w.fire('SavegameLoaded')
    valid(w,'late External resumed')
    assert(w.state.Bodies[F.ids.a].Choice=='external' and w.state.Bodies[F.ids.a].RestoreState=='clean')
    completedOff(w)
end)

test('one successful External-while-off cannot conceal another pending character',function()
    local w=F.Boot(root);assert(w.mod.SetDesiredBody(F.ids.b,'bcb'));off(w)
    local b=w.entities[F.ids.b];w.entities[F.ids.b]=nil
    assert(w.mod.SetDesiredBody(F.ids.b,'external')==false)
    assert(w.mod.SetDesiredBody(F.ids.a,'external'))
    valid(w,'mixed External-while-off')
    assert(w.state.PassThroughRestoreComplete==false and w.state.MasterTransition.PendingCharacters[F.ids.b])
    w.resetSpies();assert(w.mod.SetDesiredBody(F.ids.a,'external'))
    assert(#w.reads==0 and #w.writes==0 and w.state.PassThroughRestoreComplete==false,'clean repeat changed pending global state')
    w.entities[F.ids.b]=b;w.fire('SavegameLoaded')
    valid(w,'all External characters resumed')
    completedOff(w)
end)

test('repeated clean External while off does not recapture or restore external-owned state',function()
    local w=F.Boot(root);off(w);assert(w.mod.SetDesiredBody(F.ids.a,'external'))
    local foreign='77777777-7777-4777-8777-777777777777'
    w.resources[foreign]={SourceFile='Generated/Public/ExternalOwner/body.GR2'}
    w.resources[F.ids.cv].VisualSet.BodySetVisual=foreign
    w.entities[F.ids.a].CharacterCreationAppearance.Visuals={F.ids.external,foreign}
    local original=w.state.Bodies[F.ids.a].OrigBodySetVisual
    w.resetSpies();assert(w.mod.SetDesiredBody(F.ids.a,'external'))
    assert(#w.reads==0 and #w.writes==0,'clean External performed gameplay work')
    assert(w.state.Bodies[F.ids.a].OrigBodySetVisual==original,'clean External recaptured baseline')
    assert(w.resources[F.ids.cv].VisualSet.BodySetVisual==foreign)
    assert(w.entities[F.ids.a].CharacterCreationAppearance.Visuals[2]==foreign)
    valid(w,'idempotent External')
end)

test('off preference update followed by explicit External remains External on re-enable',function()
    local w=F.Boot(root);off(w)
    w.resetSpies()
    assert(w.mod.SetDesiredBody(F.ids.a,'bcb'));valid(w,'off preference')
    assert(#w.writes==0,'off preference was not configuration-only')
    assert(w.mod.SetDesiredBody(F.ids.a,'external'));valid(w,'off explicit External')
    assert(w.state.Bodies[F.ids.a].PreferredChoice=='bcb')
    assert(w.mod.SetMasterEnabled(true,'test'))
    assert(w.state.Bodies[F.ids.a].Choice=='external')
    valid(w,'re-enabled explicit External')
end)

test('Off fail-soft does not force Vanilla on residual missing origin',function()
    local w=F.Boot(root)
    assert(w.mod.SetDesiredBody(F.ids.a,'bcb'))
    w.state.Bodies[F.ids.a].OrigBodySetVisual=nil
    w.resetSpies()
    assert(w.mod.SetMasterEnabled(false,'test'))
    assert(#w.writes==0,'Off wrote while origin was residual/missing')
    assert(w.resources[F.ids.cv].VisualSet.BodySetVisual==F.ids.bcb,'Off rewound or forced a fallback body')
    assert(w.resources[F.ids.cv].VisualSet.BodySetVisual~=VANILLA,'Off silently forced Vanilla')
    assert(w.state.Bodies[F.ids.a].Choice~='vanilla','Off silently selected Vanilla')
    valid(w,'fail-soft Off')
    assert(w.state.MasterEnabled==false and w.state.MutationGateClosed==true)
    assert(w.state.PassThroughRestoreComplete==true or w.state.MasterState~='enabled')
end)

test('failed External-while-off does not silently force Vanilla',function()
    local reject=false
    local w=F.Boot(root,{onWrite=function(_,kind,guid)
        if reject and guid==F.ids.a and (kind=='Template.EquipmentRace' or kind=='CV.BodySetVisual') then
            error('injected restore refusal')
        end
    end})
    assert(w.mod.SetDesiredBody(F.ids.a,'bcb'))
    off(w)
    local live=w.resources[F.ids.cv].VisualSet.BodySetVisual
    reject=true
    assert(w.mod.SetDesiredBody(F.ids.a,'external')==false)
    valid(w,'failed External-while-off fail-soft')
    assert(w.resources[F.ids.cv].VisualSet.BodySetVisual~=VANILLA,'failed External-while-off forced Vanilla')
    assert(w.state.Bodies[F.ids.a].Choice~='vanilla','failed External-while-off selected Vanilla')
    assert(w.state.PassThroughRestoreComplete==false)
    assert(live==F.ids.bcb or w.resources[F.ids.cv].VisualSet.BodySetVisual==live)
end)

local failed=0
for _,row in ipairs(tests) do local ok,why=pcall(row[2]);if ok then print('PASS '..row[1]) else failed=failed+1;print('FAIL '..row[1]..' '..tostring(why)) end end
print(('R1_REVIEW_ROUND2_RESULT %d/%d'):format(#tests-failed,#tests))
if failed>0 then os.exit(1) end