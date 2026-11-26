local p = {}
local metrics = {
    { label = '编辑数', key = 'edits' },
    { label = '页面数', key = 'pages' },
}

local function integer(raw)
    local digits = (raw or ''):gsub('，', ''):gsub('[,%s]', '')
    local count = digits:match('^%d+$') and tonumber(digits)
    return count ~= math.huge and count or nil
end

function p.render(frame)
    local dial = mw.html.create('div'):addClass('td2-home-dial')
    local reading = dial:tag('dl'):addClass('td2-home-reading')
    for _, metric in ipairs(metrics) do
        local count = integer(frame.args[metric.label])
        local class = 'td2-home-' .. metric.key
        local ring = dial:tag('span'):addClass('td2-home-ring'):addClass(class):attr('aria-hidden', 'true')
        local row = reading:tag('div'):addClass(class)
        local display = count and string.format('%.0f', count) or '—'
        row:tag('dt'):wikitext(metric.label)
        local value = row:tag('dd'):wikitext(display)
        if count then
            local nextGoal = 1
            while nextGoal <= count do nextGoal = nextGoal * 2 end
            ring:attr('style', string.format('--td2-home-arc:%.4fdeg', 360 * count / nextGoal))
            if count > 0 then ring:addClass('td2-home-ring-filled') end
            if metric.key == 'edits' then value:attr('style', '--td2-digits:' .. #display) end
            row:attr('title', metric.label .. ' ' .. display .. ' / ' .. string.format('%.0f', nextGoal))
        end
    end
    local followers = integer(frame.args['关注数'])
    local footer = mw.html.create('dl'):addClass('td2-home-followers')
    footer:tag('dt'):wikitext('关注数:')
    local followerCount = footer:tag('dd')
    followerCount:tag('span'):attr('aria-hidden', 'true'):wikitext('[[File:TD2-UI-Loadout11-Icon.png|32px|link=|alt=]]')
    followerCount:tag('span'):addClass('td2-home-follower-count'):wikitext(followers and string.format('%.0f', followers) or '—')
    return tostring(dial) .. tostring(footer)
end

return p
