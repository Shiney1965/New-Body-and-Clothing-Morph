local root=assert(arg[1],'explicit Runtime stage required')
local Schema=dofile(root..'/Mods/ClothMorphRuntime/ScriptExtender/Lua/StateSchema7.lua')
local A='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
local CV='11111111-1111-4111-8111-111111111111'
local BODY='22222222-2222-4222-8222-222222222222'
local ER='71180b76-5752-4a97-b71f-911a69197f58'
local CCSV='a22009cd-b9e9-55b1-8295-f89a0ede1bf6'
local tests={}
local function test(name,fn) tests[#tests+1]={name,fn} end
local function valid()
    return assert(Schema.Migrate({Version=6,Bodies={[A]={Choice='sbbf',CvGuid=CV,
        OrigBodySetVisual=BODY,OrigEquipRace=ER}},OptoutTemplates={},BodyTattooPolicy='match'}))
end
for _,row in ipairs({{'MasterEnabled','true'},{'MutationGateClosed',0},{'MasterState','ready'},
    {'PassThroughRestoreComplete',1},{'CleanupState','unknown'},{'BodyTattooPolicy','bad'},
    {'OptoutTemplates','bad'},{'ProviderDescriptors','bad'},{'Version','7'}}) do
    test('malformed top-level '..row[1]..' rejected without repair',function()
        local s=valid();s[row[1]]=row[2]
        local result=Schema.Migrate(s)
        assert(result==nil,'accepted invalid '..row[1])
        assert(s[row[1]]==row[2],'mutated invalid state')
    end)
end
for _,row in ipairs({{'RestoreState','ready'},{'RestoreFailures','bad'},{'OriginalVisuals','bad'},
    {'RemovedOriginalVisuals','bad'},{'HistoricalOriginals','bad'},{'Transition',true},
    {'ProviderTransition',true},{'ActiveProvider',true},{'CvGuid','bad'},
    {'OrigBodySetVisual','bad'},{'OrigEquipRace','bad'}}) do
    test('malformed record '..row[1]..' rejected without repair',function()
        local s=valid();s.Bodies[A][row[1]]=row[2]
        local result=Schema.Migrate(s)
        assert(result==nil,'accepted invalid '..row[1])
        assert(s.Bodies[A][row[1]]==row[2],'mutated invalid record')
    end)
end
test('nonlegacy CCSV claim requires matching active descriptor',function()
    local s=valid()
    s.Bodies[A].OwnedCcsvs[CCSV]={ProviderId='missing.provider',OwnerModuleUuid=A,
        ProviderDigest=string.rep('A',64),ResourceKind='body_ccsv',AddedForCvGuid=CV}
    assert(Schema.Migrate(s)==nil,'stale provider claim accepted')
end)
test('schema migration rejects malformed body records',function()
    assert(Schema.Migrate({Version=6,Bodies={[A]='bad'}})==nil,'legacy malformed record silently repaired')
end)
test('schema 6 preserves exact legacy claim and only that claim',function()
    local s={Version=6,Bodies={[A]={Choice='sbbf',CvGuid=CV,OrigBodySetVisual=BODY,
        OrigEquipRace=ER,AppliedCcsv=CCSV}},BodyTattooPolicy='match'}
    assert(Schema.Migrate(s))
    local claim=s.Bodies[A].OwnedCcsvs[CCSV]
    assert(claim.ProviderId=='legacy.runtime' and claim.ProviderDigest==Schema.R0_PACKAGE_SHA256)
    assert(Schema.Migrate(s)==s,'idempotent migration changed object')
end)
local failed=0
for _,row in ipairs(tests) do local ok,why=pcall(row[2]);if ok then print('PASS '..row[1]) else failed=failed+1;print('FAIL '..row[1]..' '..tostring(why)) end end
print(('R1_SCHEMA_RESULT %d/%d'):format(#tests-failed,#tests))
if failed>0 then os.exit(1) end
