from pathlib import Path
from wiki_subset import WikiSubset
from tools.equipment.lua import LuaBoundary
import json
import subprocess
from functools import lru_cache

ROOT=Path(__file__).resolve().parents[1]

@lru_cache(maxsize=1)
def equipment_snapshot():
    return json.loads(subprocess.check_output(['node','-e','process.stdout.write(JSON.stringify(require("./tools/exotic_gear/data.cjs").snapshot()))'],cwd=ROOT,encoding='utf8'))

class ExoticLuaReader(WikiSubset):
    def __init__(self,equipment_patch=None,acquisition_patch=None,**kwargs):
        super().__init__(ROOT,**kwargs)
        self.lua_boundary=LuaBoundary(self)
        if equipment_patch:
            lua=self.lua_boundary.lua
            data=lua.eval("require('Module:TD2装备属性数据')")
            for key,value in equipment_patch.items():data[key]=lua.table_from(value,recursive=True)
        if acquisition_patch is not None:
            lua=self.lua_boundary.lua
            data=lua.eval("require('Module:TD2装备映射')")
            data['acquisition']=lua.table_from(acquisition_patch,recursive=True)

    def fixed(self,raw,fields):
        """Change the fixed-data fixture, then render through the same page mapping as production."""
        import re
        identity=re.search(r'\|资料ID=([^\n|}]+)',raw)[1].strip()
        data=self.lua_boundary.lua.eval("require('Module:TD2装备属性数据')")
        for key,value in fields.items():data['equipment'][identity]['fields'][key]=value
        return self.expand(raw,{})
