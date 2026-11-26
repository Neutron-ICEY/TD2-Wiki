local p = {}
local data = mw.loadData('Module:TD2装备映射')
function p.hasBlueprint(subject)
    local row=(data.acquisition or {})[subject]
    return row and row.hasBlueprint or false
end
function p.acquisitionText(subject,purpose)
    local facts=(data.acquisition or {})[subject] or {}
    local result={}
    for _,row in ipairs(facts[purpose] or {}) do
        result[#result+1]=row.text
    end
    if #result>0 then return table.concat(result,'\n') end
    return purpose=='blueprint' and facts.hasBlueprint==false and '无制作图纸' or '暂无获取资料'
end
function p.coreValue(frame,core)
    local typeCount=0
    if core then for _ in ipairs(core.types) do typeCount=typeCount+1 end end
    if not core or core.count<1 or typeCount==0 then error('核心配置未确认') end
    local values={}
    for _,kind in ipairs(core.types) do
        values[#values+1]=frame:expandTemplate{title=core.selection=='fixed' and 'TD2主属性显示' or 'TD2图标',args=core.selection=='fixed' and {[1]=kind} or {['类别']='state',['键']=kind}}
    end
    if core.selection=='fixed' then
        if core.count~=typeCount then error('固定核心数量不一致') end
        return table.concat(values,'<br>')
    end
    if core.selection~='random' or core.count>typeCount then error('随机核心数量不合法') end
    local row='<span class="td2-major-random">' .. table.concat(values) .. '<span>随机加成</span></span>'
    local rows={};for i=1,core.count do rows[#rows+1]=row end
    return table.concat(rows,'<br>')
end
function p.core(frame)
    local entity=data.entities[frame.args['资料ID']]
    return p.coreValue(frame,entity and entity.rules[frame.args['规则']] and entity.rules[frame.args['规则']].core)
end
function p.namedCore(frame,id)
    local row=data.named[id]
    local entity=row and data.entities[row['资料ID']]
    local rule=entity and entity.rules and entity.rules['named:'..id]
    if not rule or not rule.core then error('具名主核心映射缺失：' .. id) end
    return p.coreValue(frame,rule.core)
end
local function merge(frame, input, fixed)
    local args = {}
    for key,value in pairs(input) do args[key]=value end
    for key,value in pairs(fixed) do args[key]=frame:preprocess(value) end
    return args
end
function p.named(frame)
    local input=frame:getParent().args
    local row=data.named[mw.text.trim(input.stable_id or '')]
    if not row then error('具名装备身份未配置') end
    return frame:expandTemplate{title='品牌装备摘要内容',args=merge(frame,input,row)}
end
function p.render(frame)
    local input=frame:getParent().args
    local entity=data.entities[mw.text.trim(input['资料ID'] or '')]
    if not entity then error('装备身份未配置') end
    local args=merge(frame,input,entity.fields)
    if entity.template=='品牌套装信息' then
        local rows={}
        for _,id in ipairs(entity.named) do rows[#rows+1]=frame:expandTemplate{title='品牌装备摘要',args={stable_id=id}} end
        args['具名装备资料']=table.concat(rows,'\n')
    end
    if entity.template=='品牌套装信息' then return frame:expandTemplate{title='品牌套装内容',args=args} end
    return frame:expandTemplate{title='装备组内容',args=args}
end
return p
