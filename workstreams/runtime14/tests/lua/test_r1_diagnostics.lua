local script=debug.getinfo(1,'S').source:sub(2):gsub('\\','/')
local F=dofile(script:match('^(.*)/[^/]+$')..'/production_engine.lua')
local root=assert(arg[1],'explicit Runtime stage required')
local tests={}
local function test(name,fn) tests[#tests+1]={name,fn} end
test('cm_status prints all exact ownership and distinct version labels without writes',function()
    local w=F.Boot(root);w.logs={};w.resetSpies();w.console.cm_status('cm_status',F.ids.a)
    local output=table.concat(w.logs,'\n')
    for _,field in ipairs({'ConfiguredChoice','PreferredChoice','EffectiveMode','MasterEnabled','Transition',
        'RestoreState','RestoreFailures','CvGuid','LiveBodySetVisual','OriginalBodySetVisual','LiveEquipmentRace',
        'OriginalEquipmentRace','BodyFamilyId','ClothMorphOwnedCcsvs','LiveVisuals',
        'PackageVersion64','PackageSemver','RuntimeCodeVersion','PersistentSchema','ScriptExtenderRequiredVersion',
        'PassThroughApiVersion','ExternalRefitApiVersion','BodyFamilyApiVersion','ProviderRegistrySnapshotApiVersion','CleanupApiVersion'}) do
        assert(output:find(field..':',1,true),'missing status label '..field)
    end
    assert(#w.writes==0,'status wrote gameplay')
end)
test('ownership diagnostics safely report an invalid record without repairing it',function()
    local w=F.Boot(root);w.state.Bodies[F.ids.a]='invalid';w.resetSpies()
    local status=w.mod.GetOwnershipStatus(F.ids.a)
    assert(status.effectiveMode=='external' and #status.failureCodes>0,'invalid state not reported as gated')
    assert(w.state.Bodies[F.ids.a]=='invalid' and #w.writes==0,'diagnostic repaired invalid record')
end)
test('ownership diagnostic arrays are detached from PersistentVars',function()
    local w=F.Boot(root);w.state.Bodies[F.ids.a].RestoreFailures={'fixture-failure'}
    local status=w.mod.GetOwnershipStatus(F.ids.a);status.failureCodes[1]='changed'
    assert(w.state.Bodies[F.ids.a].RestoreFailures[1]=='fixture-failure','diagnostic leaked mutable table')
end)
test('global diagnostics safely classify a non-table record as blocked',function()
    local w=F.Boot(root);w.state.Bodies[F.ids.a]=123;w.resetSpies()
    local called,status=pcall(w.mod.GetStateDiagnostics)
    assert(called and type(status)=='table' and status.SchemaFailure,'invalid global state crashed diagnostics')
    assert(status.BlockedGuids[1]==F.ids.a and #w.writes==0,'malformed record not classified read-only')
end)
local failed=0
for _,row in ipairs(tests) do local ok,why=pcall(row[2]);if ok then print('PASS '..row[1]) else failed=failed+1;print('FAIL '..row[1]..' '..tostring(why)) end end
print(('R1_DIAGNOSTICS_RESULT %d/%d'):format(#tests-failed,#tests))
if failed>0 then os.exit(1) end
