local p = {}
local function trim(v) return mw.text.trim(tostring(v or '')) end
local function escape(v) return tostring(v or ''):gsub('&','&amp;'):gsub('<','&lt;'):gsub('>','&gt;'):gsub('"','&quot;') end
-- 仅在属性展示入口按稳定属性 ID 和已核实名称关联；目标标题经 Registry 核实。
local attributeLinks = {
    bonus_increased_threat = {page='威胁度', names={['威胁度']=true, ['提升威胁度']=true}},
    minor_attribute_reduced_threat = {page='威胁度', names={['降低威胁度']=true}},
}
local function attributeName(frame, id, name)
    local link = attributeLinks[id]
    if not link or not link.names[name] then return name end
    return '<span class="td2-attribute-link">[[' .. link.page .. '|' .. name .. ']]</span>'
end
function p.attributeName(frame)
    return attributeName(frame, trim(frame.args.id), trim(frame.args.name))
end
function p.effect(frame)
    local a, row = frame:getParent().args, {}
    local reference = mw.loadData('Module:TD2效果映射')[trim(a['引用'])]
    local mapped = reference and reference[trim(a['模式'])] or {}
    for _, key in ipairs({'效果ID','模式','所属装备','件数','部位','依赖','名称','图标','属性ID','属性','数值','单位','描述'}) do
        row[key] = trim(a[key] ~= nil and a[key] or mapped[key])
        if (key == '名称' or key == '描述') and a[key] == nil then row[key] = frame:preprocess(row[key]) end
    end
    if trim(a['引用']) ~= '' and not (reference and reference[trim(a['模式'])]) then row['描述']='<strong class="td2-data-error">效果引用未配置。</strong>' end
    return '<span class="td2-effect-record" data-record="' .. escape(mw.text.jsonEncode(row)) .. '"></span>'
end
function p.read(raw)
    local rows = {}
    for encoded in tostring(raw or ''):gmatch('<span class="td2%-effect%-record" data%-record="([^"]*)"></span>') do
        rows[#rows+1] = mw.text.jsonDecode(mw.text.decode(encoded))
    end
    return rows
end
function p.anchor(row) return 'td2-effect-' .. row['效果ID']:gsub(':','-') .. '-' .. row['模式']:lower() end
function p.note(args,row)
    return trim(args['天赋脚注:' .. row['效果ID'] .. ':' .. row['模式']])
end
function p.references(frame)
    local out,used={},{}
    for key,value in pairs(frame:getParent().args) do
        local mode=tostring(key):match('^天赋脚注:.+:(Pv[EP])$')
        if mode and trim(value) ~= '' then used[mode]=true end
    end
    for _,mode in ipairs({'PvE','PvP'}) do
        if used[mode] then out[#out+1]='<div class="td2-brand-panel td2-brand-' .. mode:lower() .. '">' .. frame:extensionTag('references','',{group=mode}) .. '</div>' end
    end
    return table.concat(out)
end
function p.body(frame,row,note)
    if row['名称'] ~= '' then
        local icon = row['图标'] ~= '' and frame:expandTemplate{title='TD2图标',args={['类别']='talent',['键']=row['图标'],['用途']='optional'}} or ''
        local description='<p>' .. row['描述']:gsub('\n\n+','</p><p>'):gsub('\n','<br>') .. '</p>'
        local name=row['名称']
        if trim(note) ~= '' then name=name .. frame:extensionTag('ref',note,{name='td2-note-' .. row['效果ID'] .. '-' .. row['模式'],group=row['模式']}) end
        return frame:expandTemplate{title='TD2天赋资料',args={['名称']=name,['描述']=description,['图标内容']=icon}}
    end
    local value = row['数值']
    if value ~= '' and row['属性ID'] ~= '' then value=frame:preprocess('{{#invoke:TD2品牌投影|bonusValue|' .. value .. '|词条=' .. row['属性ID'] .. '}}')
    elseif value ~= '' then value=frame:preprocess('{{#invoke:TD2品牌投影|value|' .. value .. '}}') end
    return '<div class="td2-bonus-line"><span class="td2-bonus-text"><strong>' .. value .. row['单位'] .. '</strong> ' .. attributeName(frame, row['属性ID'], row['属性']) .. '</span></div>' .. (row['描述'] ~= '' and '<div class="td2-talent-description">' .. row['描述'] .. '</div>' or '')
end
function p.renderRows(frame,raw,owner,reference)
    local rows,output = p.read(raw),{}
    owner=trim(owner)
    for _, mode in ipairs({'PvE','PvP'}) do
        local parts = {}
        for _, row in ipairs(rows) do
            if row['模式'] == mode and row['所属装备'] == owner and (not reference or row['效果ID'] == reference) then
                local body=p.body(frame,row)
                parts[#parts+1]='<div id="' .. escape(p.anchor(row)) .. '" class="td2-brand-effect">' .. body .. '</div>'
            end
        end
        if #parts > 0 then output[#output+1]='<div class="td2-brand-panel td2-brand-' .. mode:lower() .. '">' .. table.concat(parts) .. '</div>' end
    end
    return table.concat(output)
end
function p.render(frame) return p.renderRows(frame,frame.args.records,frame.args.owner) end
return p
