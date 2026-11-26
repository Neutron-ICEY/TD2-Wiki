local p = {}
local function trim(v) return mw.text.trim(tostring(v or '')) end
local function escape(v) return tostring(v or ''):gsub('&','&amp;'):gsub('<','&lt;'):gsub('>','&gt;'):gsub('"','&quot;') end
local function problem() return '<strong class="td2-data-error">奇特装备资料未配置或不合法，请核对属性规则。</strong>' end
local function list(raw)
    local out, seen = {}, {}
    if raw == '' then return out end
    for v in (raw .. ';'):gmatch('(.-);') do
        if v == '' or seen[v] then return nil end
        seen[v] = true; out[#out+1] = v
    end
    return out
end
local function lookup(rows, id)
    for _, r in ipairs(rows) do if r.id == id then return r end end
end
local function call(frame, title, args) return frame:expandTemplate{title=title, args=args} end
local function blueprints(frame, raw, purpose, target, data)
    local ids = list(raw)
    if not ids then return nil end
    local items = {}
    for _, id in ipairs(ids) do
        local row = lookup(data.blueprints or {}, id)
        if not row or row.purpose ~= purpose or row.target_id ~= target then return nil end
        items[#items+1] = call(frame,'品牌图纸列表',{['条目']=escape(row.name),['用途']=purpose == 'craft' and '制作' or '重新配置'})
    end
    local content = call(frame,'品牌图纸列表',{['内容']=table.concat(items),['无图纸文本']=purpose == 'craft' and '无制作图纸' or '无重新配置图纸'})
    return content
end
local fields = {'槽位ID','类型','选择方式','属性规则','候选池','预设百分位','可校准'}
local keys = {'id','kind','choice','rule','pool','percent','calibration'}
function p.slot(frame)
    local a = frame:getParent().args
    local out = {'<span class="td2-exotic-slot"'}
    for i, key in ipairs(keys) do out[#out+1] = ' data-' .. key .. '="' .. escape(trim(a[fields[i]])) .. '"' end
    out[#out+1] = '></span>'
    return table.concat(out)
end
local function validPercentile(value)
    if value == '' then return true end
    if not (value == '-1' or value:match('^-1%.0+$') or value:match('^%d+$') or value:match('^%d+%.%d+$')) then return false end
    local number = tonumber(value)
    return number ~= nil and number == number and number ~= math.huge and number ~= -math.huge
end
local function attributeRow(frame, row, data)
    local core = row.kind == '主属性'
    if not core and row.kind ~= '次属性' then return nil end
    if row.calibration ~= '' and row.calibration ~= '是' and row.calibration ~= '否' and row.calibration ~= '待核实' then return nil end
    if not validPercentile(row.percent) then return nil end
    local value
    if row.choice == '预设' then
        local rule = lookup(data.rules, row.rule)
        if not rule or row.pool ~= '' or core ~= (rule.kind == 'core') then return nil end
        local standard = row.percent == '' or tonumber(row.percent) == -1 or tonumber(row.percent) == 100 or rule.constant or rule.kind == 'named_special'
        if core then
            value = standard and call(frame,'TD2主属性显示',{rule.core_type}) or (call(frame,'TD2图标',{['类别']='state',['键']=rule.core_type}) .. call(frame,'TD2主属性名称',{rule.core_type}))
        else
            value = call(frame,'TD2固定词条图标',{rule.id}) .. (standard and rule.display_max and call(frame,'TD2固定词条片段',{rule.id}) or call(frame,'TD2次属性名称',{rule.attribute_id}))
        end
    elseif row.choice == '随机' then
        local pool = lookup(data.pools,row.pool)
        if not pool or row.rule ~= '' or core ~= (pool.kind == 'core') then return nil end
        local coreTypes, minorCategories = {}, {}
        for _, id in ipairs(pool.rules) do
            local rule = lookup(data.rules,id)
            if not rule or rule.kind ~= pool.kind then return nil end
            if core then coreTypes[#coreTypes+1] = rule.core_type
            else minorCategories[rule.category or 'unknown'] = true end
        end
        local minorCategory = next(minorCategories)
        if core and #coreTypes > 1 then
            value = call(frame,'TD2主属性列表',{table.concat(coreTypes,';')})
        elseif minorCategory and not next(minorCategories,minorCategory) and ({offense=true,defense=true,utility=true})[minorCategory] then
            value = call(frame,'TD2图标',{['类别']='attribute_category',['键']=minorCategory}) .. '随机加成'
        else
            value = call(frame,'TD2图标',{['类别']='state',['键']=core and coreTypes[1] or 'random'}) .. '随机加成'
        end
    else return nil end
    if core then return value end
    return '<div class="td2-equipment-row">' .. call(frame,'TD2装备行图标',{'minor_attribute'}) .. '<span class="td2-row-label">次属性：</span><span class="td2-row-value">' .. value .. '</span></div>'
end
function p.render(frame)
    local a, data = {}, mw.loadData('Module:TD2装备属性数据')
    for k,v in pairs(frame:getParent().args) do a[k]=v end
    local equipment=data.equipment[trim(a['资料ID'])]
    if not equipment then return problem() end
    for k,v in pairs(equipment.fields) do a[k]=frame:preprocess(v) end
    local slots={}
    for _, row in ipairs(equipment.slots) do slots[#slots+1]=call(frame,'奇特装备属性槽',row) end
    a['属性槽']=table.concat(slots)
    local id, slot = trim(a['装备ID']), trim(a['装备部位'])
    if not id:match('^exotic:%x+$') or #id ~= 39 or trim(a['装备名称']) == '' then return problem() end
    if not ({mask=true,backpack=true,chest=true,gloves=true,holster=true,kneepads=true})[slot] then return problem() end
    local raw, rows, seen = trim(a['属性槽']), {}, {}
    local remainder = raw:gsub('<span class="td2%-exotic%-slot"(.-)></span>',function(attrs)
        local row = {}
        for k,v in attrs:gmatch(' data%-([a-z]+)="([^"]*)"') do row[k] = v end
        for _,k in ipairs(keys) do if row[k] == nil then return attrs end end
        if not row.id:match('^[a-z][a-z0-9_]*$') or seen[row.id] then return attrs end
        seen[row.id]=true
        local value = attributeRow(frame,row,data.attributes)
        if not value then return attrs end
        rows[#rows+1] = {kind=row.kind, value=value}
        return ''
    end)
    if trim(remainder) ~= '' or #rows == 0 then return problem() end
    local talents, talentData, records = {},{},require('Module:TD2资料记录')
    for _, row in ipairs(records.read(a['效果资料'])) do
        local talent=lookup(talentData,row['效果ID'])
        if not talent then talent={id=row['效果ID'],modes={}};talentData[#talentData+1]=talent;talents[#talents+1]=talent.id end
        talent.modes[row['模式']]=row
    end
    local count = trim(a['插件槽数'])
    if count ~= '' and (not count:match('^%d+$') or tonumber(count)>250) then return problem() end
    local crafting = blueprints(frame,trim(a['制作图纸']),'craft',id,data)
    local reconfigure = blueprints(frame,trim(a['重新配置图纸']),'reconfigure',id,data)
    if not crafting or not reconfigure then return '<strong class="td2-data-error">奇特装备图纸引用无效，请核对图纸资料。</strong>' end
    local out = {'<div class="td2-brand td2-exotic-gear" data-equipment-version="' .. data.version .. '">'}
    out[#out+1] = '<div class="td2-brand-top">'
    if trim(a['英文原名']) ~= '' then out[#out+1] = '<div class="td2-brand-name-en" lang="en">' .. escape(a['英文原名']) .. '</div>' end
    local identity = {['套装全称']=escape(a['装备名称']),['品质']='exotic',['品质图标']=slot}
    if equipment.inventory_asset then
        local file = call(frame,'TD2资产',{equipment.inventory_asset})
        identity['图标内容'] = '[[File:' .. file .. '|200x144px|alt=' .. identity['套装全称'] .. ']]'
        identity['附加类'] = 'td2-exotic-infobox'
    end
    out[#out+1] = '<div class="td2-brand-bonus-header">' .. call(frame,'品牌套装信息框',identity) .. '</div></div>'
    if trim(a['简介']) ~= '' then out[#out+1] = '<p class="td2-equipment-flavor">' .. escape(a['简介']):gsub('\n','<br>') .. '</p>' end
    local cores, attributes = {}, {}
    for _, row in ipairs(rows) do if row.kind == '主属性' then cores[#cores+1] = row.value end end
    if #cores > 0 then
        attributes[#attributes+1] = call(frame,'TD2装备槽行',{['数量']='1',['标签']='主属性',['图标']='major_attribute',['内容']='<span class="td2-major-value">' .. table.concat(cores,'<br>') .. '</span>'})
    end
    for _, row in ipairs(rows) do if row.kind == '次属性' then attributes[#attributes+1] = row.value end end
    attributes[#attributes+1] = call(frame,'TD2装备槽行',{['数量']=count,['标签']='插件槽',['图标']='mod_slot',['状态图标']='gear_mod_slot',['无槽位内容']='无插件槽位',['内容']='装备改装槽位'})
    local card = call(frame,'品牌装备属性',{
        ['基础装甲']=call(frame,'TD2普通装备规则',{'armor',['部位']=slot}),
        ['属性行']=table.concat(attributes)
    })
    out[#out+1] = '<h2>装备属性</h2>' .. card
    if #talents > 0 then
        out[#out+1] = '<h3 class="td2-talent-section-title">天赋</h3><div class="td2-brand-bonuses">'
        for _, mode in ipairs({'PvE','PvP'}) do
            out[#out+1] = '<div class="td2-brand-panel td2-brand-' .. mode:lower() .. '">'
            for _, key in ipairs(talents) do
                local talent = lookup(talentData,key); local c = talent.modes[mode]
                if c then
                    out[#out+1] = '<div id="td2-exotic-' .. key .. '-' .. mode:lower() .. '">' .. records.body(frame,c,records.note(a,c)) .. '</div>'
                else out[#out+1] = '<p>天赋资料待核实</p>' end
            end
            out[#out+1] = '</div>'
        end
        out[#out+1] = '</div>'
    end

    local acquisitionReader = require('Module:TD2品牌投影')
    out[#out+1] = '<h2>制作与获取</h2><h3 class="td2-source-heading">装备图纸</h3><dl class="td2-ordinary-blueprints"><dt>制作图纸</dt><dd>' .. crafting .. '</dd><dt>重新配置图纸</dt><dd>' .. reconfigure .. '</dd></dl>'
    out[#out+1] = '<div class="td2-divider-soft" aria-hidden="true"></div><h3 class="td2-source-heading">图纸获取</h3><div class="td2-acquisition-result">' .. acquisitionReader.blueprintSource({args={source_subject=id},expandTemplate=function(_,spec)return frame:expandTemplate(spec) end}) .. '</div>'
    out[#out+1] = '<div class="td2-divider-soft" aria-hidden="true"></div><h3 class="td2-source-heading">' .. frame:preprocess(acquisitionReader.acquisitionHeading(frame)) .. '</h3>'
    out[#out+1] = acquisitionReader.acquisition({args={source_subject=id}})
    if trim(a['其他机制']) ~= '' then out[#out+1] = '<h2>其他资料</h2>' .. frame:preprocess(a['其他机制']) end
    out[#out+1] = call(frame,'TD2普通装备规则',{'expertise'}) .. records.references(frame)
    out[#out+1] = '</div>'

    out[#out+1] = call(frame,'TD2装备导航',{})
    return table.concat(out)
end
return p
