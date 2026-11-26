local p = {}
local events = mw.loadData('Module:TD2活动日程')
local time = require('Module:TD2首页时间')

local function card(frame, now, start, finish, fields)
    fields['开始时刻'], fields['结束时刻'] = start, finish
    fields['未开始'] = now < start and '1' or ''
    fields['日期'] = time.beijingTime(start) .. ' 至 ' .. time.beijingTime(finish) .. '（北京时间）'
    fields['结束日期'] = os.date('!%Y-%m-%dT%H:%M:%SZ', finish)
    fields['剩余'] = time.remaining(finish - now)
    return frame:expandTemplate{title = 'TD2首页消息卡', args = fields}
end

function p.render(frame)
    local now = tonumber(frame.args['时刻']) or os.time()
    local cards = {}
    for _, event in ipairs(events) do
        if now < event.finish then
            cards[#cards + 1] = card(frame, now, event.start, event.finish, {
                ['名称'] = event.name, ['图片'] = event.image,
                ['类型'] = event.kind, ['图标'] = event.icon, ['日历图'] = '1'
            })
        end
    end
    return table.concat(cards, '\n')
end

function p.manual(frame)
    local args = frame.args
    local now, start, lastDay = tonumber(args['时刻']), tonumber(args['开始时刻']), tonumber(args['结束日'])
    if not now or not start or not lastDay or lastDay < start or now >= lastDay + 86400 then return '' end
    return card(frame, now, start, lastDay + 86400, {
        ['名称'] = args['名称'], ['来源'] = args['来源'], ['图片'] = args['图片'],
        ['类型'] = args['类型'], ['图标'] = args['图标']
    })
end

return p
