local script=debug.getinfo(1,'S').source:sub(2):gsub('\\','/')
local F=dofile(script:match('^(.*)/[^/]+$')..'/production_engine.lua')
local root=assert(arg[1],'explicit Runtime stage required')
local tests={}
local function test(name,fn) tests[#tests+1]={name,fn} end
test('master enable journals each managed character before writes',function()
    local inspect=false
    local w=F.Boot(root,{onWrite=function(world,kind,guid)
        if inspect and world.state and guid==F.ids.a then
            local rec=world.state.Bodies[guid]
            assert(rec.Transition and rec.Transition.Direction=='to_managed','missing master character journal at '..kind)
            assert(world.state.MutationGateClosed and world.state.MasterState=='enabling','master gate not persisted')
        end
    end})
    w.mod.SetMasterEnabled(false,'test-server')
    inspect=true
    local ok,summary=w.mod.SetMasterEnabled(true,'test-server')
    assert(ok and summary.managedGuids[1]==F.ids.a,'master reenable failed')
    assert(w.state.Bodies[F.ids.a].Choice=='sbbf' and w.state.Bodies[F.ids.a].Transition==nil)
end)
test('late managed character keeps configured choice across enable and resumes later',function()
    local w=F.Boot(root)
    local entity=w.entities[F.ids.a];w.entities[F.ids.a]=nil
    w.mod.SetMasterEnabled(false,'test-server')
    w.mod.SetDesiredBody(F.ids.a,'bcb')
    w.mod.SetMasterEnabled(true,'test-server')
    assert(w.state.Bodies[F.ids.a].Choice=='bcb','late configured choice lost')
    assert(w.state.Bodies[F.ids.a].RestoreState=='pending','late record not deferred')
    w.entities[F.ids.a]=entity;w.fire('SavegameLoaded')
    assert(w.state.Bodies[F.ids.a].Choice=='bcb' and w.state.Bodies[F.ids.a].RestoreState=='clean','late enable not resumed')
    assert(w.resources[F.ids.cv].VisualSet.BodySetVisual==F.ids.bcb,'late BCB body not applied')
end)
test('restoration re-adds only ledger-proven original visuals and preserves live order',function()
    local w=F.Boot(root)
    local removed='77777777-7777-4777-8777-777777777777'
    local later='88888888-8888-4888-8888-888888888888'
    local absent='99999999-9999-4999-8999-999999999999'
    local rec=w.state.Bodies[F.ids.a]
    rec.OriginalVisuals={removed,absent,later};rec.RemovedOriginalVisuals={[removed]=true}
    w.entities[F.ids.a].CharacterCreationAppearance.Visuals={F.ids.external,later}
    assert(w.mod.SetDesiredBody(F.ids.a,'external'))
    local visuals=w.entities[F.ids.a].CharacterCreationAppearance.Visuals
    assert(#visuals==3 and visuals[1]==F.ids.external and visuals[2]==removed and visuals[3]==later,'non-destructive restoration merge incorrect')
end)
test('master status returns read-only managed/external/pending GUID lists',function()
    local w=F.Boot(root)
    w.resetSpies()
    local status=w.console.cm_master('cm_master','status')
    assert(type(status)=='table' and status.ManagedGuids[1]==F.ids.a,'missing master status managed list')
    assert(type(status.PendingGuids)=='table' and type(status.ExternalGuids)=='table','missing master status lists')
    assert(#w.writes==0,'status mutated gameplay')
end)
test('fresh empty PersistentVars supports first explicit character management',function()
    local w=F.Boot(root,{state={}})
    local ok=w.mod.SetDesiredBody(F.ids.a,'bcb')
    assert(ok==true,'new-save management refused')
    assert(w.state.Version==7 and w.state.Bodies[F.ids.a].OrigBodySetVisual==F.ids.body,'fresh baseline absent')
end)
local failed=0
for _,row in ipairs(tests) do local ok,why=pcall(row[2]);if ok then print('PASS '..row[1]) else failed=failed+1;print('FAIL '..row[1]..' '..tostring(why)) end end
print(('R1_MASTER_JOURNALS_RESULT %d/%d'):format(#tests-failed,#tests))
if failed>0 then os.exit(1) end
