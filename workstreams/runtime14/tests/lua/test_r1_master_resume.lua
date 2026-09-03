local script=debug.getinfo(1,'S').source:sub(2):gsub('\\','/')
local F=dofile(script:match('^(.*)/[^/]+$')..'/production_engine.lua')
local root=assert(arg[1],'explicit Runtime stage required')
local tests={}
local function test(name,fn) tests[#tests+1]={name,fn} end
test('global disable does not overwrite a clean External owner baseline',function()
    local w=F.Boot(root)
    assert(w.mod.SetDesiredBody(F.ids.a,'bcb'))
    assert(w.mod.SetDesiredBody(F.ids.a,'external'))
    local foreign='77777777-7777-4777-8777-777777777777'
    w.resources[foreign]={SourceFile='Generated/Public/ExternalOwner/body.GR2'}
    w.resources[F.ids.cv].VisualSet.BodySetVisual=foreign
    w.resetSpies();w.mod.SetMasterEnabled(false,'test-server')
    assert(w.resources[F.ids.cv].VisualSet.BodySetVisual==foreign,'clean External baseline overwritten')
    assert(#w.writes==0,'global disable wrote clean External character')
end)
test('load resumes master disable saved before the first character journal',function()
    local w=F.Boot(root)
    assert(w.console.cm_applyccsv('cm_applyccsv','a22009cd-b9e9-55b1-8295-f89a0ede1bf6',F.ids.a))
    w.state.MasterEnabled=false;w.state.MutationGateClosed=true;w.state.MasterState='off_restoring';w.state.PassThroughRestoreComplete=false
    w.state.MasterTransition={Direction='disable',Started=true,PendingCharacters={[F.ids.a]=true}}
    local applied=w.state.Bodies[F.ids.a].AppliedCcsv
    assert(applied,'fixture CCSV missing')
    w.fire('SavegameLoaded')
    local rec=w.state.Bodies[F.ids.a]
    assert(w.state.MasterState=='off_restored' and w.state.PassThroughRestoreComplete,'global disable did not resume')
    assert(rec.Choice=='sbbf' and rec.RestoreState=='clean','configured choice/restore wrong')
    assert(rec.AppliedCcsv==applied,'Off resume stripped owned CCSV via origin restore')
end)
test('load resumes master enable saved before the first character journal',function()
    local w=F.Boot(root)
    assert(w.mod.SetDesiredBody(F.ids.a,'bcb'));w.mod.SetMasterEnabled(false,'test-server')
    w.state.MasterEnabled=true;w.state.MutationGateClosed=true;w.state.MasterState='enabling';w.state.PassThroughRestoreComplete=false
    w.state.MasterTransition={Direction='enable',Started=true,PendingCharacters={[F.ids.a]=true},RequestedChoices={[F.ids.a]='bcb'}}
    w.fire('SavegameLoaded')
    assert(w.state.MasterState=='enabled' and w.state.MutationGateClosed==false,'global enable did not resume')
    assert(w.state.Bodies[F.ids.a].Choice=='bcb' and w.state.Bodies[F.ids.a].RestoreState=='clean')
    assert(w.resources[F.ids.cv].VisualSet.BodySetVisual==F.ids.bcb,'configured BCB did not resume')
end)
test('released process CV ownership cannot later undo an external owner using the same resource',function()
    local w=F.Boot(root)
    assert(w.mod.SetDesiredBody(F.ids.a,'bcb'));assert(w.mod.SetDesiredBody(F.ids.a,'external'))
    w.resources[F.ids.cv].VisualSet.BodySetVisual=F.ids.bcb
    w.resetSpies();w.fire('SavegameLoaded')
    assert(w.resources[F.ids.cv].VisualSet.BodySetVisual==F.ids.bcb,'released CV write treated as still owned')
    assert(#w.writes==0,'released ownership caused a lifecycle write')
end)
test('recaptured External baseline replaces the old process restoration original',function()
    local inspect=false;local staleWrite=false
    local w=F.Boot(root,{onWrite=function(_,kind,_,value)
        if inspect and kind=='CV.BodySetVisual' and value==F.ids.body then staleWrite=true end
    end})
    assert(w.mod.SetDesiredBody(F.ids.a,'bcb'));assert(w.mod.SetDesiredBody(F.ids.a,'external'))
    local foreign='77777777-7777-4777-8777-777777777777'
    w.resources[foreign]={SourceFile='Generated/Public/ExternalOwner/body.GR2'}
    w.resources[F.ids.cv].VisualSet.BodySetVisual=foreign
    assert(w.mod.SetDesiredBody(F.ids.a,'bcb'))
    inspect=true;w.fire('SavegameLoaded')
    assert(not staleWrite,'old process original overrode recaptured baseline during lifecycle')
end)
test('shared-CV managed fallback cannot overwrite an External peers later body change',function()
    local state={Version=6,Bodies={
        [F.ids.a]={Choice='bcb',CvGuid=F.ids.cv,OrigBodySetVisual=F.ids.body,OrigEquipRace=F.ids.er},
        [F.ids.b]={Choice='bcb',CvGuid=F.ids.cv,OrigBodySetVisual=F.ids.body,OrigEquipRace=F.ids.er}}}
    local w=F.Boot(root,{state=state,sharedCv=true})
    assert(w.mod.SetDesiredBody(F.ids.b,'bcb'));assert(w.mod.SetDesiredBody(F.ids.a,'external'))
    local foreign='77777777-7777-4777-8777-777777777777'
    w.resources[foreign]={SourceFile='Generated/Public/ExternalOwner/body.GR2'}
    w.resources[F.ids.cv].VisualSet.BodySetVisual=foreign
    w.fire('SavegameLoaded')
    assert(w.resources[F.ids.cv].VisualSet.BodySetVisual==foreign,'managed peer overwrote External owner CV')
    assert(w.state.Bodies[F.ids.b].AppliedCcsv,'managed peer lost owned fallback')
    assert(w.mod.SetDesiredBody(F.ids.b,'external'))
    assert(w.resources[F.ids.cv].VisualSet.BodySetVisual==foreign,'fallback restoration overwrote External peer baseline')
end)
local failed=0
for _,row in ipairs(tests) do local ok,why=pcall(row[2]);if ok then print('PASS '..row[1]) else failed=failed+1;print('FAIL '..row[1]..' '..tostring(why)) end end
print(('R1_MASTER_RESUME_RESULT %d/%d'):format(#tests-failed,#tests))
if failed>0 then os.exit(1) end
