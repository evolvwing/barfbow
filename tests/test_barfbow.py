import re
import unittest

import barfbow


class PaletteTests(unittest.TestCase):
    def test_l_cycle_chroma_ranges(self):
        H, half_period, chroma_ranges, rows = barfbow.build_palette(
            N=10,
            H_orbits=1.0,
            h1=0.0,
            L1=30.0,
            L2=80.0,
            L_cycles=1.0,
            C_values=(80.0, 40.0),
            C_mode="L",
        )

        self.assertEqual(H, 4)
        self.assertEqual(half_period, 4)
        self.assertEqual(len(rows), 10)
        self.assertEqual(chroma_ranges, [("c1", 80.0, 0, 7), ("c2", 40.0, 8, 9)])
        self.assertEqual(rows[0][1:], (30.0, 80.0, 0.0))
        self.assertEqual(rows[8][2], 40.0)

    def test_numeric_c_mode_shifts_every_k_colors(self):
        _, _, chroma_ranges, rows = barfbow.build_palette(
            N=8,
            H_orbits=1.0,
            h1=0.0,
            L1=30.0,
            L2=80.0,
            L_cycles=1.0,
            C_values=(90.0, 60.0, 30.0),
            C_mode="3",
        )

        self.assertEqual(chroma_ranges, [("c1", 90.0, 0, 2), ("c2", 60.0, 3, 5), ("c3", 30.0, 6, 7)])
        self.assertEqual([row[2] for row in rows], [90.0, 90.0, 90.0, 60.0, 60.0, 60.0, 30.0, 30.0])

    def test_c_mode_normalization(self):
        self.assertEqual(barfbow.normalized_C_mode("L"), "L")
        self.assertEqual(barfbow.normalized_C_mode("h-orbit"), "H")
        self.assertEqual(barfbow.normalized_C_mode("-7.9"), "7")
        self.assertEqual(barfbow.normalized_C_mode("0"), "1")

    def test_hex_outputs(self):
        self.assertRegex(barfbow.oklch_to_srgb_hex(50, 80, 120), r"^#[0-9A-F]{6}$")
        self.assertRegex(barfbow.simulate_cvd_hex("#D50062", barfbow.M_PROT), r"^#[0-9A-F]{6}$")
        self.assertRegex(barfbow.simulate_monochrome_hex("#D50062"), r"^#[0-9A-F]{6}$")

    def test_default_command_mentions_canonical_script(self):
        self.assertIn("python3 barfbow.py", barfbow.DEFAULT_COMMAND)
        self.assertIsNotNone(re.search(r"--C-mode L\b", barfbow.DEFAULT_COMMAND))


if __name__ == "__main__":
    unittest.main()
