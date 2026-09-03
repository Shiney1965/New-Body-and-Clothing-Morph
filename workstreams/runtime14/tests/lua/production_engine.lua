-- Engine-only fixture. Every Ext.Require executes the actual staged Lua module.
-- No Shared, EquipRace, family, targeting, policy, or bootstrap module is mocked.
local F = {}
F.ids = {
    runtime = '20aca985-e3e9-41d7-bf8f-10f2a3c413e4',
    a = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    b = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
    cv = '11111111-1111-4111-8111-111111111111',
    body = '22222222-2222-4222-8222-222222222222',
    er = '71180b76-5752-4a97-b71f-911a69197f58',
    race = '0eb594cb-8820-4be6-a58d-8be7a1a98fba',
    external = '33333333-3333-4333-8333-333333333333',
    sbbf = '672a9c38-ba20-4872-a072-ba7f23f58f06',
    bcb = '74131131-2167-5e3c-a9d1-e6f18cab4ee5',
}
function F.Boot(root, options)
    options = options or {}
    local ids = F.ids
    local world = { modules = {}, entities = {}, resources = {}, statics = {},
        reads = {}, writes = {}, logs = {}, warnings = {}, events = {}, listeners = {},
        console = {}, timers = {}, nativeAdds = {}, broadcasts = {}, mcmWrites = {}, mcm = {}, loaded = {} }
    local function read(kind, key)
        world.reads[#world.reads+1] = {kind,key}
        if options.onRead then options.onRead(world,kind,key) end
    end
    local function write(kind, key, value)
        world.writes[#world.writes+1] = {kind,key,value}
        if options.onWrite then options.onWrite(world,kind,key,value) end
    end
    local function event(name)
        world.events[name] = {}
        return {Subscribe=function(_,fn) table.insert(world.events[name],fn) end}
    end
    local function tracked(fields,kind,guid)
        return setmetatable({}, {__index=fields,__newindex=function(_,key,value)
            write(kind..'.'..key,guid,value)
            if not (options.visualWriteNoop and kind=='CCA' and key=='Visuals') then fields[key]=value end
        end})
    end
    function world.fire(name, ...)
        for _, fn in ipairs(world.events[name] or {}) do fn(...) end
        for _, fn in ipairs(world.listeners[name] or {}) do fn(...) end
    end
    function world.resetSpies() world.reads={}; world.writes={} end
    function world.flushTimers()
        local timers=world.timers; world.timers={}
        for _,fn in ipairs(timers) do fn() end
    end
    -- The original live probe observed native additions becoming readable only
    -- after the command tick. Native engine work is not an Ext.Timer callback
    -- and cannot be cancelled by Runtime's delayed-callback gate.
    function world.flushNativeAdds()
        local pending=world.nativeAdds;world.nativeAdds={}
        for _,fn in ipairs(pending) do fn() end
    end
    function world.addCharacter(guid,cv,user,race,er)
        local entity = {Guid=guid, UserReservedFor={UserID=user or 1},
            ClientControl = {}, CharacterCreationStats={Race=race or ids.race,BodyType=1,BodyShape=0},
            CharacterCreationAppearance=tracked({Visuals={ids.external}},'CCA',guid),
            ServerCharacter={Template=tracked({CharacterVisualResourceID=cv or ids.cv,EquipmentRace=er or ids.er},'Template',guid)}}
        function entity:Replicate(component) write('Replicate',guid,component) end
        world.entities[guid]=entity
        return entity
    end
    world.addCharacter(ids.a,ids.cv,1)
    world.addCharacter(ids.b,options.sharedCv and ids.cv or '66666666-6666-4666-8666-666666666666',0x10001)
    world.resources[ids.cv]={VisualSet=tracked({BodySetVisual=options.currentBody or ids.body},'CV',ids.a)}
    world.resources['66666666-6666-4666-8666-666666666666']={VisualSet=tracked({BodySetVisual=ids.body},'CV',ids.b)}
    world.resources[ids.body]={SourceFile='Generated/Public/Shared/original.GR2'}
    world.resources[ids.sbbf]={SourceFile='Generated/Public/ClothMorphRuntime/sbbf.GR2'}
    world.resources[ids.bcb]={SourceFile='Generated/Public/ClothMorphRuntime/bcb.GR2'}
    world.resources['3bc12bd9-6c5e-5067-a20f-b17e45647a10']={SourceFile='Generated/Public/ClothMorphRuntime/vanilla.GR2'}
    world.statics['a22009cd-b9e9-55b1-8295-f89a0ede1bf6']={VisualResource=ids.sbbf}
    world.statics['fe01f8f7-814e-5c2e-9829-a0467fd5a6ce']={VisualResource=ids.bcb}
    world.loaded[ids.runtime]=true
    local env=setmetatable({}, {__index=_G}); env._G=env
    -- BG3SE's Mods entry is the module environment: global registration hooks
    -- and explicit MOD assignments are the same public table.
    env.Mods={ClothMorphRuntime=env}
    env.ModuleUUID=ids.runtime
    env.PersistentVars=options.state or {Version=6,Bodies={[ids.a]={Choice='sbbf',CvGuid=ids.cv,
        OrigBodySetVisual=ids.body,OrigEquipRace=ids.er}},OptoutTemplates={},BodyTattooPolicy='match'}
    local channel={}
    function channel:SetHandler(fn) self.handler=fn end
    function channel:SetRequestHandler(fn) self.requestHandler=fn end
    function channel:Broadcast(data) table.insert(world.broadcasts,data) end
    function channel:SendToServer(data) table.insert(world.broadcasts,data) end
    world.channel=channel
    env.MCM={Get=function(id) return world.mcm[id] end,
        Set=function(id,value,_,notify) world.mcmWrites[#world.mcmWrites+1]={id,value,notify};world.mcm[id]=value end,
        Keybinding={SetCallback=function(id,fn) world.console[id]=fn end}}
    env.Osi={GetHostCharacter=function() return ids.a end,
        IsPartyMember=function(guid) read('IsPartyMember',guid);return world.entities[guid] and 1 or 0 end,
        GetEquippedItem=function(guid,slot) read('GetEquippedItem',guid); return world.equipped and world.equipped[guid] and world.equipped[guid][slot] end,
        Unequip=function(guid,item)
            write('Unequip',guid,item)
            if options.simulateInventory then
                world.inventory=world.inventory or {};world.itemSlots=world.itemSlots or {}
                for slot,value in pairs(world.equipped and world.equipped[guid] or {}) do
                    if value==item then
                        world.itemSlots[item]=slot;world.equipped[guid][slot]=nil;world.inventory[item]=guid
                    end
                end
            end
        end,
        Equip=function(guid,item)
            write('Equip',guid,item)
            if options.simulateInventory and world.inventory and world.inventory[item]==guid then
                world.equipped[guid][world.itemSlots[item]]=item;world.inventory[item]=nil
            end
        end,
        AddCustomVisualOverride=function(guid,ccsv)
            write('AddCustomVisualOverride',guid,ccsv)
            if options.addNoop then return end
            world.nativeAdds[#world.nativeAdds+1]=function()
                local list=assert(world.entities[guid]).CharacterCreationAppearance.Visuals
                list[#list+1]=ccsv
            end
        end}
    env.Ext={Utils={Print=function(s) table.insert(world.logs,s) end,PrintWarning=function(s) table.insert(world.warnings,s) end,
        MonotonicTime=function() return 10000 end},
        Entity={Get=function(guid) read('Entity',guid);return world.entities[guid] end,
            GetAllEntitiesWithComponent=function() read('Entities','ClientControl');return {world.entities[ids.a]} end},
        Resource={Get=function(guid,kind) read(kind,guid);return world.resources[guid] end},
        StaticData={Get=function(guid,kind) read(kind,guid);return world.statics[guid] end,GetAll=function(kind) read('StaticAll',kind);return {} end},
        Template={GetAllRootTemplates=function() read('Templates','all');return world.templates or {} end},
        Mod={GetLoadOrder=function() local a={};for id in pairs(world.loaded) do a[#a+1]=id end;table.sort(a);return a end,
            GetMod=function(id) if world.loaded[id] then return {Info={ModuleUUID=id,ModVersion={Major=1,Minor=0,Revision=0,Build=0}}} end end,
            IsModLoaded=function(id) return world.loaded[id]==true end},
        Net={CreateChannel=function() return channel end},
        Osiris={RegisterListener=function(name,_,_,fn) world.listeners[name]=world.listeners[name] or {};table.insert(world.listeners[name],fn) end},
        Events={SessionLoaded=event('SessionLoaded')},
        ModEvents={BG3MCM={MCM_Setting_Saved=event('MCM_Setting_Saved')}},
        Timer={WaitFor=function(_,fn) world.timers[#world.timers+1]=fn end},
        RegisterConsoleCommand=function(name,fn) world.console[name]=fn end,
        Json={Stringify=function() return '<fixture diagnostic serialization>' end}}
    env.Ext.Require=function(name)
        if world.modules[name]==nil then
            world.modules[name]=assert(loadfile(root..'/Mods/ClothMorphRuntime/ScriptExtender/Lua/'..name,'t',env))()
        end
        return world.modules[name]
    end
    if options.client then env.Osi=nil end
    local bootstrap=options.client and 'BootstrapClient.lua' or 'BootstrapServer.lua'
    assert(loadfile(root..'/Mods/ClothMorphRuntime/ScriptExtender/Lua/'..bootstrap,'t',env))()
    world.env=env;world.mod=env.Mods.ClothMorphRuntime;world.state=env.PersistentVars
    return world
end
return F
