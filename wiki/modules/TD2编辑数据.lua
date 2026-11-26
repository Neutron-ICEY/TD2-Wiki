local p = {}
function p.export(frame)
    local data = mw.loadData('Module:TD2编辑数据值')
    local text = data.json:gsub('&','&amp;'):gsub('<','&lt;'):gsub('>','&gt;'):gsub('"','&quot;'):gsub('{','&#123;'):gsub('}','&#125;'):gsub('%[','&#91;'):gsub('%]','&#93;')
    return '<span data-td2-editor-catalog="' .. text .. '"></span>'
end
return p
