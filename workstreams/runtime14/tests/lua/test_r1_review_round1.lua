local script=debug.getinfo(1,'S').source:sub(2):gsub('\\','/')
local F=dofile(script:match('^(.*)/[^/]+$')..'/production_engine.lua')
local root=assert(arg[1],'verified Runtime stage required')
local selected=arg[2]
local tests={}
local CCSV='a22009cd-b9e9-55b1-8295-f89a0ede1bf6'
local function test(group,name,fn) tests[#tests+1]={group,name,fn} end
local function clone(v) if type(v)~='table' then return v end;local out={};for k,x in pairs(v) do out[k]=clone(x) end;return out end
local function provider(w)
    w.loaded[F.ids.b]=true
    local ok,status=w.mod.RegisterExternalRefits('review-provider',
        {vanilla={},sbbf={[F.ids.external]=F.ids.sbbf},bcb={}},
        {ownerModuleUuid=F.ids.b,providerId='review.provider',bodyCcsvs={CCSV}})
    assert(ok and status=='ACTIVE','provider fixture failed to activate')
end
test('mcm','origin-free saved event cannot be laundered through the host client',function()
    local server=F.Boot(root)
    local client=F.Boot(root,{client=true})
    client.fire('SessionLoaded')
    server.env.Ext.Entity.GetAllEntitiesWithComponent=function() return {server.entities[F.ids.a],server.entities[F.ids.b]} end
    local payload={modUUID=F.ids.runtime,settingId='master_enabled',value=false,oldValue=true}
    server.fire('MCM_Setting_Saved',payload)
    assert(server.state.MasterEnabled==true,'origin-free server event acquired authority')
    client.fire('MCM_Setting_Saved',payload)
    for _,message in ipairs(client.broadcasts) do server.channel.handler(message,1) end
    assert(server.state.MasterEnabled==true,'guest-origin broadcast was laundered through host client')
end)
test('provider','saved ACTIVE without process activation cannot issue a new body claim',function()
    local old=F.Boot(root);provider(old)
    local w=F.Boot(root,{state=clone(old.state)})
    w.loaded[F.ids.b]=true
    assert(w.console.cm_applyccsv('cm_applyccsv',CCSV,F.ids.a)~=true,'absent owner admitted a new claim')
    assert(w.state.Bodies[F.ids.a].OwnedCcsvs[CCSV]==nil,'unactivated provider gained ownership')
    assert(w.state.ProviderDescriptors['review.provider'].activationState=='active','snapshot rewrote saved evidence')
end)
test('provider','snapshot distinguishes saved ACTIVE without rewriting saved evidence',function()
    local old=F.Boot(root);provider(old)
    local w=F.Boot(root,{state=clone(old.state)})
    assert(w.mod.GetProviderRegistrySnapshot().descriptors[1].activationState~='active','snapshot advertised persisted-only ACTIVE')
    assert(w.state.ProviderDescriptors['review.provider'].activationState=='active','snapshot rewrote saved evidence')
end)
test('provider','current activation is revalidated before a new claim',function()
    local w=F.Boot(root);provider(w);w.loaded[F.ids.b]=nil
    assert(w.console.cm_applyccsv('cm_applyccsv',CCSV,F.ids.a)~=true,'disappeared owner admitted a new claim')
    assert(w.state.Bodies[F.ids.a].OwnedCcsvs[CCSV]==nil)
end)
test('provider','activated available owner can claim and absent owner can still restore historical claim',function()
    local w=F.Boot(root);provider(w)
    assert(w.console.cm_applyccsv('cm_applyccsv',CCSV,F.ids.a))
    assert(w.state.Bodies[F.ids.a].OwnedCcsvs[CCSV].OwnerModuleUuid==F.ids.b)
    w.loaded[F.ids.b]=nil
    assert(w.mod.SetDesiredBody(F.ids.a,'external'),'historical restoration incorrectly required current provider activation')
    assert(w.state.Bodies[F.ids.a].OwnedCcsvs[CCSV]==nil)
end)
test('mcm','one guest body event cannot apply an unintended body choice to the host character',function()
    local server=F.Boot(root)
    local host=F.Boot(root,{client=true})
    local guest=F.Boot(root,{client=true})
    guest.env.Ext.Entity.GetAllEntitiesWithComponent=function() return {guest.entities[F.ids.b]} end
    local payload={modUUID=F.ids.runtime,settingId='body_choice',value='BCB',oldValue='SBBF'}
    host.fire('MCM_Setting_Saved',payload);guest.fire('MCM_Setting_Saved',payload)
    for _,message in ipairs(host.broadcasts) do server.channel.handler(message,1) end
    for _,message in ipairs(guest.broadcasts) do server.channel.handler(message,0x10002) end
    assert(server.state.Bodies[F.ids.a].Choice=='sbbf','guest body notification changed host character')
end)
test('master','master enable retains inner rollback blocker until explicit restoration',function()
    local armed,rejected=false,false
    local w=F.Boot(root,{sharedCv=true,onWrite=function(_,kind,guid)
        if armed and guid==F.ids.a and kind=='Replicate' then rejected=true;error('replication unavailable') end
        if armed and rejected and guid==F.ids.a and kind=='CCA.Visuals' then error('owned rollback unavailable') end
    end})
    assert(w.mod.SetDesiredBody(F.ids.b,'external'))
    assert(w.mod.SetMasterEnabled(false,'test'))
    armed=true;w.mod.SetMasterEnabled(true,'test')
    local rec=w.state.Bodies[F.ids.a]
    assert(rec.OwnedCcsvs[CCSV] and rec.Transition,'fixture failed to preserve unremoved append')
    local codes={};for _,code in ipairs(rec.RestoreFailures) do codes[code]=true end
    assert(codes.MANAGED_REAPPLY_ROLLBACK_FAILED,'master summary erased rollback-blocking evidence')
    armed=false
    assert(w.mod.SetDesiredBody(F.ids.a,'bcb')==false,'managed request bypassed explicit restore retry')
    assert(w.mod.SetDesiredBody(F.ids.a,'external'))
    assert(w.mod.SetDesiredBody(F.ids.a,'bcb'))
end)
test('crosssave','no-op process restore remains pending and retries after writer recovery',function()
    local w=F.Boot(root);assert(w.mod.SetDesiredBody(F.ids.a,'bcb'))
    local live=F.ids.bcb;local reject=true;local attempts=0
    w.resources[F.ids.cv].VisualSet=setmetatable({}, {
        __index=function(_,key) if key=='BodySetVisual' then return live end end,
        __newindex=function(_,key,value) if key=='BodySetVisual' then attempts=attempts+1;if not reject then live=value end end end,
    })
    w.env.PersistentVars={Version=7,MasterEnabled=false,MutationGateClosed=true,MasterState='off_restored',
        PassThroughRestoreComplete=true,CleanupState='idle',Bodies={},OptoutTemplates={},ProviderDescriptors={},BodyTattooPolicy='match'}
    w.fire('SavegameLoaded');assert(attempts==1,'first restoration not attempted')
    reject=false;w.fire('SavegameLoaded')
    assert(attempts==2 and live==F.ids.body,'failed process restore was retired without readback')
    local warned=false;for _,line in ipairs(w.warnings) do if line:find('base%-restore%-readback%-failed') then warned=true end end
    assert(warned,'failed process restore was not exposed')
end)
test('capture','new shared-CV claimant uses proven same-process original',function()
    local w=F.Boot(root,{state={},sharedCv=true})
    assert(w.mod.SetCharacterMode(F.ids.a,'bcb','test'))
    assert(w.mod.SetCharacterMode(F.ids.b,'bcb','test'),'second first-use claimant rejected existing process baseline')
    assert(w.state.Bodies[F.ids.b].OrigBodySetVisual==F.ids.body,'second claimant captured managed visual as original')
end)
test('capture','unattributed minted shared body is not accepted as an original',function()
    local w=F.Boot(root,{state={},sharedCv=true,currentBody=F.ids.bcb})
    assert(w.mod.SetCharacterMode(F.ids.b,'bcb','test')==false)
    assert(w.state.Bodies[F.ids.b].OrigBodySetVisual==nil)
end)
test('capture','stale process baseline cannot authorize an unrelated current shared value',function()
    local w=F.Boot(root,{state={},sharedCv=true})
    assert(w.mod.SetDesiredBody(F.ids.a,'bcb'))
    w.resources[F.ids.cv].VisualSet.BodySetVisual=F.ids.sbbf
    assert(w.mod.SetDesiredBody(F.ids.b,'sbbf')==false,'stale process ledger attested a different current value')
end)
local function history()
    return {ProviderId='legacy.runtime',ProviderDigest=string.rep('A',64),CvGuid=F.ids.cv,
        OrigBodySetVisual=F.ids.body,OrigEquipRace=F.ids.er,OriginalVisuals={F.ids.external},
        Effective=false,Reason='provider_remint'}
end
local corruptions={
    {'enabled-restore-complete',function(s) s.PassThroughRestoreComplete=true end},
    {'empty-history',function(s,r) r.HistoricalOriginals={{}} end},
    {'bad-clothed-choice',function(s,r) r.ClothedChoice='garbage' end},
    {'bad-family-choice',function(s,r) r.FamilyClothedChoice='off' end},
    {'bad-family-id',function(s,r) r.BodyFamilyId={} end},
    {'bad-optout-key',function(s) s.OptoutTemplates={not_guid=true} end},
    {'bad-optout-value',function(s) s.OptoutTemplates={[F.ids.external]='yes'} end},
    {'bad-character-key',function(s,r) s.Bodies.not_guid=clone(r) end},
    {'off-restored-pending-record',function(s,r) s.MasterEnabled=false;s.MutationGateClosed=true;s.MasterState='off_restored';s.PassThroughRestoreComplete=true;r.RestoreState='pending' end},
    {'bad-history-guid',function(s,r) local h=history();h.OrigBodySetVisual='bad';r.HistoricalOriginals={h} end},
    {'bad-history-effective',function(s,r) local h=history();h.Effective='yes';r.HistoricalOriginals={h} end},
    {'bad-history-visuals',function(s,r) local h=history();h.OriginalVisuals={'bad'};r.HistoricalOriginals={h} end},
    {'bad-history-provider-id',function(s,r) local h=history();h.ProviderId='';r.HistoricalOriginals={h} end},
    {'bad-history-digest',function(s,r) local h=history();h.ProviderDigest='bad';r.HistoricalOriginals={h} end},
    {'bad-history-cv',function(s,r) local h=history();h.CvGuid='bad';r.HistoricalOriginals={h} end},
    {'bad-history-reason',function(s,r) local h=history();h.Reason=nil;r.HistoricalOriginals={h} end},
    {'active-history-without-provider',function(s,r) local h=history();h.Effective=true;r.HistoricalOriginals={h} end},
    {'two-effective-history-rows',function(s,r) local h=history();h.Effective=true;r.ActiveProvider={ProviderId=h.ProviderId,ProviderDigest=h.ProviderDigest,OwnerModuleUuid=F.ids.runtime};r.HistoricalOriginals={h,clone(h)} end},
    {'effective-history-wrong-provider',function(s,r) local h=history();h.Effective=true;r.ActiveProvider={ProviderId='different',ProviderDigest=h.ProviderDigest,OwnerModuleUuid=F.ids.runtime};r.HistoricalOriginals={h} end},
    {'effective-history-wrong-cv',function(s,r) local h=history();h.Effective=true;h.CvGuid=F.ids.external;r.ActiveProvider={ProviderId=h.ProviderId,ProviderDigest=h.ProviderDigest,OwnerModuleUuid=F.ids.runtime};r.HistoricalOriginals={h} end},
}
for _,case in ipairs(corruptions) do test('schema',case[1]..' rejects rather than remaining managed',function()
    local initial=F.Boot(root);local state=clone(initial.state);case[2](state,state.Bodies[F.ids.a])
    local w=F.Boot(root,{state=state})
    assert(w.mod.GetOwnershipStatus(F.ids.a).effectiveMode=='external','malformed schema remained effectively managed')
    w.resetSpies();assert(w.mod.SetDesiredBody(F.ids.a,'bcb')==false,'malformed schema accepted a managed request')
    assert(#w.writes==0,'invalid schema wrote gameplay')
end) end
test('schema','valid history and exact optouts are preserved without mutation',function()
    local initial=F.Boot(root);local state=clone(initial.state)
    state.Bodies[F.ids.a].HistoricalOriginals={history()};state.OptoutTemplates={[F.ids.external]=false}
    local w=F.Boot(root,{state=state})
    assert(w.mod.GetOwnershipStatus(F.ids.a).effectiveMode=='sbbf')
    assert(w.state.Bodies[F.ids.a].HistoricalOriginals[1].Reason=='provider_remint' and w.state.OptoutTemplates[F.ids.external]==false)
end)
test('schema','nullable archived originals stay missing without binding to todays provider',function()
    local initial=F.Boot(root);local state=clone(initial.state);local h=history()
    h.ProviderId='archived.provider';h.CvGuid=F.ids.external;h.OrigBodySetVisual=nil;h.OrigEquipRace=nil
    state.Bodies[F.ids.a].HistoricalOriginals={h}
    local w=F.Boot(root,{state=state})
    assert(w.mod.GetOwnershipStatus(F.ids.a).effectiveMode=='sbbf')
    local saved=w.state.Bodies[F.ids.a].HistoricalOriginals[1]
    assert(saved.OrigBodySetVisual==nil and saved.OrigEquipRace==nil and saved.FamilyOrigEquipRace==nil)
    assert(saved.ProviderId=='archived.provider' and saved.CvGuid==F.ids.external and saved.Effective==false)
end)
test('status','cm_master status prints every required GUID classification',function()
    local w=F.Boot(root)
    local original=clone(w.state.Bodies[F.ids.a])
    for _,row in ipairs({{F.ids.b,'pending'},{F.ids.external,'partial'},{F.ids.cv,'blocked'}}) do
        local rec=clone(original);rec.Choice='external';rec.RestoreState=row[2];w.state.Bodies[row[1]]=rec
    end
    w.logs={};w.console.cm_master('cm_master','status')
    local out=table.concat(w.logs,'\n')
    local expected={ManagedGuids={F.ids.a},ExternalGuids={F.ids.b,F.ids.external,F.ids.cv},
        PendingGuids={F.ids.b},PartialGuids={F.ids.external},BlockedGuids={F.ids.cv}}
    for label,guids in pairs(expected) do
        local line=out:match(label..': ([^\n]*)')
        assert(line,'missing printed '..label)
        for _,guid in ipairs(guids) do assert(line:find(guid,1,true),'wrong GUID classification '..label) end
        local count=0;for _ in line:gmatch('%x%x%x%x%x%x%x%x%-%x%x%x%x%-%x%x%x%x%-%x%x%x%x%-%x%x%x%x%x%x%x%x%x%x%x%x') do count=count+1 end
        assert(count==#guids,'unexpected GUID in '..label)
    end
end)
local failed,count=0,0
for _,row in ipairs(tests) do if not selected or selected==row[1] then
    count=count+1
    local ok,why=pcall(row[3])
    if ok then print('PASS '..row[1]..': '..row[2]) else failed=failed+1;print('FAIL '..row[1]..': '..row[2]..' '..tostring(why)) end
end end
assert(count>0,'unknown review selector')
print(('R1_REVIEW_ROUND1_RESULT %s %d/%d'):format(selected or 'all',count-failed,count))
if failed>0 then os.exit(1) end
