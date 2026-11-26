from pathlib import Path
from tools.equipment.wikitext import WikiSubset
from tools.equipment.lua import LuaBoundary

def invoke(method,args,acquisition=None,template=None):
    reader=template.__self__ if template else WikiSubset(Path(__file__).resolve().parents[1])
    boundary=getattr(reader,'lua_boundary',None) or LuaBoundary(reader)
    return boundary.invoke('TD2品牌投影',method,args)
