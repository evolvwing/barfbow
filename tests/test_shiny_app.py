import inspect
import unittest

import barfbow
from app import (
    APP_CSS,
    DEPENDENT_CONTROL_JS,
    README_PRESETS,
    SHARE_LINK_JS,
    app_ui,
    delta_c_bounds,
    generate_palette_name,
    hue_slider_css,
    make_palette_state,
    n_to_slider_position,
    parse_shared_parameters,
    preview_number_labels,
    preview_html,
    r_palette_script,
    server,
    slider_position_to_n,
)


class ShinyPaletteStateTests(unittest.TestCase):
    def test_default_app_state_uses_cli_palette_math(self):
        state = make_palette_state(
            n=100,
            h_orbits=2.5,
            h1=90,
            h2=270,
            l1=30,
            l2=85,
            l_cycles=3.5,
            c1=85,
            delta_c=-30,
            c_mode="L",
            divergent=False,
        )
        expected = barfbow.build_palette(
            100, 2.5, 90, 30, 85, 3.5, (85, 55, 25, 0), "L"
        )
        self.assertEqual(state.rows, expected[3])
        self.assertEqual(state.chroma_ranges, expected[2])
        self.assertRegex(state.palette_name, r"^[a-z]+_[a-z]+$")
        self.assertEqual(state.palette_name, generate_palette_name(state.rows))

    def test_divergent_state_has_one_shared_peak_for_odd_n(self):
        state = make_palette_state(
            n=101,
            h_orbits=2.5,
            h1=260,
            h2=30,
            l1=50,
            l2=98,
            l_cycles=3.5,
            c1=85,
            delta_c=0,
            c_mode="L",
            divergent=True,
        )
        self.assertEqual(len(state.rows), 101)
        self.assertEqual(state.rows[50][1:], (98.0, 85.0, 260.0))
        self.assertEqual(state.rows[51][3], 30.0)
        self.assertEqual(state.luminance_cycles, 1.0)

    def test_divergent_progression_applies_to_second_half(self):
        additive = make_palette_state(
            n=10, h_orbits=2.5, h1=40, h2=220, l1=20, l2=90,
            l_cycles=3.5, c1=80, delta_c=-20, c_mode="k", divergent=True,
        )
        self.assertEqual(additive.chroma_ranges, [
            ("c1", 80.0, 0, 4),
            ("c2", 60.0, 5, 9),
        ])
        self.assertTrue(all(row[2] == 80.0 for row in additive.rows[:5]))
        self.assertTrue(all(row[2] == 60.0 for row in additive.rows[5:]))
        self.assertTrue(additive.divergent)

        halved = make_palette_state(
            n=10, h_orbits=2.5, h1=40, h2=220, l1=20, l2=90,
            l_cycles=3.5, c1=80, delta_c=None, c_mode="L", divergent=True,
        )
        self.assertEqual(halved.chroma_ranges[1][1], 40.0)

        markup = preview_html(additive, {})
        self.assertIn("Chroma : c1 = 80%", markup)
        self.assertIn("c2 = 60%", markup)
        self.assertEqual(markup.count('class="wheel-card"'), 3)

    def test_live_preview_contains_png_equivalent_sections(self):
        state = make_palette_state(
            n=9,
            h_orbits=1,
            h1=90,
            h2=270,
            l1=30,
            l2=85,
            l_cycles=1,
            c1=85,
            delta_c=-30,
            c_mode="L",
            divergent=False,
        )
        markup = preview_html(state, {0: "Example color"})
        for label in ("Original", "Protanopia", "Deuteranopia", "Tritanopia", "Monochrome"):
            self.assertIn(label, markup)
        self.assertIn("Example color", markup)
        self.assertIn("Palette data · 9 rows", markup)
        self.assertIn('src="barfbow_logo2.png"', markup)
        self.assertIn('alt="Barfbow frog wizard logo"', markup)
        self.assertIn(f'data-palette-name="{state.palette_name}"', markup)
        self.assertIn(f"<strong>{state.palette_name}</strong>", markup)

    def test_palette_names_are_deterministic_and_palette_specific(self):
        rows = [("#112233", 20.0, 30.0, 40.0), ("#AABBCC", 50.0, 60.0, 70.0)]
        self.assertEqual(generate_palette_name(rows), generate_palette_name(list(rows)))
        self.assertNotEqual(
            generate_palette_name(rows),
            generate_palette_name(rows + [("#FFCC00", 80.0, 90.0, 100.0)]),
        )

    def test_low_cycle_preview_hides_chroma_details(self):
        state = make_palette_state(
            n=100,
            h_orbits=2.5,
            h1=90,
            h2=270,
            l1=30,
            l2=85,
            l_cycles=0.5,
            c1=85,
            delta_c=-28,
            c_mode="L",
            divergent=False,
        )
        markup = preview_html(state, {})
        self.assertIn('class="wheels single-wheel"', markup)
        self.assertEqual(markup.count('class="wheel-card"'), 1)
        self.assertNotIn("Initial Chroma :", markup)
        self.assertNotIn("c1 =", markup)

    def test_dense_number_labels_are_thinned_and_rotated(self):
        self.assertEqual(preview_number_labels(37), [4, 9, 14, 19, 24, 29, 34])
        labels = preview_number_labels(1000)
        self.assertEqual(labels[:3], [49, 99, 149])
        self.assertEqual(labels[-1], 999)
        self.assertEqual(len(labels), 20)

        state = make_palette_state(
            n=1000, h_orbits=0.5, h1=280, h2=100, l1=30, l2=85,
            l_cycles=0.5, c1=55, delta_c=-30, c_mode="L", divergent=False,
        )
        markup = preview_html(state, {})
        self.assertIn('class="number-grid number-grid-rotated"', markup)
        self.assertIn('grid-column:1000">1000</span>', markup)
        self.assertNotIn('grid-column:10">10</span>', markup)
        self.assertIn('.number-grid.number-grid-rotated { height:43px; padding-top:4px; }', str(app_ui))
        self.assertIn('transform-origin:left top', str(app_ui))

    def test_divergent_switch_disables_irrelevant_controls(self):
        markup = str(app_ui)
        self.assertIn('id="h-orbits-control"', markup)
        self.assertIn('id="h1-control"', markup)
        self.assertIn('id="h2-control"', markup)
        self.assertIn('id="l-cycles-control"', markup)
        self.assertIn('id="delta-c-control"', markup)
        self.assertIn('id="c-mode-control"', markup)
        self.assertIn('.controls:not(:has(#divergent:checked)) #h2-control', APP_CSS)
        self.assertIn('.controls:has(#divergent:checked) #h2-control', APP_CSS)
        self.assertIn('.controls:has(#divergent:checked) #c-mode-control', APP_CSS)
        self.assertIn('.controls:has(#divergent:checked) #c-interval-control', APP_CSS)
        self.assertIn('id="c-interval-control"', markup)
        self.assertIn('id="chroma-controls"', markup)
        self.assertIn('id="chroma-progression-controls"', markup)
        self.assertIn("syncDependentControls", DEPENDENT_CONTROL_JS)
        self.assertIn("syncChromaInterval", DEPENDENT_CONTROL_JS)
        self.assertIn('divergent.addEventListener("change", sync)', DEPENDENT_CONTROL_JS)
        self.assertIn('cMode.addEventListener("change", syncCMode)', DEPENDENT_CONTROL_JS)
        self.assertIn("slider.update({ disable: disabled })", DEPENDENT_CONTROL_JS)
        self.assertIn('setSliderDisabled("l-cycles-control", "l_cycles", divergent, 1)', DEPENDENT_CONTROL_JS)
        self.assertIn('setSliderDisabled("h2-control", "h2", !divergent)', DEPENDENT_CONTROL_JS)
        self.assertIn('divergent || chromaProgressionIsDisabled()', DEPENDENT_CONTROL_JS)
        self.assertIn('setSelectDisabled("c-mode-control", "c_mode", disabled || divergent)', DEPENDENT_CONTROL_JS)
        self.assertIn('chromaProgressionIsDisabled() || divergent || cMode !== "k"', DEPENDENT_CONTROL_JS)
        self.assertIn('slider.update({ min: -100, max: 100, from: -50, disable: true })', DEPENDENT_CONTROL_JS)
        self.assertIn("syncChromaProgressionSection", DEPENDENT_CONTROL_JS)
        self.assertIn("const disabled = luminanceCycles <= 1 && !divergent", DEPENDENT_CONTROL_JS)
        self.assertIn("chromaProgressionBound", DEPENDENT_CONTROL_JS)
        self.assertIn("change.chromaProgression", DEPENDENT_CONTROL_JS)
        self.assertIn('syncDependentControls(Boolean(document.getElementById("divergent")?.checked))', DEPENDENT_CONTROL_JS)
        self.assertIn('addCustomMessageHandler("barfbow-dependent-controls"', DEPENDENT_CONTROL_JS)
        self.assertIn("registerDependentControlHandler();", DEPENDENT_CONTROL_JS)
        self.assertIn('setInputValue("dependent_controls_ready"', DEPENDENT_CONTROL_JS)
        self.assertIn("window.setInterval(enforceCModeAvailability, 200)", DEPENDENT_CONTROL_JS)
        self.assertNotIn('for (const id of ["c1", "delta_c", "c_interval"])', DEPENDENT_CONTROL_JS)
        self.assertLess(markup.index('id="c1"'), markup.index('id="chroma-progression-controls"'))

        server_source = inspect.getsource(server)
        self.assertIn("def default_divergent_delta_c", server_source)
        self.assertIn('ui.update_slider("delta_c", value=0.0', server_source)
        self.assertIn('if "delta_c" in shared_values', server_source)

    def test_hue_sliders_use_their_selected_display_colors(self):
        css = hue_slider_css(42, 220)
        h1_color = barfbow.oklch_to_srgb_hex(62, 85, 42)
        h2_color = barfbow.oklch_to_srgb_hex(62, 85, 220)
        self.assertIn(f"#h1-control .irs--shiny .irs-bar", css)
        self.assertIn(f"background:{h1_color}!important", css)
        self.assertIn(f"#h2-control .irs--shiny .irs-bar", css)
        self.assertIn(f"background:{h2_color}!important", css)
        self.assertIn(".irs--shiny .irs-handle", css)
        self.assertIn(".irs--shiny .irs-single", css)
        self.assertIn('id="hue_slider_styles" style="display:contents"', str(app_ui))

    def test_controls_include_plain_language_help_and_bounded_luminance(self):
        markup = str(app_ui)
        for explanation in (
            "How many full turns the palette makes around the color wheel.",
            "Where the palette starts on the color wheel.",
            "Brightness at the starting and ending edges of each luminance cycle.",
            "Center brightness of each luminance cycle (or of the palette when divergent mode is on).",
            "Use 0.5 for a sequential palette or 1 for a divergent palette.",
            "How vivid the first chroma block is.",
            "Choose how chroma changes at each new block defined by C-mode:",
            "In divergent mode, the second half of the palette is the next chroma block.",
            "L at each luminance cycle, H at each hue orbit, or k after a fixed number of colors.",
        ):
            self.assertIn(explanation, markup)
        self.assertIn('id="l1" data-skin="shiny" data-min="0" data-max="100"', markup)
        self.assertIn('id="l2" data-skin="shiny" data-min="0" data-max="100"', markup)
        self.assertLess(markup.index('id="l-cycles-control"'), markup.index('id="l1"'))

    def test_readme_presets_match_documented_examples(self):
        markup = str(app_ui)
        self.assertIn(
            "Hike up and down the color domes to generate perceptually uniform color palettes. "
            "Check colorblind simulations to improve accessibility.",
            markup,
        )
        self.assertIn('class="intro-copy"', markup)
        self.assertNotIn('alt="Evolvwing unicorn logo"', markup)
        self.assertNotIn("avatars.githubusercontent.com", markup)
        self.assertIn('src="barfbow_logo1.png"', markup)
        self.assertIn('alt="Barfbow unicorn logo"', markup)
        self.assertIn('class="sidebar-logo"', markup)
        self.assertIn('href="https://www.dnacrobatics.com"', markup)
        self.assertIn('href="https://github.com/evolvwing"', markup)
        self.assertIn("Designed by ", markup)
        self.assertIn("Latest app version: August 20, 2026", markup)
        self.assertIn('class="app-footer"', markup)
        self.assertLess(markup.index('class="sidebar-logo"'), markup.index('class="app-footer"'))
        self.assertIn('id="preset"', markup)
        self.assertNotIn("README presets", markup)
        self.assertIn('<span class="visually-hidden">Palette preset</span>', markup)
        self.assertNotIn("Load a documented example", markup)
        self.assertIn('id="n" data-skin="shiny" data-min="2" data-max="190"', markup)
        self.assertIn('#preset-label { position:absolute!important;', markup)

        self.assertEqual(README_PRESETS["default"]["label"], "Chroma Rainbows · 100 colors")

        categorical = README_PRESETS["categorical"]
        self.assertEqual(
            (categorical["n"], categorical["h_orbits"], categorical["h1"], categorical["l_cycles"]),
            (26, 3.6, 300, 2.4),
        )
        self.assertEqual(categorical["delta_mode"], "halve")

        sequential = README_PRESETS["sequential"]
        self.assertEqual(sequential["label"], "Sequential - Blue-to-Yellow")
        self.assertEqual(
            (sequential["n"], sequential["h_orbits"], sequential["h1"], sequential["l_cycles"], sequential["c1"]),
            (1000, 0.5, 280, 0.5, 55),
        )

        divergent = README_PRESETS["divergent"]
        self.assertEqual(divergent["label"], "Divergent - Blue-Bright-Red")
        self.assertEqual(
            (divergent["divergent"], divergent["n"], divergent["h1"], divergent["h2"], divergent["l1"], divergent["l2"]),
            (True, 301, 260, 30, 50, 98),
        )

        divergent_dark = README_PRESETS["divergent_dark"]
        self.assertEqual(divergent_dark["label"], "Divergent - Blue-Dark-Red")
        self.assertEqual(
            (divergent_dark["divergent"], divergent_dark["h1"], divergent_dark["h2"], divergent_dark["l1"], divergent_dark["l2"]),
            (True, 260, 30, 90, 10),
        )

    def test_number_of_colors_slider_uses_two_speed_scale(self):
        self.assertEqual(slider_position_to_n(2), 2)
        self.assertEqual(slider_position_to_n(100), 100)
        self.assertEqual(slider_position_to_n(101), 110)
        self.assertEqual(slider_position_to_n(190), 1000)
        self.assertEqual(n_to_slider_position(37), 37)
        self.assertEqual(n_to_slider_position(100), 100)
        self.assertEqual(n_to_slider_position(110), 101)
        self.assertEqual(n_to_slider_position(1000), 190)
        self.assertIn('numberOfColors.dataset.twoSpeedBound', DEPENDENT_CONTROL_JS)
        self.assertIn('maximum.textContent !== "1,000"', DEPENDENT_CONTROL_JS)
        self.assertIn("new MutationObserver(syncNumberLabels)", DEPENDENT_CONTROL_JS)
        self.assertIn('if (id === "n")', SHARE_LINK_JS)

    def test_r_download_and_share_link_controls(self):
        markup = str(app_ui)
        self.assertIn('id="download_r"', markup)
        self.assertIn("Download R object", markup)
        self.assertIn('id="generate_link"', markup)
        self.assertIn("Generate link", markup)
        self.assertIn('id="copy-note"', markup)
        self.assertIn("navigator.clipboard.writeText", SHARE_LINK_JS)
        self.assertIn("Copied to clipboard", SHARE_LINK_JS)
        self.assertIn('query.set("palette_name", paletteName)', SHARE_LINK_JS)

        script = r_palette_script(
            [("#112233", 20.0, 30.0, 40.0), ("#AABBCC", 50.0, 60.0, 70.0)],
            "radiante_lisboa",
        )
        self.assertIn('radiante_lisboa <- c(', script)
        self.assertIn('barfbow_palette <- radiante_lisboa', script)
        self.assertIn('"#112233"', script)
        self.assertIn('"#AABBCC"', script)
        self.assertIn('"#112233", "#AABBCC"', script)
        self.assertIn("ggplot2::scale_colour_manual", script)
        self.assertIn("ggplot2::scale_fill_manual", script)

    def test_share_link_parameters_are_bounded_and_typed(self):
        values = parse_shared_parameters(
            "?n=5000&h_orbits=-2.5&h1=42&h2=220&l_cycles=2.5&l1=20&l2=90"
            "&c1=75&delta_mode=halve&delta_c=-50&c_mode=k&c_interval=24&divergent=1"
            "&palette_name=radiante_lisboa"
        )
        self.assertEqual(values["n"], 1000)
        self.assertEqual(values["h_orbits"], -2.5)
        self.assertEqual(values["delta_mode"], "halve")
        self.assertEqual(values["c_mode"], "k")
        self.assertEqual(values["c_interval"], 24)
        self.assertIs(values["divergent"], True)
        self.assertEqual(values["palette_name"], "radiante_lisboa")

    def test_delta_bounds_keep_generated_blocks_inside_chroma_range(self):
        self.assertEqual(
            delta_c_bounds(n=100, h_orbits=2.5, l_cycles=3.5, c1=85, c_mode="L", divergent=False),
            (-28, 4),
        )
        self.assertEqual(
            delta_c_bounds(n=100, h_orbits=2.5, l_cycles=3.5, c1=85, c_mode="L", divergent=True),
            (-84, 14),
        )
        self.assertEqual(
            delta_c_bounds(n=100, h_orbits=0, l_cycles=3.5, c1=85, c_mode="H", divergent=False),
            (-100, 100),
        )

    def test_overview_separator_does_not_reduce_wheel_width(self):
        markup = str(app_ui)
        self.assertIn('.wheel-card:first-child { position:relative; }', markup)
        self.assertIn('.wheel-card:first-child::after', markup)
        self.assertNotIn('border-right:1px solid #d2ccc1; padding-right', markup)


if __name__ == "__main__":
    unittest.main()
