local script=debug.getinfo(1,'S').source:sub(2):gsub('\\','/')
local F=dofile(script:match('^(.*)/[^/]+$')..'/production_engine.lua')
local root=assert(arg[1],'explicit Runtime stage required')
local tests={}
local function test(name,fn) tests[#tests+1]={name,fn} end
local function has(values,wanted) for _,v in ipairs(values) do if v==wanted then return true end end;return false end
for _,case in ipairs({
    {'CV.BodySetVisual','base-restore-write-rejected'},
    {'Template.EquipmentRace','equipment-restore-write-rejected'},
    {'CCA.Visuals','ccsv-strip-write-rejected'},
}) do
    test('failed '..case[1]..' restoration stays External and retains exact retry evidence',function()
        local fail=false
        local w=F.Boot(root,{onWrite=function(_,kind,guid)
            if fail and guid==F.ids.a and kind==case[1] then error('injected write rejection') end
        end})
        if case[1]=='CV.BodySetVisual' then assert(w.mod.SetDesiredBody(F.ids.a,'bcb'))
        else assert(w.console.cm_applyccsv('cm_applyccsv','a22009cd-b9e9-55b1-8295-f89a0ede1bf6',F.ids.a)) end
        fail=true
        assert(w.mod.SetDesiredBody(F.ids.a,'external')==false,'failed restore reported success')
        local rec=w.state.Bodies[F.ids.a]
        assert(rec.Choice=='external' and rec.Transition~=nil,'failed restore lost its gate/journal')
        assert(rec.OrigBodySetVisual==F.ids.body and rec.OrigEquipRace==F.ids.er,'failure erased original evidence')
        assert(has(rec.RestoreFailures,case[2]),'missing exact restore failure code')
        if case[1]=='CCA.Visuals' then assert(rec.OwnedCcsvs['a22009cd-b9e9-55b1-8295-f89a0ede1bf6'],'failed strip erased claim') end
        fail=false
        assert(w.mod.SetDesiredBody(F.ids.a,'external'),'explicit restore retry failed')
        assert(rec.RestoreState=='clean' and rec.Transition==nil)
    end)
end
for _,phase in ipairs({'gated','captured','applying','verifying'}) do
    test('saved managed transition '..phase..' rolls back before ordinary load reapply',function()
        local w=F.Boot(root)
        local rec=w.state.Bodies[F.ids.a]
        rec.Choice='bcb';rec.PreferredChoice='bcb';rec.RestoreState='pending'
        rec.Transition={Direction='to_managed',Phase=phase,RequestedChoice='bcb'}
        w.resources[F.ids.cv].VisualSet.BodySetVisual=F.ids.bcb
        w.entities[F.ids.a].ServerCharacter.Template.EquipmentRace='c7a11e5e-0002-4b0d-9e57-5bbf00000002'
        w.fire('SavegameLoaded')
        assert(rec.Choice=='external' and rec.RestoreState=='clean' and rec.Transition==nil,'interrupted transition not restored')
        assert(w.resources[F.ids.cv].VisualSet.BodySetVisual==F.ids.body,'managed body reapplied after rollback')
        assert(w.entities[F.ids.a].ServerCharacter.Template.EquipmentRace==F.ids.er,'managed ER reapplied after rollback')
    end)
end
test('successful body write cannot conceal failed required EquipmentRace application',function()
    local armed=false
    local w=F.Boot(root,{onWrite=function(_,kind,guid,value)
        if armed and kind=='Template.EquipmentRace' and guid==F.ids.a and value~=F.ids.er then error('ER refused') end
    end})
    armed=true
    assert(w.mod.SetDesiredBody(F.ids.a,'bcb')==false,'body-only success concealed failed ER')
    assert(w.state.Bodies[F.ids.a].Choice=='external','failed managed transition remained managed')
    assert(w.resources[F.ids.cv].VisualSet.BodySetVisual==F.ids.body,'failed managed body not rolled back')
end)
test('failed Vanilla writes cannot be reported as a successful managed transition',function()
    local armed=false
    local w=F.Boot(root,{onWrite=function(_,kind,guid,value)
        if armed and guid==F.ids.a and ((kind=='CV.BodySetVisual' and value~=F.ids.body)
            or (kind=='Template.EquipmentRace' and value~=F.ids.er)) then error('Vanilla refused') end
    end})
    armed=true
    assert(w.mod.SetDesiredBody(F.ids.a,'vanilla')==false,'Vanilla boolean ignored readback failure')
    assert(w.state.Bodies[F.ids.a].Choice=='external')
end)
test('failed preflight preserves a clean External baseline and never schedules rollback writes',function()
    local w=F.Boot(root);assert(w.mod.SetDesiredBody(F.ids.a,'external'))
    local foreign='77777777-7777-4777-8777-777777777777'
    w.resources[foreign]={SourceFile='Generated/Public/ExternalOwner/body.GR2'}
    w.resources[F.ids.cv].VisualSet.BodySetVisual=foreign
    w.entities[F.ids.a].CharacterCreationStats=nil
    w.resetSpies()
    assert(w.mod.SetDesiredBody(F.ids.a,'bcb')==false,'incomplete preflight accepted')
    local rec=w.state.Bodies[F.ids.a]
    assert(rec.OrigBodySetVisual==F.ids.body,'failed capture overwrote prior evidence')
    w.fire('SavegameLoaded')
    assert(#w.writes==0 and w.resources[F.ids.cv].VisualSet.BodySetVisual==foreign,'no-write preflight caused later restoration writes')
end)
test('load-time CV change gates the record without replacing its trusted originals',function()
    local w=F.Boot(root);assert(w.mod.SetDesiredBody(F.ids.a,'bcb'))
    local rec=w.state.Bodies[F.ids.a]
    local newCv='66666666-6666-4666-8666-666666666666'
    w.entities[F.ids.a].ServerCharacter.Template.CharacterVisualResourceID=newCv
    w.fire('SavegameLoaded')
    assert(rec.CvGuid==F.ids.cv and rec.OrigBodySetVisual==F.ids.body,'load replaced trusted original/CV evidence')
    assert(w.mod.GetOwnershipStatus(F.ids.a).effectiveMode=='external','changed CV record not gated')
    assert(w.resources[newCv].VisualSet.BodySetVisual==F.ids.body,'new CV was mutated')
end)
local failed=0
for _,row in ipairs(tests) do local ok,why=pcall(row[2]);if ok then print('PASS '..row[1]) else failed=failed+1;print('FAIL '..row[1]..' '..tostring(why)) end end
print(('R1_FAILURE_MATRIX_RESULT %d/%d'):format(#tests-failed,#tests))
if failed>0 then os.exit(1) end
