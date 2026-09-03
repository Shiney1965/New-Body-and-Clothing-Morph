local script=debug.getinfo(1,'S').source:sub(2):gsub('\\','/')
local dir=script:match('^(.*)/[^/]+$')
local F=dofile(dir..'/production_engine.lua')
local root=assert(arg[1],'explicit Runtime stage required')
local tests={}
local function test(name,fn) tests[#tests+1]={name,fn} end
local SOURCE='096665c7-75aa-4747-9548-6ccafba985c8'
local function maps() return {vanilla={},sbbf={[F.ids.external]=F.ids.sbbf},bcb={}} end
test('legacy external hook returns boolean and does not mislabel source module as owner',function()
    local w=F.Boot(root);w.loaded[SOURCE]=true
    local ok,status=w.mod.RegisterExternalRefits('fixture',maps(),{sourceModUuid=SOURCE,credit='fixture credit'})
    assert(ok==true and status=='ACTIVE','legacy boolean contract broken')
    local descriptor=w.mod.GetProviderRegistrySnapshot().descriptors[1]
    assert(descriptor.ownerModuleUuid=='' and descriptor.ownerUnresolved==true,'source or Runtime UUID was invented as owner')
    descriptor.ownerUnresolved=false
    assert(w.mod.GetProviderRegistrySnapshot().descriptors[1].ownerUnresolved==true,'unknown-owner snapshot not detached')
end)
test('queued legacy source dependency is revalidated before activation',function()
    local w=F.Boot(root);w.loaded[SOURCE]=true;w.mod.SetMasterEnabled(false,'test-server')
    local ok,status=w.mod.RegisterExternalRefits('fixture',maps(),{sourceModUuid=SOURCE,sourceModVersion='36028797018963968',credit='fixture credit'})
    assert(ok==true and status=='QUEUED_MASTER_OFF','legacy queue failed')
    w.loaded[SOURCE]=nil;w.mod.SetMasterEnabled(true,'test-server')
    assert(w.modules['EquipRace.lua'].REFIT_BY_VR.sbbf[F.ids.external]==nil,'source-less queued map activated')
    local attempts=w.mod.GetProviderRegistrySnapshot().rejectedAttempts
    assert(#attempts>0 and attempts[#attempts].ownerUnresolved==true,'rejected unknown ownership evidence lost')
end)
test('unknown legacy owner cannot establish provider CCSV ownership',function()
    local w=F.Boot(root);w.loaded[SOURCE]=true
    local ok=w.mod.RegisterExternalRefits('unknown-body',maps(),{sourceModUuid=SOURCE,bodyCcsvs={'a22009cd-b9e9-55b1-8295-f89a0ede1bf6'}})
    assert(ok==false,'unproven provider body ownership admitted')
end)
test('genuine Recluse caller sees true after successful real registration',function()
    local w=F.Boot(root)
    w.loaded[SOURCE]=true;w.loaded['873d1b73-6adf-4f0c-9e8f-51a78fc3d9c5']=true
    local providerRoot=dir..'/../../runtime/r0_reference/recluse'
    local resourceMaps=assert(loadfile(providerRoot..'/RefitMaps.lua'))().SINDAE_RECLUSE_REFIT_BY_VR
    for _,mapping in pairs(resourceMaps) do for _,target in pairs(mapping) do w.resources[target]={SourceFile='Generated/Public/Recluse/fixture.GR2'} end end
    local providerExt={};for key,value in pairs(w.env.Ext) do providerExt[key]=value end
    local env=setmetatable({Ext=providerExt,Mods=w.env.Mods},{__index=_G})
    providerExt.Require=function(name) return assert(loadfile(providerRoot..'/'..name,'t',env))() end
    assert(loadfile(providerRoot..'/BootstrapServer.lua','t',env))()
    w.fire('SessionLoaded')
    local logged=false
    for _,line in ipairs(w.logs) do if line:find('registered 4 exact Recluse Wave 2 refit routes',1,true) then logged=true end end
    assert(logged,'genuine boolean-only caller falsely reported rejection')
end)
test('reported legacy digest can be supplied for idempotent verification without self-reference',function()
    local w=F.Boot(root)
    local info={ownerModuleUuid=F.ids.runtime,providerId='fixture.digest'}
    assert(w.mod.RegisterExternalRefits('digest',maps(),info))
    info.canonicalDigest=w.mod.GetProviderRegistrySnapshot().descriptors[1].canonicalDigest
    local ok,status=w.mod.RegisterExternalRefits('digest',maps(),info)
    assert(ok==true and status=='IDEMPOTENT','digest verification hashed its own assertion')
end)
test('explicit legacy owner must actually be loaded before activation',function()
    local w=F.Boot(root)
    local ok=w.mod.RegisterExternalRefits('missing-owner',maps(),{ownerModuleUuid='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'})
    assert(ok==false,'unloaded explicit owner activated maps')
    assert(w.modules['EquipRace.lua'].REFIT_BY_VR.sbbf[F.ids.external]==nil)
end)
local failed=0
for _,row in ipairs(tests) do local ok,why=pcall(row[2]);if ok then print('PASS '..row[1]) else failed=failed+1;print('FAIL '..row[1]..' '..tostring(why)) end end
print(('R1_EXTERNAL_LEGACY_RESULT %d/%d'):format(#tests-failed,#tests))
if failed>0 then os.exit(1) end
