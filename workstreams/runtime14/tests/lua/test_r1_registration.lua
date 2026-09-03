local script=debug.getinfo(1,'S').source:sub(2):gsub('\\','/')
local dir=script:match('^(.*)/[^/]+$')
local F=dofile(dir..'/production_engine.lua')
local root=assert(arg[1],'explicit Runtime stage required')
local tests={}
local function test(name,fn) tests[#tests+1]={name,fn} end
local OWNER='b57bab2c-5679-5445-8fee-ca8c282990a5'
local function family(w)
    local profiles={
        vanilla={ccsv='f7315508-9afd-522a-867b-96213cc6443e',visual='bfec2869-70cf-51a7-9806-1bbf02ff1bbe',equipmentRace='0f09bfaa-52b2-5ad5-a489-545cdd1a6ce7'},
        sbbf={ccsv='294df7c6-c8d7-529d-9bcc-4122c0182cf3',visual='ed2d8876-26c8-5844-827f-def771068f63',equipmentRace='c4ab884e-1184-5bd7-b67e-ee3a28a883fd'},
        bcb={ccsv='eca05d33-9887-5d5e-868a-8be722c2eb12',visual='eab8e30e-0207-58d8-8764-e3b4477133fa',equipmentRace='e1371ee6-3c97-544b-b644-e3033021d187',requiredModUuid='1d24059d-ff23-4a79-8892-57c85d512416'},
    }
    w.loaded[OWNER]=true
    for _,profile in pairs(profiles) do
        w.resources[profile.visual]={SourceFile='Generated/Public/ClothMorphTieflingBT1Test/body.GR2'}
        w.statics[profile.ccsv]={VisualResource=profile.visual}
    end
    return {moduleUuid=OWNER,familyId='tif_f_bt1',sourceEquipRace='cf421f4e-107b-4ae6-86aa-090419c624a5',bodyType=1,bodyShape=0,profiles=profiles}
end
test('legacy body and family refits both queue while master off without active maps',function()
    local w=F.Boot(root);local spec=family(w)
    w.mod.SetMasterEnabled(false,'test-server');w.resetSpies()
    local bodyOk,bodyStatus=w.mod.RegisterBodyFamily('fixture-family',spec)
    assert(bodyOk==true and bodyStatus=='QUEUED_MASTER_OFF','body metadata was dropped rather than queued')
    local refitOk,refitStatus=w.mod.RegisterFamilyRefits('fixture-family','tif_f_bt1',{vanilla={},sbbf={},bcb={}},{})
    assert(refitOk==true and refitStatus=='QUEUED_MASTER_OFF','family refits were dropped rather than queued')
    assert(w.modules['BodyFamilyRegistry.lua'].GetProvider('tif_f_bt1')==nil,'queued family activated early')
    assert(#w.writes==0,'queued registration wrote gameplay')
    local snapshot=w.mod.GetProviderRegistrySnapshot()
    assert(#snapshot.descriptors>=2,'queued body/refit descriptor evidence missing')
    local enabled,summary=w.mod.SetMasterEnabled(true,'test-server')
    assert(enabled and #summary.providerActivationResults==2,'queued activation results lost')
    assert(w.modules['BodyFamilyRegistry.lua'].GetProvider('tif_f_bt1')~=nil,'queued family did not activate')
end)
test('revealing metadata queues rather than silently dropping while off',function()
    local w=F.Boot(root);w.mod.SetMasterEnabled(false,'test-server');w.resetSpies()
    local ok,status=w.mod.RegisterExternalRevealing({F.ids.external})
    assert(ok==true and status=='QUEUED_MASTER_OFF','revealing queue missing')
    assert(#w.writes==0,'queued revealing mutated gameplay')
    local snapshot=w.mod.GetProviderRegistrySnapshot()
    local found=false;for _,row in ipairs(snapshot.descriptors) do if row.kind=='revealing' and row.activationState=='queued' then found=true end end
    assert(found,'revealing descriptor evidence missing')
end)
test('cleanup states reject legacy family registration and never queue',function()
    local w=F.Boot(root);local spec=family(w)
    w.state.CleanupState='disable_requested';w.state.MutationGateClosed=true
    local ok,status=w.mod.RegisterBodyFamily('fixture-family',spec)
    assert(ok==false and status=='REJECTED_CLEANUP_DISABLED','wrong cleanup result')
    assert(next(w.state.ProviderDescriptors)==nil,'cleanup registration queued')
end)
test('genuine accepted bootstrap can submit both queued halves without changing API version',function()
    local w=F.Boot(root);family(w)
    for _,id in ipairs({'6cc531d9-a288-50ba-a891-c1917e7d818a','7dfb06bf-e196-575d-b96c-0b39a92a57e8',
        'd40c4b38-6ccb-52ef-a86b-73da0951f27a','c2e59b63-4efd-5645-8bf1-113488f9fec2',
        '88774d3f-4436-51e9-8f9f-c64cb3a45cd9','c86d4c8d-0dfa-5c12-bc8c-9d4fdef816e2'}) do w.resources[id]={SourceFile='Generated/Public/ClothMorphTieflingBT1Test/garment.GR2'} end
    w.mod.SetMasterEnabled(false,'test-server')
    assert(loadfile(dir..'/../../runtime/r0_reference/accepted_tiefling_bootstrap.lua','t',w.env))()
    w.fire('SessionLoaded')
    local queued=0;for _,row in ipairs(w.mod.GetProviderRegistrySnapshot().descriptors) do if row.activationState=='queued' then queued=queued+1 end end
    assert(queued>=2,'genuine provider could not submit both queued stages')
    assert(w.mod.BodyFamilyApiVersion==1,'legacy API changed')
    assert(w.modules['BodyFamilyRegistry.lua'].GetProvider('tif_f_bt1')==nil,'genuine queued provider activated')
end)
test('queued family activates before its configured Tiefling character resumes',function()
    local w=F.Boot(root);local spec=family(w)
    w.loaded['1d24059d-ff23-4a79-8892-57c85d512416']=true
    local entity=w.entities[F.ids.a];entity.CharacterCreationStats.Race='b6dccbed-30f3-424b-a181-c4540cf38197'
    entity.ServerCharacter.Template.EquipmentRace=spec.sourceEquipRace
    local rec=w.state.Bodies[F.ids.a];rec.OrigEquipRace=spec.sourceEquipRace;rec.FamilyOrigEquipRace=spec.sourceEquipRace;rec.Choice='bcb';rec.PreferredChoice='bcb'
    w.mod.SetMasterEnabled(false,'test-server')
    assert(w.mod.RegisterBodyFamily('fixture-family',spec))
    assert(w.mod.RegisterFamilyRefits('fixture-family','tif_f_bt1',{vanilla={},sbbf={},bcb={}},{}) )
    w.mod.SetMasterEnabled(true,'test-server')
    assert(rec.Choice=='bcb' and rec.RestoreState=='clean','queued provider character did not resume')
    assert(w.resources[F.ids.cv].VisualSet.BodySetVisual==spec.profiles.bcb.visual,'wrong resumed family body')
end)
test('changed environment rejects queued body without partial family activation',function()
    local w=F.Boot(root);local spec=family(w);w.mod.SetMasterEnabled(false,'test-server')
    assert(w.mod.RegisterBodyFamily('fixture-family',spec))
    assert(w.mod.RegisterFamilyRefits('fixture-family','tif_f_bt1',{vanilla={},sbbf={},bcb={}},{}) )
    w.loaded[OWNER]=nil
    w.mod.SetMasterEnabled(true,'test-server')
    assert(w.modules['BodyFamilyRegistry.lua'].GetProvider('tif_f_bt1')==nil,'unloaded provider activated')
    for _,row in ipairs(w.mod.GetProviderRegistrySnapshot().descriptors) do assert(row.activationState~='active','partial active descriptor') end
end)
test('queued descriptor is detached from caller and snapshots are immutable',function()
    local w=F.Boot(root);local spec=family(w);w.mod.SetMasterEnabled(false,'test-server')
    assert(w.mod.RegisterBodyFamily('fixture-family',spec))
    local ok,status=w.mod.RegisterBodyFamily('fixture-family',spec)
    assert(ok and status=='IDEMPOTENT','duplicate queue not idempotent')
    local original=w.mod.GetProviderRegistrySnapshot().descriptors[1].canonicalDigest
    spec.profiles.bcb.visual=F.ids.external
    local snapshot=w.mod.GetProviderRegistrySnapshot();snapshot.descriptors[1].bodyCcsvs[1]=F.ids.external
    assert(w.mod.GetProviderRegistrySnapshot().descriptors[1].canonicalDigest==original,'caller changed stored descriptor')
    assert(w.mod.GetProviderRegistrySnapshot().descriptors[1].bodyCcsvs[1]~='33333333-3333-4333-8333-333333333333','snapshot leaked mutable resource list')
end)
test('persisted ACTIVE metadata is not proof of process-local body/refit activation after restart',function()
    local function clone(value)
        if type(value)~='table' then return value end
        local out={};for k,v in pairs(value) do out[k]=clone(v) end;return out
    end
    local w=F.Boot(root);local spec=family(w)
    assert(w.mod.RegisterBodyFamily('fixture-family',spec))
    assert(w.mod.RegisterFamilyRefits('fixture-family','tif_f_bt1',{vanilla={},sbbf={},bcb={}},{}) )
    local restarted=F.Boot(root,{state=clone(w.state)});local freshSpec=family(restarted)
    local ok,status=restarted.mod.RegisterBodyFamily('fixture-family',freshSpec)
    assert(ok and status=='ACTIVE','persisted descriptor falsely treated as process activation')
    assert(restarted.mod.RegisterFamilyRefits('fixture-family','tif_f_bt1',{vanilla={},sbbf={},bcb={}},{}) )
    assert(restarted.modules['BodyFamilyRegistry.lua'].GetProvider('tif_f_bt1')~=nil,'restarted family registry remains empty')
end)
test('same-process empty save reattaches exact active descriptors without gameplay writes',function()
    local w=F.Boot(root);local spec=family(w)
    assert(w.mod.RegisterBodyFamily('fixture-family',spec))
    assert(w.mod.RegisterFamilyRefits('fixture-family','tif_f_bt1',{vanilla={},sbbf={},bcb={}},{}) )
    local newState={Version=7,MasterEnabled=false,MutationGateClosed=true,MasterState='off_restored',
        PassThroughRestoreComplete=true,CleanupState='idle',Bodies={},OptoutTemplates={},ProviderDescriptors={},BodyTattooPolicy='always_hide'}
    w.env.PersistentVars=newState;w.resetSpies()
    local snapshot=w.mod.GetProviderRegistrySnapshot()
    assert(#snapshot.descriptors==2,'active process descriptors lost on cross-save')
    assert(newState.MasterEnabled==false and newState.BodyTattooPolicy=='always_hide' and next(newState.Bodies)==nil,'cross-save ownership/preferences overwritten')
    assert(#w.writes==0,'reattachment wrote gameplay')
end)
test('cross-save conflicting descriptor is preserved and requires restart before writes',function()
    local function clone(value) if type(value)~='table' then return value end;local out={};for k,v in pairs(value) do out[k]=clone(v) end;return out end
    local w=F.Boot(root);local spec=family(w)
    assert(w.mod.RegisterBodyFamily('fixture-family',spec))
    assert(w.mod.RegisterFamilyRefits('fixture-family','tif_f_bt1',{vanilla={},sbbf={},bcb={}},{}) )
    local state=clone(w.state)
    local changed=state.ProviderDescriptors['legacy.body.tif_f_bt1']
    changed.ownerModuleUuid='ffffffff-ffff-4fff-8fff-ffffffffffff';changed.canonicalDigest=string.rep('F',64)
    w.env.PersistentVars=state;w.resetSpies()
    local snapshot=w.mod.GetProviderRegistrySnapshot()
    assert(snapshot.restartRequired==true,'conflicting process maps were silently reused')
    assert(changed.ownerModuleUuid=='ffffffff-ffff-4fff-8fff-ffffffffffff' and changed.canonicalDigest==string.rep('F',64),'saved conflict overwritten')
    assert(w.mod.SetDesiredBody(F.ids.a,'bcb')==false,'conflicting profile mutated character')
    assert(#w.writes==0 and state.MasterEnabled==true,'conflict changed gameplay or save master preference')
end)
test('accepted provider-managed body cannot be captured as a new original',function()
    local w=F.Boot(root);local spec=family(w)
    w.loaded['1d24059d-ff23-4a79-8892-57c85d512416']=true
    assert(w.mod.RegisterBodyFamily('fixture-family',spec))
    assert(w.mod.RegisterFamilyRefits('fixture-family','tif_f_bt1',{vanilla={},sbbf={},bcb={}},{}) )
    local entity=w.entities[F.ids.a];entity.CharacterCreationStats.Race='b6dccbed-30f3-424b-a181-c4540cf38197'
    entity.ServerCharacter.Template.EquipmentRace=spec.sourceEquipRace
    local rec=w.state.Bodies[F.ids.a];rec.Choice='external';rec.OrigBodySetVisual=nil;rec.OrigEquipRace=spec.sourceEquipRace
    w.resources[F.ids.cv].VisualSet.BodySetVisual=spec.profiles.bcb.visual
    w.resetSpies()
    assert(w.mod.SetDesiredBody(F.ids.a,'bcb')==false,'provider target captured as original')
    assert(rec.OrigBodySetVisual==nil and #w.writes==0,'untrusted original mutated state/gameplay')
end)
local failed=0
for _,row in ipairs(tests) do local ok,why=pcall(row[2]);if ok then print('PASS '..row[1]) else failed=failed+1;print('FAIL '..row[1]..' '..tostring(why)) end end
print(('R1_REGISTRATION_RESULT %d/%d'):format(#tests-failed,#tests))
if failed>0 then os.exit(1) end
