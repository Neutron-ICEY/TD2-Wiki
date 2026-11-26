from types import SimpleNamespace
import unittest
from tools.equipment import native_tree as tree, weapon_damage as damage


class Level40DamageTests(unittest.TestCase):
    def test_next_segment_starts_with_rounded_previous_power(self):
        root=tree.parse('''
myPowerDefinitions
{
 myPowerBaseValue 10
 myLevelModifiers
 {
  LevelPowerModifier 40
  {
   myMaxLevel 40
   myModifier 1.125
  }
  LevelPowerModifier 30
  {
   myModifier 1.40625
  }
  LevelPowerModifier 25
  {
   myMaxLevel 25
   myModifier 1.125
  }
  LevelPowerModifier 31
  {
   myMaxLevel 31
   myModifier 1.25
  }
 }
}
''')
        defs=tree.child(root,'myPowerDefinitions')
        self.assertEqual([damage.level_power(defs,k) for k in (1,25,30,31,40)],[10,169,930,1163,3358])
        with self.assertRaises(ValueError):
            damage.level_power(defs,41)

    def test_primary_pve_event_overrides_weapon_type_before_volley(self):
        def context(kind,name):
            return {'resource_type':kind,'internal_name':name}
        def info(parents,name,kind,maximum):
            ctx=[*parents,context('DamageInfo',name)]
            return [{'context':ctx,'field':'myDamageType','raw_value':kind},
                    {'context':ctx,'field':'myDamageMax','raw_value':str(maximum)}]
        event=context('BurstFireEvent','default')
        aimed=context('FullAutoFireEvent','aimed')
        override=context('myWeaponOverride','')
        primary={'context':[event],'field':'myBulletsPerRound','raw_value':'3'}
        main=info([],'weapon','PHYSICAL',25)
        n=SimpleNamespace(collection=lambda w,field:(None,main,[]))
        alt=info([aimed,override],'scope','PHYSICAL',999)
        self.assertEqual(damage.base_volley(n,None,[primary,*alt],10,3,2),150)
        special=info([event,override],'thermal','FIRE',400)+info([event,override],'shot','PHYSICAL',7.25)
        self.assertEqual(damage.base_volley(n,None,[primary,*special,*alt],10,3,2),43.5)
        main.clear()
        self.assertEqual(damage.base_volley(n,None,[primary,*alt],10,3,.1),15)
        with self.assertRaises(ValueError):
            damage.base_volley(n,None,[],10,3,2)
