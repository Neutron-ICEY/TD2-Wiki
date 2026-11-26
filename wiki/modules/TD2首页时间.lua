local p = {}

function p.beijingTime(timestamp)
    local d = os.date('!*t', timestamp + 8 * 3600)
    return string.format('%d月%d日 %02d:%02d', d.month, d.day, d.hour, d.min)
end

function p.remaining(seconds)
    local days = math.floor(seconds / 86400)
    local hours = math.floor(seconds / 3600) % 24
    if days > 0 then return days .. '天 ' .. hours .. '小时' end
    local minutes = math.floor(seconds / 60) % 60
    if hours > 0 then return hours .. '小时 ' .. minutes .. '分' end
    return minutes > 0 and minutes .. '分钟' or '不足1分钟'
end

return p
