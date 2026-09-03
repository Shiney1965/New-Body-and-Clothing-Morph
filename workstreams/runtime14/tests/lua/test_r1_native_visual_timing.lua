-- The live 05_equipmentrace_probe/PROBE_GUIDE.md records delayed native-add
-- visibility. This fixture checks ownership safety, not rendered geometry.
local script=debug.getinfo(1,'S').source:sub(2):gsub('\\','/')
local F=dofile(script:match('^(.*)/[^/]+$')..'/production_engine.lua')
local root=assert(arg[1],'explicit Runtime stage required')
local CCSV='a22009cd-b9e9-55b1-8295-f89a0ede1bf6'
local tests={}
local function test(name,fn) tests[#tests+1]={name,fn} end
test('native-add fixture does not fabricate same-command visibility',function()
    local w=F.Boot(root)
    w.env.Osi.AddCustomVisualOverride(F.ids.a,CCSV)
    assert(#w.entities[F.ids.a].CharacterCreationAppearance.Visuals==1)
    assert(#w.nativeAdds==1)
    w.flushNativeAdds()
    assert(w.entities[F.ids.a].CharacterCreationAppearance.Visuals[2]==CCSV)
end)
test('known managed CCSV command succeeds without untracked native work',function()
    local w=F.Boot(root)
    assert(w.console.cm_applyccsv('cm_applyccsv',CCSV,F.ids.a)==true,
        'managed native add is not immediately readable')
    assert(w.state.Bodies[F.ids.a].OwnedCcsvs[CCSV])
    assert(#w.nativeAdds==0,'managed command left uncancellable native add')
end)
test('External cannot receive an orphaned native add from earlier command',function()
    local w=F.Boot(root)
    w.console.cm_applyccsv('cm_applyccsv',CCSV,F.ids.a)
    assert(w.mod.SetDesiredBody(F.ids.a,'external'))
    w.flushNativeAdds();w.flushTimers()
    local list=w.entities[F.ids.a].CharacterCreationAppearance.Visuals
    assert(#list==1 and list[1]==F.ids.external,
        'DEFERRED_NATIVE_ADD_UNRESOLVED: unowned visual appeared after External')
end)
test('scoped append preserves current unowned entries order and duplicates',function()
    local w=F.Boot(root)
    local third='cccccccc-cccc-4ccc-8ccc-cccccccccccc'
    w.entities[F.ids.a].CharacterCreationAppearance.Visuals={F.ids.external,third,F.ids.external}
    assert(w.console.cm_applyccsv('cm_applyccsv',CCSV,F.ids.a)==true)
    local list=w.entities[F.ids.a].CharacterCreationAppearance.Visuals
    assert(#list==4 and list[1]==F.ids.external and list[2]==third and list[3]==F.ids.external and list[4]==CCSV)
    assert(w.mod.SetDesiredBody(F.ids.a,'external'))
    list=w.entities[F.ids.a].CharacterCreationAppearance.Visuals
    assert(#list==3 and list[1]==F.ids.external and list[2]==third and list[3]==F.ids.external)
end)
test('preexisting unowned target is never adopted or removed',function()
    local w=F.Boot(root)
    w.entities[F.ids.a].CharacterCreationAppearance.Visuals={F.ids.external,CCSV,CCSV}
    assert(w.console.cm_applyccsv('cm_applyccsv',CCSV,F.ids.a)~=true)
    assert(w.state.Bodies[F.ids.a].OwnedCcsvs[CCSV]==nil)
    assert(w.mod.SetDesiredBody(F.ids.a,'external'))
    local list=w.entities[F.ids.a].CharacterCreationAppearance.Visuals
    assert(#list==3 and list[2]==CCSV and list[3]==CCSV)
end)
for _,failure in ipairs({'rejected','no-op','readback'}) do
    test('CCSV '..failure..' write cannot acquire ownership',function()
        local armed=false
        local w=F.Boot(root,{visualWriteNoop=failure=='no-op',onWrite=function(_,kind)
            if armed and failure=='rejected' and kind=='CCA.Visuals' then error('injected CCA rejection') end
        end})
        if failure=='readback' then
            local backing={F.ids.external}
            w.entities[F.ids.a].CharacterCreationAppearance=setmetatable({}, {
                __index=function(_,key) if key=='Visuals' then return backing end end,
                __newindex=function(_,key,_) if key=='Visuals' then backing={F.ids.external,F.ids.external} end end,
            })
        end
        armed=true
        assert(w.console.cm_applyccsv('cm_applyccsv',CCSV,F.ids.a)~=true)
        assert(w.state.Bodies[F.ids.a].OwnedCcsvs[CCSV]==nil)
        assert(#w.nativeAdds==0,'failed CCA write queued a native add')
    end)
end
test('replication failure after append cannot strand an unowned Runtime visual',function()
    local armed=false
    local w=F.Boot(root,{onWrite=function(_,kind,guid)
        if armed and kind=='Replicate' and guid==F.ids.a then
            armed=false
            error('injected one-shot replication rejection')
        end
    end})
    armed=true
    assert(w.console.cm_applyccsv('cm_applyccsv',CCSV,F.ids.a)~=true)
    local rec=w.state.Bodies[F.ids.a]
    local list=w.entities[F.ids.a].CharacterCreationAppearance.Visuals
    assert(rec.OwnedCcsvs[CCSV]==nil,'rejected transaction acquired ownership')
    assert(#list==1 and list[1]==F.ids.external,
        'CCA_REPLICATION_FAILURE_ORPHAN: failed command left an unowned Runtime visual')
end)
for _,entrypoint in ipairs({'transition','direct-debug'}) do
    test(entrypoint..' preserves proven ownership when propagation and owned rollback fail',function()
        local armed=false
        local rejected=false
        local later='dddddddd-dddd-4ddd-8ddd-dddddddddddd'
        local w=F.Boot(root,{onWrite=function(world,kind,guid)
            if armed and guid==F.ids.a and kind=='Replicate' then
                if not rejected then
                    rejected=true
                    local list=world.entities[F.ids.a].CharacterCreationAppearance.Visuals
                    list[#list+1]=later
                end
                error('replication unavailable')
            end
            if armed and rejected and guid==F.ids.a and kind=='CCA.Visuals' then error('rollback write unavailable') end
        end})
        armed=true
        local ok
        if entrypoint=='transition' then ok=w.console.cm_applyccsv('cm_applyccsv',CCSV,F.ids.a)
        else ok=w.mod.ApplyBody(F.ids.a,'sbbf') end
        assert(ok~=true,'failed propagation reported applied')
        local rec=w.state.Bodies[F.ids.a]
        assert(rec.OwnedCcsvs[CCSV],'proven server write evidence was erased')
        assert(rec.RestoreState~='clean' and rec.Transition,'failed rollback did not retain gated retry journal')
        assert(w.mod.GetOwnershipStatus(F.ids.a).effectiveMode=='external','failed rollback remained writable')
        armed=false
        assert(w.mod.SetDesiredBody(F.ids.a,'external'),'owned rollback retry failed')
        local list=w.entities[F.ids.a].CharacterCreationAppearance.Visuals
        assert(#list==2 and list[1]==F.ids.external and list[2]==later,'rollback lost unrelated later entry')
        assert(rec.OwnedCcsvs[CCSV]==nil and rec.RestoreState=='clean' and rec.Transition==nil)
    end)
end
local failed=0
for _,row in ipairs(tests) do
    local ok,why=pcall(row[2])
    if ok then print('PASS '..row[1]) else failed=failed+1;print('FAIL '..row[1]..' '..tostring(why)) end
end
print(('R1_NATIVE_VISUAL_TIMING_RESULT %d/%d'):format(#tests-failed,#tests))
if failed>0 then os.exit(1) end
