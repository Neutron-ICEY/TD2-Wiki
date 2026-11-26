"""Exercise real core rules with Scribunto-style read-only array proxies."""
import unittest
from pathlib import Path

from wiki_subset import WikiSubset
from tools.equipment.lua import LuaBoundary

ROOT = Path(__file__).resolve().parents[1]


class LoadDataProxyTests(unittest.TestCase):
    def test_all_real_core_rules_match_plain_tables(self):
        lua = LuaBoundary(WikiSubset(ROOT)).lua
        lua.execute('''
          testFrame={expandTemplate=function(self,r)
            return r.title..':'..tostring(r.args[1] or r.args['键'])
          end}
        ''')
        data = lua.eval("require('Module:TD2装备映射')")
        module = lua.eval("require('Module:TD2资料映射')")
        get_core = lua.eval("function(e,r) return mw.loadData('Module:TD2装备映射').entities[e].rules[r].core end")
        checked = 0
        for entity_id, entity in data['entities'].items():
            for rule_id, rule in entity['rules'].items():
                core = rule['core']
                if core is None:
                    continue
                with self.subTest(entity=entity_id, rule=rule_id):
                    proxy = get_core(entity_id, rule_id)
                    self.assertEqual(lua.eval('function(t)return #t.types end')(proxy), 0)
                    self.assertEqual(module.coreValue(lua.globals().testFrame, proxy),
                                     module.coreValue(lua.globals().testFrame, core))
                    checked += 1
        self.assertGreater(checked, 0)


if __name__ == '__main__':
    unittest.main()
