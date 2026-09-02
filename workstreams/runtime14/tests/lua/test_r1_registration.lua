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
    w.mod.SetMasterEnabled(true,'test-server')
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
local failed=0
for _,row in ipairs(tests) do local ok,why=pcall(row[2]);if ok then print('PASS '..row[1]) else failed=failed+1;print('FAIL '..row[1]..' '..tostring(why)) end end
print(('R1_REGISTRATION_RESULT %d/%d'):format(#tests-failed,#tests))
if failed>0 then os.exit(1) end
