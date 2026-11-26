local p = {}
local records = require('Module:TD2资料记录')
local function esc(v) return tostring(v or ''):gsub('&','&amp;'):gsub('<','&lt;'):gsub('>','&gt;'):gsub('"','&quot;') end
local function num(v)
    if v == nil then return '' end
    local s = string.format('%.2f',v):gsub('0+$',''):gsub('%.$','')
    local integer, fraction = s:match('^(%-?%d+)(.*)$')
    local reversed = integer:reverse():gsub('(%d%d%d)','%1,'):reverse():gsub('^,','')
    return reversed .. fraction
end
local groupIcons = {AssaultRifle='ammo_ar', Rifle='ammo_rifle', SniperRifle='ammo_marksman', SubMachinegun='ammo_smg', LightMachinegun='ammo_lmg', Shotgun='ammo_shotgun', Pistol='ammo_pistol'}
local signatureIcons = {
    ['5D4179F15AB8BE5E000525BA4972A14E']='ammo_signature_gl',
    ['544DB9085D8B8C81000459B0CDBF54B1']='ammo_signature_flamethrower',
    ['346395BC5CC2B99600036014FF5641E9']='ammo_signature_gunner',
    ['5D4179F15AFD2E67005F48A5D47C660F']='ammo_signature_marksman',
    ['5D4179F15ABB46D3000066CD81115529']='ammo_signature_crossbow',
    ['346395BC5D0A379900038CEFACEF046A']='ammo_signature_technician',
}
local slots = {OpticsSocket='光学仪器导轨',MagazineSocket='弹匣槽位',UnderbarrelSocket='下枪管槽位',MuzzleSocket='枪口槽位',WeaponSkin='皮肤槽位'}
local function section(title,body,level)
    if body == '' then return '' end
    local h = level or 2
    if h==2 then return '<h2><span class="mw-headline">'..title..'</span></h2><div class="td2-weapon-section">'..body..'</div>' end
    return '<div class="td2-weapon-section"><div class="td2-talent-section-title" role="heading" aria-level="'..h..'">'..title..'</div>'..body..'</div>'
end
local function metric(label,value,unit,integer,decimals,named)
    if value == nil then return '' end
    local display=type(value)=='string' and value or decimals and string.format('%.'..decimals..'f',value) or num(integer and math.floor(value) or value)
    return '<div class="td2-weapon-stat"><dt>'..label..'</dt><dd'..(named and ' class="td2-text-gold"' or '')..'>'..display..(unit or '')..'</dd></div>'
end
local function stats(r,base)
    local s=r.stats
    local function changed(key)
        -- Compare native weapon parameters through myBaseWeapon. Fixed talent
        -- and attachment bonuses are not named-variant parameter overrides.
        return r.kind=='named' and r.base_uid==base['装备UID'] and s[key]~=nil and base.stats[key]~=nil and s[key]~=base.stats[key]
    end
    local function outputValue(value,step)
        if value and s.damage_precision then
            return '约 '..num(math.floor(value/step+0.5)*step)
        end
        return value
    end
    local damage=outputValue(s.damage_ui or s.damage_with_mods or s.base_damage,s.damage_precision)
    local damageLabel=r.kind=='signature' and '面板基础伤害' or s.default_damage_pending and '基础伤害' or '伤害'
    local out={metric(damageLabel,damage,nil,true,nil,changed('damage_max')),metric('每分钟射速',s.rpm_with_mods or s.rpm,nil,true,nil,changed('rpm')),metric(s.reload_unnecessary and '标称弹匣' or '弹匣',s.magazine_with_mods or s.magazine,nil,true,nil,changed('magazine'))}
    if s.base_explosion_damage then out[#out+1]=metric('基础爆炸伤害',s.base_explosion_damage,nil,true) end
    local cycle=s.fire_cycle or {}
    local dpsLabel=cycle.mode=='charged' and '满蓄力 DPS' or cycle.mode=='burst' and '连发 DPS' or cycle.mode=='binary' and '双发 DPS' or 'DPS'
    if r.kind=='signature' then dpsLabel='基础 DPS' end
    local dpsStep=s.damage_precision and s.damage_precision*10
    local dps=outputValue(s.dps,dpsStep)
    if not dps and s.dps_range then
        local function endpoint(v) return num(dpsStep and math.floor(v/dpsStep+0.5)*dpsStep or math.floor(v)) end
        dps=(dpsStep and '约 ' or '')..endpoint(s.dps_range[1])..'–'..endpoint(s.dps_range[2])
    elseif not dps and r.kind~='signature' and not s.fire_cycle and s.base_damage and s.base_rpm then
        -- The previous published mapping supplied these two inputs instead of a projected DPS.
        dps=s.base_damage*s.base_rpm/60
    end
    out[#out+1]=metric(dpsLabel,dps,nil,true)
    if (cycle.period_ms or cycle.period_range_ms) and (cycle.mode=='burst' or cycle.mode=='binary') then
        out[#out+1]=metric('每轮发数',cycle.rounds)
        local range=cycle.period_range_ms
        out[#out+1]=metric(cycle.mode=='binary' and '双发周期' or '连发周期',range and (num(range[1])..'–'..num(range[2])) or cycle.period_ms,' 毫秒')
    elseif cycle.period_ms and cycle.mode=='charged' then
        out[#out+1]=metric('满蓄力周期',cycle.period_ms,' 毫秒')
    end
    out[#out+1]=metric('爆头伤害',s.headshot,'%',false,1)
    out[#out+1]=metric('最优距离',s.optimal_with_mods or s.optimal,nil,true,nil,changed('optimal'))
    local fixed=s.fixed_secondary or {}
    for _,entry in ipairs({{'crit_chance','固定暴击机率','%'},{'crit_damage','固定暴击伤害','%'},{'switch_factor','武器切换速度','×'},{'melee_factor','近战伤害倍率','×'},{'movement_factor','移动速度','×'},{'penetration','子弹穿透值',''}}) do
        local pair=fixed[entry[1]]
        if pair then out[#out+1]=metric(entry[2],pair[2],entry[3]) end
    end
    return '<dl class="td2-weapon-stats">'..table.concat(out)..'</dl>'
end
local function attributes(frame,r,level)
    local core,other={},{}
    for _,a in ipairs(r.attributes or {}) do
        local amount=a.granted or a.maximum
        local value=amount and not a.instance_value_pending and '<strong class="'..(a.named and 'td2-text-gold' or 'td2-text-orange')..'">+'..(a.core and a.unit=='%' and string.format('%.1f',amount) or num(amount))..(a.unit or '')..'</strong> ' or ''
        local icon=frame:expandTemplate{title='TD2图标',args={['类别']=a.id and 'weapon' or 'state',['键']=a.id and (a.core and 'core_attribute' or 'attribute') or 'random'}}
        local line='<div class="td2-equipment-row td2-weapon-attribute">'..icon..'<span class="td2-row-value">'..value..frame:preprocess(a.name)..'</span></div>'
        local target=a.core and core or other;target[#target+1]=line
    end
    local out={}
    if #core>0 then out[#out+1]=section('核心属性',table.concat(core),level) end
    if #other>0 then out[#out+1]=section('属性',table.concat(other),level) end
    return #out>0 and '<div class="td2-weapon-attributes">'..table.concat(out)..'</div>' or ''
end
local function talents(frame,r,effects,args)
    if r.random_talent then
        return '<div class="td2-random-talent">随机武器天赋</div>'
    end
    local parts={}
    for _,mode in ipairs({'PvE','PvP'}) do
        local content={}
        for _,effect in ipairs(effects) do
            if effect['所属装备']==r.stable_id and effect['模式']==mode then
                content[#content+1]='<div id="'..esc(records.anchor(effect))..'">'..records.body(frame,effect,records.note(args,effect))..'</div>'
            end
        end
        if #content>0 then parts[#parts+1]='<div class="td2-brand-panel td2-brand-'..mode:lower()..'">'..table.concat(content)..'</div>' end
    end
    return table.concat(parts)
end
local function controls(frame,r)
    local s=r.stats;local out={}
    local icon=''
    if r['装备UID']=='5D4179F15BD9C83400030DB924AA0FB5' then
        icon=frame:expandTemplate{title='TD2图标',args={['类别']='weapon',['键']='attribute'}}
    end
    for _,v in ipairs({{'准确度','accuracy_compare'},{'稳定度','stability_compare'}}) do
        local value=s[v[2]]
        if value then
            local fill=math.max(0,math.min(100,value))
            out[#out+1]='<div class="td2-weapon-control"><span>'..icon..v[1]..'</span><div class="td2-weapon-bar" role="meter" aria-label="'..v[1]..'" aria-valuemin="0" aria-valuemax="100" aria-valuenow="'..fill..'" aria-valuetext="'..num(value)..'"><span style="width:'..fill..'%"></span></div><div class="td2-weapon-control-value">'..num(value)..'</div></div>'
        end
    end
    local reload=s.reload_ui
    if s.reload_unnecessary then
        out[#out+1]='<dl class="td2-weapon-facts"><div class="td2-weapon-stat"><dt>装弹时间</dt><dd>无需装弹</dd></div></dl>'
    elseif reload and reload>=0 then
        local regular,empty=s.reload_with_mods,s.reload_empty_with_mods
        local adjusted=(regular and regular~=s.reload) or (empty and empty~=s.reload_empty)
        local times=metric('装弹时间',reload/1000,' 秒')
        if adjusted and s.reload_per_round then
            times=metric('整匣装填',reload/1000,' 秒')..metric('逐发装填',regular and regular/1000,' 秒')..metric('空仓首发装填',empty and empty/1000,' 秒')
        elseif adjusted and regular and empty and regular~=empty then
            times=metric('常规装填',regular/1000,' 秒')..metric('空仓装填',empty/1000,' 秒')
        end
        out[#out+1]='<dl class="td2-weapon-facts">'..times..'</dl>'
    end
    return table.concat(out)
end
local function charts(r)
    local uid = r['装备UID']:lower()
    local data = mw.loadData('Module:TD2武器图表/'..r.group)
    -- Older shards also contain launcher charts. Only explicitly supported signature models may render.
    if r.kind == 'signature' and not (data.signatureChartUids and data.signatureChartUids[uid]) then return '' end
    local model = data.models[uid]
    if not model then return '' end
    local showRecoil = r.kind ~= 'signature' or uid == data.signatureRecoilUid
    local trace = showRecoil and model.trace and data.traces[model.trace] or ''
    return '<div class="td2-weapon-charts" id="weapon-charts-'..uid..'" data-name="'..esc(r['装备名称'])..'" data-angles="'..esc(model.angles)..'" data-recoil="'..esc(trace)..'" data-target="'..esc(data.target)..'"><span class="td2-chart-art">[[File:'..data.image..'|512px|link=|alt=]]</span></div>'
end
local function rangePlot(a,b,limit)
    -- Get Range Points uses two fixed HUD levels. A cut through the slope keeps its direction.
    local nearY, farY = 20, 90
    local lines, points, ticks = {}, {}, {}
    local prevX, prevY
    local function vertex(x,y)
        if x==prevX and y==prevY then return end
        if prevX then
            local kind = x==prevX and 'drop' or y==prevY and 'flat' or 'slope'
            local style='inset:auto;left:'..prevX..'%;top:'..prevY..'%;'
            if kind=='drop' then
                style=style..'width:4px;height:'..(y-prevY)..'%;transform:translateX(-50%)'
            elseif kind=='flat' then
                style=style..'width:'..(x-prevX)..'%;height:4px;transform:translateY(-50%)'
            else
                style=style..'width:'..(x-prevX)..'%;height:'..(y-prevY)..'%;background:var(--td2-range-diagonal,linear-gradient(to top right,transparent calc(50% - 2px),#eee calc(50% - 2px),#eee calc(50% + 2px),transparent calc(50% + 2px)))'
            end
            lines[#lines+1]='<span class="td2-weapon-range-line td2-range-'..kind..'" style="'..style..'"></span>'
        end
        points[#points+1]='<span class="td2-corner-node td2-weapon-range-point" style="left:'..x..'%;top:'..y..'%"></span>'
        if x~=prevX then
            local edge=x==0 and ' td2-range-start' or x==100 and ' td2-range-end' or ''
            ticks[#ticks+1]='<span class="td2-weapon-range-mark'..edge..'" style="left:'..x..'%">'..(x==0 and '0' or num(x)..' 米')..'</span>'
        end
        prevX,prevY=x,y
    end
    vertex(0,nearY)
    vertex(math.min(a,100),nearY)
    if a<=100 then
        if b<=100 then
            vertex(b,farY)
            vertex(100,farY)
        else
            vertex(100,nearY+(farY-nearY)*(100-a)/(b-a))
        end
    end
    local description='伤害递减：'..num(a)..' 米开始，'..num(b)..' 米结束'
    if limit then description=description..'，超过 '..num(limit)..' 米普通物理伤害归零' end
    return '<div class="td2-weapon-range-plot" role="img" aria-label="'..description..'">'..
        table.concat(lines)..table.concat(points)..'</div><div class="td2-weapon-range-axis">'..table.concat(ticks)..'</div>'
end
local function range(r)
    local s=r.stats
    local profiles=s.distance_damage or {}
    if not profiles[1] then
        -- The inventory HUD still has O/L for entity projectiles and scripted weapons.
        if not s.optimal or not s.long then return '' end
        return '<div class="td2-weapon-range">'..rangePlot(s.optimal_with_mods or s.optimal,s.long_with_mods or s.long)..'</div>'
    end
    local modes={FullAutoFireEvent='全自动',SemiAutoFireEvent='单发'}
    local out,plots,seen={},{},{}
    for _,p in ipairs(profiles) do
        local value=p.retention==1 and '100%' or string.format('%.2f%%',p.retention*100)
        local key=table.concat({p.optimal,p.long,p.limit,value},'/')
        if not seen[key] then
            plots[#plots+1]={profile=p,value=value}
            seen[key]=true
        end
    end
    local shared=true
    for i=2,#plots do if plots[i].value~=plots[1].value then shared=false end end
    for i,plot in ipairs(plots) do
        local p=plot.profile
        local mode=plots[2] and modes[p.mode]
        if mode and p.mode=='SemiAutoFireEvent' and r['装备UID']=='346395BC5DCE9E040003A0A31ECBAA3A' then mode='开镜单发' end
        local caption=mode and ('<div class="td2-weapon-range-mode">'..mode..'</div>') or ''
        local retention=''
        if not shared or i==#plots then
            retention='<dl class="td2-weapon-facts td2-weapon-range-retention">'..metric('最小伤害比例',plot.value)..'</dl>'
        end
        out[#out+1]='<div class="td2-weapon-range">'..caption..rangePlot(p.optimal,p.long,p.limit)..retention..'</div>'
    end
    return table.concat(out)
end
local function weaponGallery(frame,title,items,level,target)
    if not items or not items[1] then return '' end
    local corners=frame:expandTemplate{title='TD2边框角节点',args={}}
    local link=target and '|link='..target or ''
    local cards={}
    for _,item in ipairs(items) do
        local name=item.name or item['装备名称']
        local art=item.image and '<div class="td2-weapon-skin-art">[[File:'..item.image..'|256px'..link..'|alt='..esc(name)..']]</div>' or ''
        cards[#cards+1]='<li class="td2-weapon-skin-card td2-frame td2-surface">'..corners..art..'<div class="td2-weapon-skin-name">'..frame:preprocess(name)..'</div></li>'
    end
    return section(title,'<ul class="td2-weapon-skins">'..table.concat(cards)..'</ul>',level)
end
local function mods(frame,r,level,entities)
    local out={}
    local icons={OpticsSocket='optics',MagazineSocket='magazine',UnderbarrelSocket='underbarrel',MuzzleSocket='muzzle'}
    for _,socket in ipairs(r.sockets or {}) do
        local values={}
        for _,mod in ipairs(socket.mods or {}) do
            if mod.name then
                local bonuses={}
                for _,b in ipairs(mod.bonuses or {}) do bonuses[#bonuses+1]='<div class="td2-bonus-line"><strong class="td2-text-orange">'..(b.value>0 and '+' or '')..(b.unit=='%' and string.format('%.1f',b.value) or num(b.value))..b.unit..'</strong> '..frame:preprocess(b.name)..'</div>' end
                values[#values+1]=frame:preprocess(mod.name)..table.concat(bonuses)
            end
        end
        local label=socket.name or slots[socket.slot]
        if label and socket.slot~='WeaponSkin' then
            if #values>0 and socket.fixed==false then label=label..'（可更换）' end
            local icon=icons[socket.slot] and frame:expandTemplate{title='TD2图标',args={['类别']='weapon',['键']=icons[socket.slot]}} or ''
            out[#out+1]='<div class="td2-weapon-mod"><div><div>'..esc(label)..'</div><div class="td2-weapon-mod-value">'..(#values>0 and table.concat(values,'<br>') or '空槽位')..'</div></div>'..icon..'</div>'
        end
    end
    local galleryLevel=#out>0 and level+1 or level
    local galleries=weaponGallery(frame,'武器皮肤',r.skins,galleryLevel)
    if r.kind=='exotic' and r.base_uid then
        local uid=r.base_uid:lower()
        local entity=entities['weapon:'..uid]
        local base=entity and entity.weapons[1]
        if base and base.kind=='normal' and base.image then
            local target=frame:expandTemplate{title='TD2页面地址',args={[1]='weapon-page-'..uid}}
            galleries=galleries..weaponGallery(frame,'武器原型',{base},galleryLevel,target)
        end
    end
    if #out==0 then return galleries end
    return section('改造模块',table.concat(out)..galleries,level)
end
local function sources(frame,r,subject,data)
    local headingTag=r.kind=='named' and 'h5' or 'h3'
    local function heading(label)
        return '<'..headingTag..' class="td2-source-heading">'..label..'</'..headingTag..'>'
    end
    local fact=data.acquisition[subject]
    local shared=require('Module:TD2品牌投影')
    local equipment=fact and heading('武器获取')..shared.acquisition({args={source_subject=subject}}) or ''
    if r.kind=='signature' then return equipment end
    local out={};local blueprintRows={}
    local labels={craft='制作图纸',reconfigure='重新配置图纸',conversion='外观转换图纸'}
    for _,purpose in ipairs({'craft','reconfigure','conversion'}) do
        local blueprints={}
        for _,b in ipairs(r.blueprints or {}) do
            if b.purpose==purpose then blueprints[#blueprints+1]=frame:expandTemplate{title='品牌图纸列表',args={['条目']=esc(b.name)}} end
        end
        if #blueprints>0 then
            local list=frame:expandTemplate{title='品牌图纸列表',args={['内容']=table.concat(blueprints)}}
            if r.kind=='exotic' then list='<dt>'..labels[purpose]..'</dt><dd>'..list..'</dd>' end
            blueprintRows[#blueprintRows+1]=list
        end
    end
    if #blueprintRows>0 then
        local list=table.concat(blueprintRows)
        if r.kind=='exotic' then list='<dl class="td2-ordinary-blueprints">'..list..'</dl>' end
        out[#out+1]=heading('武器图纸')..list
    end
    if fact then
        out[#out+1]=heading('图纸获取')..'<div class="td2-acquisition-result">'..shared.blueprintSource({args={source_subject=subject},expandTemplate=function(_,spec)return frame:expandTemplate(spec) end})..'</div>'
        out[#out+1]=equipment
    end
    return table.concat(out,'<div class="td2-divider-soft"></div>')
end
local function expertiseCap(r)
    return r.expertise_max_level or 30
end
local function expertiseKey(r)
    local bonuses={}
    for _,bonus in ipairs(r.expertise or {}) do
        local f=bonus.formula
        bonuses[#bonuses+1]=string.format('%q %q %q %.17g %.17g %.17g',bonus.attribute,bonus.name,bonus.type,f.A,f.B,f.C)
    end
    if #bonuses==0 then return nil end
    table.sort(bonuses)
    return expertiseCap(r)..' '..table.concat(bonuses,'\n')
end
local function hasSharedExpertise(weapons)
    if not weapons[2] then return false end
    local base=expertiseKey(weapons[1])
    if not base then return false end
    for i,r in ipairs(weapons) do
        if i>1 and expertiseKey(r)~=base then return false end
    end
    return true
end
local function expertise(frame,r)
    local out={}
    for _,bonus in ipairs(r.expertise or {}) do
        local f=bonus.formula
        if f.A==0 and f.C==0 and bonus.type=='UpgradeBonusType_Percentage' then
            out[#out+1]='<div class="td2-equipment-row"><span class="td2-row-label">每级加成：</span><span class="td2-row-value"><strong>+'..num(f.B*100)..'%</strong> '..frame:preprocess(bonus.name)..'</span></div>'
        end
    end
    if #out==0 then return '' end
    out[#out+1]='<div class="td2-equipment-row"><span class="td2-row-label">等级上限：</span><span class="td2-row-value">'..expertiseCap(r)..'级</span></div>'
    return '<div class="td2-expertise-card"><div class="td2-talent-detail"><div class="td2-talent-copy">'..table.concat(out)..'</div><div class="td2-talent-icon">'..frame:expandTemplate{title='TD2图标',args={['类别']='state',['键']='proficient'}}..'</div></div></div>'
end
function p.render(frame)
    local args=frame:getParent().args
    local data=mw.loadData('Module:TD2装备映射');local id=args['资料ID'];local entity=data.entities[id]
    if not entity or not entity.weapons then error('武器资料身份未配置') end
    local effects=records.read(frame:preprocess(entity.fields['效果资料']))
    local sharedExpertise=hasSharedExpertise(entity.weapons)
    local out={'<div class="td2-brand td2-weapons" data-brand="'..esc(entity.fields['装备名称'])..'">'}
    for i,r in ipairs(entity.weapons) do
        local named=i>1;local anchor=named and r['装备名称'] or '武器概览'
        local level=named and 4 or 2
        if i==2 then out[#out+1]='<h2><span class="mw-headline">具名武器</span></h2><div class="td2-weapon-named-list">' end
        if i>2 then out[#out+1]='<div class="td2-weapon-named-divider" aria-hidden="true"></div>' end
        out[#out+1]='<div class="td2-brand td2-equipment td2-weapon-unit td2-weapon-'..r.kind..'" id="'..esc(anchor)..'">'
        local art=''
        if r.image then
            local fit=r.art_fit
            art='[[File:'..r.image..'|'..(fit and fit.width or 512)..'px|alt='..esc(r['装备名称'])..']]'
            if fit then
                art='<div class="td2-weapon-art-window" style="--weapon-art-ratio:'..(fit.w/fit.h)..';--weapon-art-width:'..math.min(fit.w*1.5,540)..'px"><div class="td2-weapon-art-image" style="width:'..(100*fit.width/fit.w)..'%;left:'..(-100*fit.x/fit.w)..'%;top:'..(-100*fit.y/fit.h)..'%;">'..art..'</div></div>'
            end
        end
        local quality=(r.kind=='exotic' or r.kind=='signature') and 'exotic' or 'high_end'
        local qualityName=r.kind=='signature' and '特有武器' or r.kind=='exotic' and '奇特' or '顶级'
        local iconKey=r.kind=='signature' and signatureIcons[r.specialization.uid] or groupIcons[r.group]
        local typeIcon=frame:expandTemplate{title='TD2图标',args={['类别']='weapon',['键']=iconKey}}
        out[#out+1]='<div class="td2-brand-top"><div class="td2-brand-name-en" lang="en">'..esc(r['英文原名'])..'</div><div class="td2-brand-bonus-header">'..frame:expandTemplate{title='品牌套装信息框',args={['套装全称']=r['装备名称'],['品质']=quality,['品质名称']=qualityName,['品质图标内容']=typeIcon,['图标内容']=art,['附加类']='td2-weapon-infobox',['章节标题']=named and '是' or '否'}}..'</div></div>'
        if r.description and r.description~='' then out[#out+1]='<p class="td2-equipment-flavor">'..frame:preprocess(r.description):gsub('\n','<br>')..'</p>' end
        local sublevel=named and level or level+1
        local properties=section('核心数值',stats(r,entity.weapons[1]),sublevel)..attributes(frame,r,sublevel)..section('天赋',talents(frame,r,effects,args),sublevel)..section('武器控制力',controls(frame,r)..charts(r),sublevel)..section('伤害递减',range(r),sublevel)..mods(frame,r,sublevel,data.entities)
        out[#out+1]=named and properties or section('武器属性',properties,level)
        out[#out+1]=section('制作与获取',sources(frame,r,named and r.stable_id or id,data),level)
        if not sharedExpertise then out[#out+1]=section('专精',expertise(frame,r),level) end
        out[#out+1]='</div>'
    end
    if entity.weapons[2] then out[#out+1]='</div>' end
    if args['其他机制'] and args['其他机制']~='' then out[#out+1]=section('其他资料',frame:preprocess(args['其他机制']),2) end
    if sharedExpertise then out[#out+1]=section('专精',expertise(frame,entity.weapons[1]),2) end
    out[#out+1]=records.references(frame)
    out[#out+1]=frame:expandTemplate{title='TD2武器导航',args={}}..'</div>'
    return table.concat(out)
end
return p
