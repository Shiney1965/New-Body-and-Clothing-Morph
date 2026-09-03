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
test('accepted Tiefling saved CCSV remains a recorded-write claim when provider resource is absent',function()
    local ccsv='eca05d33-9887-5d5e-868a-8be722c2eb12'
    local other='294df7c6-c8d7-529d-9bcc-4122c0182cf3'
    local s={Version=6,Bodies={[A]={Choice='bcb',CvGuid=CV,OrigBodySetVisual=BODY,OrigEquipRace=ER,
        AppliedCcsv=ccsv,DesiredCcsv=other,OriginalVisuals={other}}}}
    assert(Schema.Migrate(s,{isRuntimeOwnedCcsv=function() return false end}))
    local claims=s.Bodies[A].OwnedCcsvs
    assert(claims[ccsv] and claims[ccsv].ProviderId=='legacy.runtime','accepted saved write not claimed')
    assert(claims[ccsv].OwnerModuleUuid=='20aca985-e3e9-41d7-bf8f-10f2a3c413e4')
    assert(claims[ccsv].ProviderDigest=='6610090CEE01091F802273D70FAEE071DCBA891900D77479ABBD828FCDDC60C6')
    assert(claims[ccsv].AddedForCvGuid==CV and claims[ccsv].ResourceKind=='body_ccsv')
    assert(claims[other]==nil,'DesiredCcsv or original visual inferred as owned')
end)
for _,field in ipairs({'AppliedCcsv','CvGuid'}) do
    test('invalid schema6 '..field..' cannot create a legacy claim',function()
        local s={Version=6,Bodies={[A]={Choice='sbbf',CvGuid=CV,AppliedCcsv=CCSV}}}
        s.Bodies[A][field]='invalid'
        assert(Schema.Migrate(s)==nil,'malformed legacy claim accepted')
        assert(s.Version==6,'invalid migration mutated source version')
    end)
end
test('missing saved CV never borrows live CV to mint ownership',function()
    local s={Version=6,Bodies={[A]={Choice='sbbf',AppliedCcsv=CCSV}}}
    assert(Schema.Migrate(s))
    assert(next(s.Bodies[A].OwnedCcsvs)==nil and s.Bodies[A].RestoreState=='blocked')
end)
for _,case in ipairs({
    {'OriginalVisuals',{[2]=BODY}}, {'OriginalVisuals',{'invalid'}},
    {'RestoreFailures',{false}}, {'RemovedOriginalVisuals',{invalid=true}},
    {'HistoricalOriginals',{[2]={}}},
    {'Transition',{Direction='unknown',Phase='gated'}},
    {'Transition',{Direction='to_managed',Phase='unknown'}},
    {'ActiveProvider',{ProviderId='provider',OwnerModuleUuid='invalid',ProviderDigest=string.rep('A',64)}},
}) do
    test('schema7 rejects malformed nested '..case[1]..' contract',function()
        local s=valid();s.Bodies[A][case[1]]=case[2]
        assert(Schema.Migrate(s)==nil,'malformed nested field accepted')
    end)
end
test('ordinary master predicates cannot contradict each other',function()
    local s=valid();s.MasterEnabled=false
    assert(Schema.Migrate(s)==nil,'master off with open gate accepted')
    s=valid();s.MutationGateClosed=true
    assert(Schema.Migrate(s)==nil,'ordinary enabled with closed gate accepted')
end)
test('malformed persisted provider descriptor cannot become source authority',function()
    local s=valid();s.ProviderDescriptors.bad='not a descriptor'
    assert(Schema.Migrate(s)==nil,'malformed provider descriptor accepted')
end)
local failed=0
for _,row in ipairs(tests) do local ok,why=pcall(row[2]);if ok then print('PASS '..row[1]) else failed=failed+1;print('FAIL '..row[1]..' '..tostring(why)) end end
print(('R1_SCHEMA_RESULT %d/%d'):format(#tests-failed,#tests))
if failed>0 then os.exit(1) end
