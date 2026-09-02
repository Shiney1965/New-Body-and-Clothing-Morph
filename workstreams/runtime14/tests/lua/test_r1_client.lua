local script=debug.getinfo(1,'S').source:sub(2):gsub('\\','/')
local F=dofile(script:match('^(.*)/[^/]+$')..'/production_engine.lua')
local root=assert(arg[1],'explicit composed Runtime root required')
local tests={}
local function test(name,fn) tests[#tests+1]={name,fn} end
test('External hotkey resolves current controlled character at action time',function()
    local w=F.Boot(root,{client=true});w.fire('SessionLoaded')
    assert(type(w.console.key_set_external)=='function','missing External hotkey')
    w.env.Ext.Entity.GetAllEntitiesWithComponent=function() return {w.entities[F.ids.b]} end
    w.console.key_set_external()
    local request=w.broadcasts[#w.broadcasts]
    assert(request.cmd=='setbody' and request.arg=='external' and request.target==F.ids.b,'wrong External request')
end)
test('External feedback renders exact MCM choice only for current client',function()
    local w=F.Boot(root,{client=true})
    w.channel.handler({cmd='cm_applied',char=F.ids.b,choice='external',ok=true})
    assert(#w.mcmWrites==0,'another character changed client MCM')
    w.channel.handler({cmd='cm_applied',char=F.ids.a,choice='external',ok=true})
    assert(w.mcm.body_choice=='External / Pass-through','wrong External label')
    assert(w.mcmWrites[1][3]==false,'feedback must suppress setting event')
end)
test('master status is forwarded as read-only request',function()
    local w=F.Boot(root,{client=true});w.console.cm_master('cm_master','status')
    local request=w.broadcasts[#w.broadcasts]
    assert(request and request.cmd=='master' and request.arg=='status','master status not forwarded')
end)
test('missing controlled target never silently chooses host',function()
    local w=F.Boot(root,{client=true})
    w.env.Ext.Entity.GetAllEntitiesWithComponent=function() return {} end
    w.console.cm_setbody('cm_setbody','bcb')
    assert(#w.broadcasts==0,'missing target forwarded for host fallback')
end)
local failed=0
for _,row in ipairs(tests) do local ok,why=pcall(row[2]);if ok then print('PASS '..row[1]) else failed=failed+1;print('FAIL '..row[1]..' '..tostring(why)) end end
print(('R1_CLIENT_RESULT %d/%d'):format(#tests-failed,#tests))
if failed>0 then os.exit(1) end
