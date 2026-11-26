"""Exercise native projection failures against the installed weapon definitions."""
import json
import subprocess
import unittest
from unittest.mock import patch

from reader_test_html import weapon_unit
from tools.equipment.weapon_projection import WeaponProjection
from tools.equipment.weapons_native import ROOT, WeaponNative
from tools.equipment.wikitext import WikiSubset


class WeaponImportProjection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        mapping = json.loads((ROOT / "data/equipment/native-map.json").read_text("utf8"))
        cls.family = next(e for e in mapping["weapons"] if e["items"][0]["name"] == "ACS-12")
        cls.items = {b["name"]: b for b in cls.family["items"]}
        cls.native = WeaponNative(ROOT / "resources/game/current/raw_files")
        cls.projection = WeaponProjection(cls.native)

    def project(self, *names):
        return self.projection.project([{**self.family, "items": [self.items[name] for name in names]}])

    def test_attribute_failure_and_retry_on_same_projector(self):
        with patch.object(self.projection, "attributes", side_effect=ValueError("missing attribute source")):
            failed = self.project("ACS-12")
        healthy = self.project("ACS-12")
        self.assertTrue(any(row["field"] == "attributes" for row in failed["unavailable"]))
        self.assertFalse(any(row["field"] == "attributes" for row in healthy["unavailable"]))
        self.assertEqual(len(healthy["entities"][0]["units"][0]["semantic"]["attributes"]), 3)

    def test_random_slot_and_failed_mode_have_distinct_membership(self):
        config = self.projection.config
        def random_slot(item, quality, field, kind):
            return ([], []) if field == "myTalentSlots" else config(item, quality, field, kind)
        with patch.object(self.projection, "config", random_slot):
            random = self.project("左边")["entities"][0]["units"][0]
        self.assertEqual(random["fixed_effect_ids"], [])
        self.assertTrue(random["semantic"]["random_talent"])
        talent = self.native.talent
        def fail_pvp(row, mode):
            if mode == "PvP":
                raise ValueError("missing mode")
            return talent(row, mode)
        with patch.object(self.native, "talent", fail_pvp):
            failed = self.project("左边")
        self.assertNotIn("fixed_effect_ids", failed["entities"][0]["units"][0])
        self.assertTrue(any(r["field"].endswith(":PvP") for r in failed["unavailable"]))

    def test_replaced_lefty_slot_renders_only_the_new_talent(self):
        config = self.projection.config
        donor = self.items["摇滚"]
        def replaced(item, quality, field, kind):
            if field == "myTalentSlots" and item["resource_uid"] == self.items["左边"]["uid"]:
                item = self.native.record(donor["source"], donor["uid"])
            return config(item, quality, field, kind)
        with patch.object(self.projection, "config", replaced):
            incoming = self.project("ACS-12", "左边")
        script = """
const fs=require('node:fs'),db=require('./tools/equipment/database.cjs'),catalog=require('./tools/equipment/catalog.cjs');
const {plan}=require('./tools/equipment/import.cjs'),projection=require('./tools/equipment/projection.cjs');
const input=JSON.parse(fs.readFileSync(0,'utf8')),e=input.entities[0],base=JSON.parse(fs.readFileSync('data/equipment/native-baseline.json'));
const records=db.load(),old=records.entities[e.id].effects.find(t=>t.所属装备===input.entities[0].units.find(u=>u.semantic?.装备名称==='左边').semantic.stable_id);
const raw=fs.readFileSync(e.source,'utf8').replace('|资料ID=','|天赋脚注:'+old.效果ID+':PvE=退役样本脚注\\n|资料ID=');
const result=plan(input,base,()=>raw,records,{}),reader=projection.reader(result.database);
const modes=Object.fromEntries(db.references(result.database).filter(r=>r.entity===e.id).map(r=>[r.id,r.modes]));
const sources={'wiki/modules/TD2装备映射.lua':'return '+catalog.lua({entities:{[e.id]:reader.entities[e.id]},acquisition:reader.acquisition}),
               'wiki/modules/TD2效果映射.lua':'return '+catalog.lua(modes)};
console.log(JSON.stringify({sources,raw:result.pages[0].raw}));
"""
        process = subprocess.run(["node", "-e", script], cwd=ROOT, input=json.dumps(incoming),
                                 capture_output=True, encoding="utf8")
        self.assertEqual(process.returncode, 0, process.stderr)
        result = json.loads(process.stdout)
        self.assertIn("退役样本脚注", result["raw"])
        rendered = WikiSubset(ROOT, sources=result["sources"]).expand(result["raw"], {})
        left = weapon_unit(rendered, "左边")
        self.assertIn("完美加大", left)
        self.assertNotIn("癫狂大锤", left)
        self.assertNotIn("退役样本脚注", left)
