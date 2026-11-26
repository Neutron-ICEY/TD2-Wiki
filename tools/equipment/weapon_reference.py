"""Read the simulator's literal weapon inputs; no assembly is executed.

The constructor contract is checked independently before accepting its arguments.
This is cross-check evidence, not a replacement for native identity or localization.
"""
import json
from pathlib import Path
from tools.asset_import.mapping import arg_index


def attributes(metadata, il):
    model=next(t for t in metadata['types'] if t['name']=='Division2BuildTool.Model.Attribute')
    ctor=next(m for m in model['methods'] if m['token']=='0x0600164e')
    for suffix,index in [('::Name',2),('::set_Value',3),('::set_Unit',4)]:
        assert any(i and o['opcode'] in ('call','stfld') and o['operand']['name'].endswith(suffix) and arg_index(ctor['il'][i-1])==index for i,o in enumerate(ctor['il']))
    named=next(t for t in metadata['types'] if t['name']=='Division2BuildTool.Model.NamedAttribute')
    named_ctor=next(m for m in named['methods'] if m['name']=='.ctor')
    assert [arg_index(o) for o in named_ctor['il'][:6]]==list(range(6))
    assert named_ctor['il'][6]['operand']['token']==ctor['token']
    tokens={ctor['token'],named_ctor['token']}
    def literal(values,op,field):
        assert [v['opcode'] for v in values]==['ldstr','ldstr','ldc.r8','ldstr','ldc.r8']
        return {'name':values[1]['operand'],'value':values[2]['operand'],'unit':values[3]['operand'],'field':field,'il_offset':op['offset']}
    rows={}
    for i,op in enumerate(il):
        if op['opcode']!='newobj' or op['operand']['token'] not in tokens:continue
        values=il[i-5:i]
        if [v['opcode'] for v in values]!=['ldstr','ldstr','ldc.r8','ldstr','ldc.r8']:continue
        if il[i+1]['opcode']!='stsfld':continue
        field=il[i+1]['operand']['name']
        # Value is the ordinary roll ceiling; MaxValue also serves prototypes.
        rows[field]=literal(values,op,field)
    end=next(i for i,o in enumerate(il) if o['opcode']=='stsfld' and o['operand']['name'].endswith('::WeaponAttribute1List'))
    start=max(i for i,o in enumerate(il[:end]) if o['opcode']=='stsfld')
    primary=[o['operand']['name'] for o in il[start+1:end] if o['opcode']=='ldsfld']
    assert len(primary)==7 and all(k in rows for k in primary)
    def argument(segment,index):
        op=segment[index]
        if op['opcode']=='ldnull':return None,index+1
        if op['opcode']=='ldsfld':return rows[op['operand']['name']],index+1
        end=segment[index+5]
        assert end['opcode']=='newobj' and end['operand']['token'] in tokens
        return literal(segment[index:index+5],end,'inline:'+str(end['offset'])),index+6
    return rows,primary,argument


def extract(metadata, constructor):
    weapon=next(t for t in constructor['types'] if t['name']=='Division2BuildTool.Model.Weapon')
    ctor=next(m for m in weapon['methods'] if m['token']=='0x060016ed')
    il=ctor['il']
    forwarded=next(m for m in weapon['methods'] if m['token']=='0x060016ee')['il']
    assert [arg_index(op) for op in forwarded[:18]]==list(range(17))+[18]
    assert forwarded[18]['operand']['token']==ctor['token']
    for suffix,index in [('::Name',4),('::set_Damage',5),('::set_RPM',6),('::set_MagazineSize',7),('::set_Reload',8),('::set_Range',9),('::set_Attribute2',10),('::set_Attribute3',11)]:
        assert any(i>0 and op['opcode'] in ('call','stfld') and op['operand']['name'].endswith(suffix)
                   and arg_index(il[i-1])==index for i,op in enumerate(il)),suffix
    data=next(t for t in metadata['types'] if t['name']=='Division2BuildTool.Model.AppData')
    il=next(m['il'] for m in data['methods'] if m['name']=='.cctor')
    attrs,primary,attribute_argument=attributes(metadata,il)
    rows=[];start=0
    def integer(op):
        if not op['opcode'].startswith('ldc.i4'):raise ValueError('Not an integer literal')
        return op['operand'] if op['opcode'] in ('ldc.i4','ldc.i4.s') else int(op['opcode'].rsplit('.',1)[1])
    for i,op in enumerate(il):
        if op['opcode']!='newobj' or op['operand']['name']!='Division2BuildTool.Model.Weapon::.ctor':continue
        assert op['operand']['token'] in (ctor['token'],'0x060016ee')
        segment=il[start:i];start=i+1
        candidates=[]
        for j,p in enumerate(segment):
            if j<3 or p['opcode']!='ldstr' or j+5>=len(segment):continue
            if [x['opcode'] for x in segment[j+1:j+3]]!=['ldc.r8','ldc.r8']:continue
            if [x['opcode'] for x in segment[j+4:j+6]]!=['ldc.r8','ldc.r8']:continue
            try:kind,rarity,save=map(integer,segment[j-3:j]);magazine=integer(segment[j+3])
            except ValueError:continue
            core=[attrs[primary[kind]]]
            cursor=j+6
            for _ in range(2):
                attr,cursor=attribute_argument(segment,cursor)
                if attr is not None:core.append(attr)
            candidates.append({'key':f'{kind}:{rarity}:{save}','name':p['operand'],'type':kind,'rarity':rarity,'attributes':core,
                               'damage':segment[j+1]['operand'],'rpm':segment[j+2]['operand'],
                               'magazine':magazine,'reload_empty':segment[j+4]['operand'],'range':segment[j+5]['operand'],
                               'image':f'weapon{kind}{rarity}_{save}.png','il_offset':p['offset'],'constructor_offset':op['offset']})
        assert len(candidates)==1,('Weapon constructor input ambiguous',op['offset'])
        rows.extend(candidates)
    assert len({r['key'] for r in rows})==len(rows)
    return rows


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('metadata',type=Path);p.add_argument('constructor',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    assert not a.output.exists()
    rows=extract(json.loads(a.metadata.read_text('utf-8-sig')),json.loads(a.constructor.read_text('utf-8-sig')))
    a.output.write_text(json.dumps({'schema_version':1,'version':'29.2.0','weapons':rows},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(len(rows),'weapon constructor inputs')
