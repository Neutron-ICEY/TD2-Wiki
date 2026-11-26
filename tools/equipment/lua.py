"""Execute maintained Lua modules at the local template expansion boundary."""
import html
import json
import os
from pathlib import Path
import sys

class LuaBoundary:
    def __init__(self,reader):
        if os.environ.get('TD2_LUA_TEST_PATH'):sys.path.insert(0,os.environ['TD2_LUA_TEST_PATH'])
        from lupa.lua51 import LuaRuntime
        self.reader=reader;self.lua=LuaRuntime(unpack_returned_tuples=True);g=self.lua.globals()
        def plain(value):
            if hasattr(value,'items'):
                value=g.dataBacking(value)
                entries=dict(value.items())
                if entries and set(entries)==set(range(1,len(entries)+1)):return [plain(entries[i]) for i in range(1,len(entries)+1)]
                return {k:plain(v) for k,v in entries.items()}
            return value
        g.json_encode=lambda value:json.dumps(plain(value),ensure_ascii=False,separators=(',',':'))
        g.json_decode=lambda value:self.lua.table_from(json.loads(value),recursive=True)
        g.decode=lambda value,*_:html.unescape(value)
        g.nowiki=lambda value:html.escape(str(value)).replace('[','&#91;').replace(']','&#93;')
        g.read_module=lambda title:reader.sources.get('wiki/modules/'+title.split(':',1)[1]+'.lua') or (reader.root/'wiki/modules'/(title.split(':',1)[1]+'.lua')).read_text('utf8')
        g.expand_template=lambda title,args:reader.template(title,{str(k):str(v) for k,v in g.dataBacking(args).items()})
        g.preprocess=lambda text:reader.expand(text,{})
        g.parent_title=lambda:reader.template_frames[-1][0] if reader.template_frames else ''
        g.html_escape=lambda value:html.escape(str(value),quote=True)
        self.lua.execute('''
          mw={text={trim=function(v) return tostring(v or ''):match('^%s*(.-)%s*$') end,jsonEncode=json_encode,jsonDecode=json_decode,decode=decode,nowiki=nowiki}}
          mw.text.split=function(s,sep,plain) local out,start={},1 while true do local a,b=s:find(sep,start,plain) if not a then out[#out+1]=s:sub(start) break end out[#out+1]=s:sub(start,a-1);start=b+1 end return out end
          local methods={}
          local function element(name,parent)
            return setmetatable({name=name,parent=parent,attrs={},children={}}, {__index=methods,__tostring=function(n)
              local attrs={};for k,v in pairs(n.attrs) do attrs[#attrs+1]=' '..k..'="'..html_escape(v)..'"' end;table.sort(attrs)
              local children={};for _,v in ipairs(n.children) do children[#children+1]=tostring(v) end
              return '<'..n.name..table.concat(attrs)..'>'..table.concat(children)..'</'..n.name..'>'
            end})
          end
          function methods:attr(k,v) self.attrs[k]=v return self end
          function methods:addClass(v) self.attrs.class=(self.attrs.class and self.attrs.class..' ' or '')..v return self end
          function methods:wikitext(v) self.children[#self.children+1]=v return self end
          function methods:tag(name) local c=element(name,self);self.children[#self.children+1]=c return c end
          function methods:done() return self.parent or self end
          mw.html={create=element}
          local modules={}
          require=function(name) if not modules[name] then modules[name]=assert(loadstring(read_module(name)))() end return modules[name] end
          -- Scribunto exposes loadData through read-only proxies. Indexing and
          -- iteration work on arrays, but Lua 5.1's raw length on a proxy is 0.
          local backing, proxies = {}, {}
          function dataBacking(value) return backing[value] or value end
          local function readonly(value)
            if type(value) ~= 'table' then return value end
            if proxies[value] then return proxies[value] end
            local proxy = setmetatable({}, {
              __index = function(_, key) return readonly(value[key]) end,
              __newindex = function() error('mw.loadData is read only') end
            })
            backing[proxy], proxies[value] = value, proxy
            return proxy
          end
          local ordinaryPairs, ordinaryIpairs = pairs, ipairs
          pairs = function(t)
            if not backing[t] then return ordinaryPairs(t) end
            return function(_, k)
              local key, value = next(backing[t], k)
              return key, readonly(value)
            end, t, nil
          end
          ipairs = function(t)
            if not backing[t] then return ordinaryIpairs(t) end
            return function(_, i)
              i = i + 1
              local value = t[i]
              if value ~= nil then return i, value end
            end, t, 0
          end
          mw.loadData = function(name) return readonly(require(name)) end
          function invoke(module,method,args,parent)
            local frame={args=args,getParent=function() return {args=parent or args,getTitle=function() return parent_title() end} end,
              expandTemplate=function(self,r) return expand_template(r.title,r.args) end,
              preprocess=function(self,text) return preprocess(text) end,
              extensionTag=function(self,name,text,attrs) return '<'..name..(attrs and attrs.name and ' name="'..html_escape(attrs.name)..'"' or '')..(attrs and attrs.group and ' group="'..html_escape(attrs.group)..'"' or '')..'>'..text..'</'..name..'>' end}
            return require('Module:'..module)[method](frame)
          end
        ''')

    def invoke(self,module,method,args,parent=None):
        convert=lambda data:self.lua.table_from({int(k) if str(k).isdigit() else k:v for k,v in data.items()})
        return self.lua.globals().invoke(module,method,convert(args),convert(parent or args))
