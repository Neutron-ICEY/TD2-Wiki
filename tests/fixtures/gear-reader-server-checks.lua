return function(p, templates, cases)
    local frame = mw.getCurrentFrame()
    local results = {}
    local function check(name, fn)
        local ok, result = pcall(fn)
        results[#results + 1] = {name=name, passed=ok, result=result}
    end
    local function has(text, value) assert(text:find(value, 1, true), value) end
    local function lacks(text, value) assert(not text:find(value, 1, true), value) end
    local function render(name, args)
        local source = templates[name]:gsub('<includeonly>', ''):gsub('</includeonly>', '')
        return frame:newChild{title='模板:' .. name, args=args}:preprocess(source)
    end
    local function equipment(args) return p.equipment(frame:newChild{args=args}) end
    local target = '<span class="td2-gear-core-target" data-slot="mask"></span>'
    for _, input in ipairs({'', 'RETURN_CHECK', 'LEGAL_170,000', target, target .. target}) do
        check('single return: ' .. input, function()
            local values = {equipment({equipment=input})}
            assert(#values == 1)
            assert(values[1] == (input:gsub('<span.-</span>', '')))
            return values[1]
        end)
    end
    check('invalid override still rejected', function()
        assert(not pcall(equipment, {pve='unknown'}))
        return true
    end)
    check('invalid target still rejected', function()
        assert(not pcall(equipment, {equipment=target:gsub('mask', 'unknown')}))
        return true
    end)
    local red = render('装备组核心槽', {['模式']='PvE', ['范围']='公共', ['选择方式']='固定', ['固定属性']='red'})
    check('real core subtemplate and icon', function()
        has(red, 'data-mode="PvE"'); has(red, 'data-scope="公共"'); has(red, 'state/red'); has(red, '武器伤害')
        return red
    end)
    for _, mode in ipairs({'PvE', 'PvP'}) do
        check(mode .. ' never inherits', function()
            local records = red:gsub('data%-mode="PvE"', 'data-mode="' .. mode .. '"')
            local text = equipment({cores=records, equipment=target})
            has(text, 'td2-brand-' .. mode:lower())
            lacks(text, mode == 'PvE' and 'td2-brand-pvp' or 'td2-brand-pve')
            return text
        end)
    end
    check('enabled empty exception does not fall back', function()
        assert(equipment({cores=red, pve='mask', equipment=target}) == '')
        return true
    end)
    for _, case in ipairs(cases) do
        check(case.name, function()
            local args = case.args
            local cores, cards, effects = {}, {}, {}
            for _, row in ipairs(case.cores) do cores[#cores+1] = render('装备组核心槽', row) end
            for _, row in ipairs(case.equipment) do
                local card = render('装备组装备', row)
                has(card, 'data-slot="' .. row['装备部位'] .. '"')
                for _, key in ipairs({'装备名称', '英文原名', '核心属性规则', '次属性规则', '来源说明'}) do
                    if row[key] and row[key] ~= '' then has(card, row[key]) end
                end
                lacks(card, '{{{')
                cards[#cards+1] = card
            end
            for _, row in ipairs(case.effects) do effects[#effects+1] = render('装备组加成', row) end
            args['核心槽'], args['装备资料'], args['套装加成'] = table.concat(cores), table.concat(cards), table.concat(effects)
            local projected = equipment({cores=args['核心槽'], equipment=args['装备资料'], pve=args['PvE独立核心部位'], pvp=args['PvP独立核心部位']})
            lacks(projected, 'td2-gear-core-target'); lacks(projected, '{{{')
            for _, value in ipairs(case.expected) do has(projected, value) end
            local _, lineCount = projected:gsub('class="td2%-gear%-core%-line"', '')
            assert(lineCount == case.lines, 'core lines: ' .. lineCount)
            local liveMain = render('装备组信息', args)
            has(liveMain, projected)
            lacks(liveMain, '{{{')
            for _, value in ipairs(case.mainExpected) do has(liveMain, value) end
            local count = #cards
            has(liveMain, projected .. count)
            return {projected=projected, information_using_published_module=liveMain, published_module_count=count, core_lines=lineCount}
        end)
    end
    return mw.text.jsonEncode(results)
end
