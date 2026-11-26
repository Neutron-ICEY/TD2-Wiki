import struct
import unittest

from tools.equipment.weapon_range import adjusted_distance, physical_damage_at


def next_binary32(value):
    bits, = struct.unpack('<I', struct.pack('<f', value))
    return struct.unpack('<f', struct.pack('<I', bits+1))[0]


class DistanceDamageTests(unittest.TestCase):
    def test_cutoff_is_inclusive_inside_before_or_after_the_slope(self):
        for limit, expected in [(15,100), (40,80), (80,40), (100,40)]:
            with self.subTest(limit=limit):
                self.assertEqual(physical_damage_at(limit,20,80,limit,100,40),expected)
                self.assertEqual(physical_damage_at(next_binary32(limit),20,80,limit,100,40),0)

    def test_coincident_and_epsilon_width_check_after_far_test(self):
        self.assertEqual(physical_damage_at(100,100,100,100,100,40),100)
        end = next_binary32(40)
        self.assertEqual(physical_damage_at(end,40,end,80,100,40),100)
        self.assertEqual(physical_damage_at(next_binary32(end),40,end,80,100,40),40)
        self.assertEqual(physical_damage_at(20,30,15,80,100,40),40)

    def test_range_modifier_adds_before_multiplication(self):
        self.assertEqual(adjusted_distance(20,5,.25),31.25)
        self.assertEqual(adjusted_distance(20,5,-2),0)
