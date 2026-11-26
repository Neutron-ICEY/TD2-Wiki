local p = {}
local seasons = mw.loadData('Module:TD2赛季日程')
local time = require('Module:TD2首页时间')

function p.render(frame)
    local now = tonumber(frame.args['时刻']) or os.time()
    local cards = {}
    for _, season in ipairs(seasons) do
        if now < season.finish then
            local card = mw.html.create('div'):addClass('td2-home-season-card'):addClass('td2-divider-soft')
                :attr('data-start', season.start):attr('data-end', season.finish)
            if now < season.start then card:addClass('td2-home-season-off') end
            card:tag('div'):addClass('td2-home-season-art')
                :wikitext('[[File:' .. season.image .. '|640px|link=|alt=]]')
            local footer = card:tag('div'):addClass('td2-home-season-details')
            local meta = footer:tag('div'):addClass('td2-home-season-meta')
            meta:tag('div'):addClass('td2-home-season-name'):wikitext(season.title .. ' · ' .. season.name)
            local hours = math.floor((season.finish - now) / 3600)
            local timer = meta:tag('div'):addClass('td2-home-season-countdown'):attr('role', 'timer')
                :attr('aria-label', '赛季剩余时间'):wikitext('距结束还有 ')
            timer:tag('span'):addClass('td2-home-season-time')
                :wikitext(string.format('%d周 %d日 %d时', math.floor(hours / 168), math.floor(hours / 24) % 7, hours % 24))
            local dial = footer:tag('div'):addClass('td2-home-season-clock')
            local fraction = math.max(0, now - season.start) / (season.finish - season.start)
            local ring = dial:tag('span'):addClass('td2-home-ring'):attr('aria-hidden', 'true')
                :attr('style', string.format('--td2-home-arc:%.4fdeg', 360 * fraction))
            if fraction > 0 then ring:addClass('td2-home-ring-filled') end
            dial:tag('span'):addClass('td2-home-season-badge')
                :wikitext('[[File:' .. season.icon .. '|128px|link=|alt=]]')
            footer:tag('time'):attr('datetime', os.date('!%Y-%m-%dT%H:%M:%SZ', season.finish))
                :wikitext(time.beijingTime(season.finish) .. ' 结束（北京时间）')
            cards[#cards + 1] = tostring(card)
        end
    end
    return table.concat(cards)
end

return p
