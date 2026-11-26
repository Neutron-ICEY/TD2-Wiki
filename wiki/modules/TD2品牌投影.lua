local p = {}
local slots = {mask=true, chest=true, holster=true, backpack=true, gloves=true, kneepads=true}

local function trim(value)
    return mw.text.trim(value or '')
end

local function text(value)
    return mw.text.nowiki(value or '')
end

function p.randomCrafting(frame)
    if trim(frame.args.kind) == 'unbranded' then return '' end
    local data = mw.loadData('Module:TD2随机品牌制作数据')
    local brand = data.brands[trim(frame.args.brand)]
    if not brand then return '' end
    for _, recipe in ipairs(data.recipes) do
        if recipe.slot == trim(frame.args.slot) then
            for _, uid in ipairs(recipe.brands) do
                if uid == brand then
                    return '<ul class="td2-blueprints td2-random-brand-crafting"><li>' .. frame:preprocess('<span class="td2-icon">[[File:{{TD2资产|ui-loadout-circle-icon}}|24x24px|link=|alt=]]</span>') .. '随机品牌制作</li></ul>'
                end
            end
        end
    end
    return ''
end

function p.value(frame)
    local value = trim(frame.args[1])
    local unsigned = value:gsub('^[+-]', '')
    if not (unsigned:match('^%d+$') or unsigned:match('^%d+%.%d+$') or unsigned:match('^%.%d+$')) then
        error('数值须为十进制文本；空白不等于 0。')
    end
    local number = tonumber(value)
    if not number or number == math.huge or number == -math.huge then error('数值无效；空白不等于 0。') end
    value = value:gsub('^%+', '')
    return (value:sub(1, 1) == '-' and '' or '+') .. text(value)
end


function p.bonusValue(frame)
    local signed = p.value(frame)
    local number = tonumber(trim(frame.args[1]))
    if trim(frame.args['词条']) == 'bonus_increased_threat' then
        return signed:sub(1, 1) .. string.format('%.0f', math.floor(math.abs(number) + 0.5))
    end
    local magnitude = math.floor(math.abs(number) * 10 + 0.5) / 10
    return signed:sub(1, 1) .. string.format('%.1f', magnitude)
end

local function rejectOrdinaryFields(args)
    for _, key in ipairs({'talent_id', 'brand_material_mode', 'blueprint_mode', '天赋引用', '品牌材料例外', '图纸例外'}) do
        if args[key] ~= nil then error('普通型号字段已退役：' .. key) end
    end
end

local function recordData(args)
    local data = {kind=args.kind, slot=trim(args.slot), name=trim(args.name), en=trim(args.en),
        stable_id=trim(args.stable_id), talent_mode=trim(args.talent_mode), talent_ref=trim(args.talent_ref)}
    if not slots[data.slot] then error('装备部位无效：请显式迁移旧 pilot 部位。') end
    if data.name == '' then error('装备名称不能为空。') end
    if data.kind ~= 'ordinary' and data.kind ~= 'named' then error('记录类型无效。') end
    if data.kind == 'ordinary' then
        rejectOrdinaryFields(args)
    end
    if data.kind == 'named' then
        data.blueprint_absent = not require('Module:TD2资料映射').hasBlueprint(data.stable_id)
    end
    if data.kind == 'named' and (data.stable_id == 'uuid' or not data.stable_id:match('^[%w_%-]+$')) then
        error('具名稳定标识缺失或损坏；请保留原标识并复核。')
    end
    return data
end

function p.record(frame)
    if frame.args.kind == 'ordinary' then
        local templates = {['品牌装备型号']=true, ['品牌型号面具']=true, ['品牌型号胸甲']=true,
            ['品牌型号枪套']=true, ['品牌型号背包']=true, ['品牌型号手套']=true, ['品牌型号护膝']=true}
        local parent = frame:getParent()
        if parent then
            local title = parent:getTitle():gsub('^[^:]+:', '')
            if templates[title] then rejectOrdinaryFields(parent.args) end
        end
    end
    return tostring(mw.html.create('span'):addClass('td2-record')
        :attr('data-record', mw.text.jsonEncode(recordData(frame.args))))
end

local function records(content)
    local rows = {}
    for encoded in (content or ''):gmatch('data%-record="(.-)"') do
        local data = mw.text.jsonDecode(mw.text.decode(encoded, true))
        if type(data) ~= 'table' then error('装备投影元数据损坏，请检查原始记录。') end
        rows[#rows+1] = data
    end
    return rows
end

function p.models(frame)
    local slot = trim(frame.args.slot)
    if not slots[slot] then error('型号部位无效。') end
    local result = mw.html.create('ul'):addClass('td2-equipment-models')
    local count = 0
    local craftable = {}
    for name in (frame.args.blueprints or ''):gmatch('[^;]+') do
        if trim(name) ~= '无制作图纸' then craftable[trim(name)] = true end
    end
    for _, item in ipairs(records((frame.args.ordinary or '') .. (frame.args.named or ''))) do
        if item.kind == 'ordinary' then rejectOrdinaryFields(item) end
        if item.slot == slot then
            local row = result:tag('li'):addClass(item.kind == 'named' and 'td2-model-named' or 'td2-model-ordinary')
            local hasBlueprint = item.kind == 'ordinary' and craftable[item.name]
                or item.kind == 'named' and not item.blueprint_absent
            if hasBlueprint then row:addClass('td2-model-craftable') end
            if item.kind == 'named' then
                if not item.stable_id:match('^[%w_%-]+$') then error('具名锚点标识无效。') end
                row:wikitext('[[#named-' .. item.stable_id .. '|' .. text(item.name) .. ']]')
            else
                row:wikitext(text(item.name))
            end
            if item.en ~= '' then
                local english = text(item.en)
                if item.kind == 'named' then english = '[[#named-' .. item.stable_id .. '|' .. english .. ']]' end
                row:tag('div'):addClass('td2-model-english'):wikitext(english)
            end
            count = count + 1
        end
    end
    if count == 0 then return '' end
    local label = '装备型号 · ' .. count
    return tostring(mw.html.create('div'):addClass('td2-models mw-collapsible mw-collapsed')
        :attr('data-expandtext', label):attr('data-collapsetext', label)
        :tag('div'):addClass('mw-collapsible-content'):wikitext(tostring(result)):done())
end

local function headingLink(frame, pageId, label)
    local page = frame:expandTemplate{title='TD2页面地址', args={[1]=pageId}}
    return '[[' .. page .. '|' .. label .. ']]'
end
function p.acquisitionHeading(frame)
    return headingLink(frame,'loot-guide','装备获取')
end
function p.blueprintHeading(frame)
    return headingLink(frame,'crafting-guide','图纸获取')
end
local function acquisitionText(subject,purpose)
    local value=require('Module:TD2资料映射').acquisitionText(subject,purpose)
    return '<p>'..(text(value):gsub('\n','<br>'))..'</p>'
end
function p.acquisition(frame)
    return '<div class="td2-acquisition-result">'..acquisitionText(frame.args.source_subject,'equipment')..'</div>'
end
function p.ordinaryBlueprintSource(frame)
    local subject = frame.args.source_subject
    local fact = (mw.loadData('Module:TD2装备映射').acquisition or {})[subject]
    if fact and fact.blueprintGroups and fact.blueprintGroups[1] then
        local rows = {}
        for _, group in ipairs(fact.blueprintGroups) do
            local methods = {}
            for _, method in ipairs(group.methods) do methods[#methods+1] = text(method) end
            rows[#rows+1] = '<dt>' .. text(group.title) .. '</dt><dd>' .. table.concat(methods, '<br>') .. '</dd>'
        end
        return '<dl class="td2-ordinary-blueprints td2-blueprint-sources">' .. table.concat(rows) .. '</dl>'
    end
    if require('Module:TD2资料映射').acquisitionText(subject,'blueprint')=='无制作图纸' then
        return '<p>'..frame:expandTemplate{title='品牌图纸列表',args={['列表']='无制作图纸'}}..'</p>'
    end
    return acquisitionText(subject,'blueprint')
end
p.blueprintSource=p.ordinaryBlueprintSource

local function renderMajor(frame, values, triple, slot)
    triple = trim(triple)
    if triple ~= '' and triple ~= '否' and triple ~= '是' then error('关闭背包例外前，请先恢复单核心。') end
    if triple == '是' and slot ~= 'backpack' then error('三核心仅适用于背包。') end
    values = trim(values)
    if triple == '是' then values = 'red;blue;yellow' end
    if values == '' then return frame:expandTemplate{title='TD2图标', args={['类别']='state', ['键']='unknown'}} .. '待核实' end
    local seen, parts = {}, {}
    for _, id in ipairs(mw.text.split(values, ';', true)) do
        if (id ~= 'red' and id ~= 'blue' and id ~= 'yellow') or seen[id] then error('主核心类型无效或重复。') end
        seen[id] = true
        parts[#parts+1] = frame:expandTemplate{title='TD2主属性显示', args={[1]=id}}
    end
    if triple ~= '是' and #parts > 1 then
        local icons = {}
        for _, id in ipairs({'red', 'blue', 'yellow'}) do
            if seen[id] then icons[#icons+1] = frame:expandTemplate{title='TD2图标', args={['类别']='state', ['键']=id}} end
        end
        return '<span class="td2-major-random">' .. table.concat(icons) .. '<span>随机加成</span></span>'
    end
    return table.concat(parts, '<br>')
end

function p.major(frame)
    return renderMajor(frame, frame.args.values, frame.args.triple, frame.args.slot)
end

function p.namedCards(frame)
    local order = {mask=1, backpack=2, chest=3, gloves=4, holster=5, kneepads=6}
    local cards = {}
    local function resolveCard(card)
        local item = records(card)[1]
        if not item or item.kind ~= 'named' then error('具名卡片缺少原记录投影。') end
        card = card:gsub('<span class="td2%-named%-effects"></span>', function()
            if item.talent_mode ~= 'fixed' or item.talent_ref == '' then return '' end
            local content=require('Module:TD2资料记录').renderRows(frame,frame.args.effects,item.stable_id,item.talent_ref)
            if content == '' then return '' end
            return '<h4 class="td2-talent-section-title">天赋</h4>' .. content
        end)
        local major=require('Module:TD2资料映射').namedCore(frame,item.stable_id)
        card = card:gsub('<span class="td2%-major%-reference".-</span>', function() return major end)
        local resolved = p.acquisition({args={source_subject=item.stable_id}})
        card = card:gsub('<span class="td2%-named%-acquisition"></span>', function() return resolved end)
        card = card:gsub('<span class="td2%-named%-acquisition%-heading"></span>', function()
            return frame:preprocess(p.acquisitionHeading(frame))
        end)
        cards[#cards+1] = {html=card, rank=order[item.slot] or 7, index=#cards+1}
        return card
    end
    local result = (frame.args.cards or ''):gsub('(<div class="td2%-equipment".-<span class="td2%-named%-end"></span>%s*</div>)', resolveCard)
    table.sort(cards, function(a, b)
        if a.rank == b.rank then return a.index < b.index end
        return a.rank < b.rank
    end)
    local index = 0
    local function nextCard()
        index = index + 1
        return cards[index].html
    end
    result = result:gsub('(<div class="td2%-equipment".-<span class="td2%-named%-end"></span>%s*</div>)', nextCard)
    return result
end

return p
