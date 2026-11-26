-- TD2 展示参数的安全边界；不保存游戏事实，不读取公共 Infobox 模块。
-- hex：通过 #invoke 的 hex 入口传入 #ABC；非法值返回空串。
-- heading：接收 强调色/渐变起色/渐变止色；只输出三个已验证的 CSS 声明。
-- 默认品质色仍在 ui/brand-sets/brand-sets.css；空串让 stylesheet 接管默认值。
-- 不在 inline style 输出 var()：MediaWiki 1.38 的 checkCss 会拒绝它。
local p = {}

local function hex(value)
    value = mw.text.trim(value or '')
    if value:match('^#%x%x%x$') or value:match('^#%x%x%x%x%x%x$') then
        return value:lower()
    end
    return ''
end

function p.hex(frame)
    return hex(frame.args[1])
end

function p.heading(frame)
    local roles = {
        {'强调色', '--td2-heading-accent'},
        {'渐变起色', '--td2-heading-start'},
        {'渐变止色', '--td2-heading-end'},
    }
    local declarations = {}
    for _, role in ipairs(roles) do
        local value = hex(frame.args[role[1]])
        if value ~= '' then declarations[#declarations + 1] = role[2] .. ':' .. value .. ';' end
    end
    return table.concat(declarations)
end

return p
