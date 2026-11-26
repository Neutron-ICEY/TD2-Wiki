local p = {}
local records = require('Module:TD2资料记录')
local slots = {mask='面具',backpack='背包',chest='胸甲',gloves='手套',holster='枪套',kneepads='护膝'}
local order = {'mask','backpack','chest','gloves','holster','kneepads'}
local function trim(v) return mw.text.trim(tostring(v or '')) end
local function call(frame,title,args) return frame:expandTemplate{title=title,args=args} end
local function escape(v) return tostring(v or ''):gsub('&','&amp;'):gsub('<','&lt;'):gsub('>','&gt;'):gsub('"','&quot;') end
local function anchor(row) return 'td2-gear-' .. row['效果ID']:gsub(':','-') .. '-' .. row['模式']:lower() end
function p.item(frame)
    local args={}
    for _,key in ipairs({'装备部位','装备名称','英文原名','装备UID','核心属性规则','次属性规则','来源说明'}) do args[key]=trim(frame.args[key]) end
    return '<span class="td2-gear-item" data-record="' .. escape(mw.text.jsonEncode(args)) .. '"></span>'
end
function p.effects(frame)
    local output,rows={},records.read(frame.args.effects)
    for _,mode in ipairs({'PvE','PvP'}) do
        local groups,counts={},{}
        for _,row in ipairs(rows) do if row['模式']==mode then
            local count=row['件数']
            if not groups[count] then groups[count]={};counts[#counts+1]=count end
            local body=records.body(frame,row,records.note(frame:getParent().args,row))
            if row['部位']~='' then body='<div class="td2-talent-section-title" role="heading" aria-level="4">' .. slots[row['部位']] .. '天赋</div>' .. body end
            groups[count][#groups[count]+1]='<div id="' .. anchor(row) .. '"' .. (row['部位']~='' and ' class="td2-gear-slot-talent"' or '') .. '>' .. body .. '</div>'
        end end
        table.sort(counts,function(a,b) return tonumber(a)<tonumber(b) end)
        for _,count in ipairs(counts) do output[#output+1]='<div class="td2-gear-effect-group td2-brand-panel td2-brand-' .. mode:lower() .. '"><div class="td2-gear-effect-title" role="heading" aria-level="3">' .. count .. '+ 件</div>' .. table.concat(groups[count]) .. '</div>' end
    end
    return table.concat(output)
end
function p.equipment(frame)
    local groups,output={},{}
    for encoded in tostring(frame.args.equipment or ''):gmatch('<span class="td2%-gear%-item" data%-record="([^"]*)"></span>') do
        local row=mw.text.jsonDecode(mw.text.decode(encoded));local slot=row['装备部位']
        if not slots[slot] then error('装备部位无效') end
        groups[slot]=groups[slot] or {};groups[slot][#groups[slot]+1]=row
    end
    local effects=records.read(frame.args.effects)
    for _,slot in ipairs(order) do if groups[slot] then
        local entity=mw.loadData('Module:TD2装备映射').entities[trim(frame.args.entity)]
        local rule=entity and entity.rules['slot:'..slot]
        if not rule then error('装备部位配置未确认') end
        local minor=rule.minor.count
        local core=require('Module:TD2资料映射').coreValue(frame,rule.core)
        local attributes='<div class="td2-equipment-row">' .. call(frame,'TD2装备行图标',{[1]='major_attribute'}) .. '<span class="td2-row-label">主属性：</span><span class="td2-row-value"><span class="td2-major-value">' .. core .. '</span></span></div>'
        if tonumber(minor)>0 then attributes=attributes .. call(frame,'TD2装备槽行',{['数量']=minor,['标签']='次属性',['图标']='minor_attribute',['状态图标']='random',['内容']='随机加成'}) end
        attributes=attributes .. call(frame,'TD2装备槽行',{['数量']=rule.mods,['标签']='插件槽',['图标']='mod_slot',['状态图标']='gear_mod_slot',['内容']='装备改装槽位',['无槽位内容']='无插件槽位'})
        local links={}
        for _,mode in ipairs({'PvE','PvP'}) do
            local parts={}
            for _,effect in ipairs(effects) do if effect['部位']==slot and effect['模式']==mode and effect['名称']~='' then parts[#parts+1]='<span class="td2-gear-talent-name">' .. call(frame,'TD2图标',{['类别']='talent',['键']=effect['图标']}) .. '[[#' .. anchor(effect) .. '|' .. effect['名称'] .. ']]</span>' end end
            if #parts>0 then links[#links+1]='<span class="td2-gear-talent-links td2-brand-panel td2-brand-' .. mode:lower() .. '">' .. table.concat(parts,' / ') .. '</span>' end
        end
        attributes=attributes .. call(frame,'TD2装备槽行',{['数量']=(slot=='backpack' or slot=='chest') and 1 or 0,['标签']='天赋位',['图标']='talent_slot',['无槽位内容']='无天赋槽位',['内容']=#links>0 and table.concat(links) or '固定专属天赋槽位'})
        local names={}
        for _,row in ipairs(groups[slot]) do
            local notes={};for _,key in ipairs({'核心属性规则','次属性规则','来源说明'}) do if row[key]~='' then notes[#notes+1]=row[key] end end
            names[#names+1]='<li>' .. escape(row['装备名称']) .. (row['英文原名']~='' and '<div class="td2-model-english">' .. escape(row['英文原名']) .. '</div>' or '') .. (#notes>0 and '<details class="td2-gear-notes"><summary>补充资料</summary>' .. table.concat(notes,'<br>') .. '</details>' or '') .. '</li>'
        end
        local label='装备型号 · '..#names
        output[#output+1]='<div class="td2-equipment-card">' .. call(frame,'装备标题卡',{['章节标题']='否',['中文名称']=slots[slot],['英文名称']=slot,['图标键']=slot,['品质']='gear_set'}) .. '<div class="td2-equipment-attributes"><p class="td2-base-armor">基础装甲：' .. call(frame,'TD2普通装备规则',{[1]='armor',['部位']=slot}) .. '</p><div class="td2-divider-soft" aria-hidden="true"></div><div class="td2-attribute-grid">' .. attributes .. '</div></div><div class="td2-models mw-collapsible mw-collapsed" data-expandtext="' .. label .. '" data-collapsetext="' .. label .. '"><div class="mw-collapsible-content"><ul class="td2-equipment-models">' .. table.concat(names) .. '</ul></div></div></div>'
    end end
    return table.concat(output)
end
return p
