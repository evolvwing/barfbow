# barfbow

<p align="center">
  <img src="docs/barfbow_logo1.png" alt="barfbow unicorn logo" width="420">
</p>

`barfbow` generates OKLCh color palettes and previews them as a PNG with color-vision simulations, monochrome rendering, named swatches, and OKLCh walk wheels.

![barfbow palette preview](docs/barfbow_preview.png)

## Install

Clone the repository, create a virtual environment, and install the dependencies:

```bash
git clone https://github.com/evolvwing/barfbow.git
cd barfbow
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

You can also install the local command in editable mode:

```bash
python -m pip install -e .
```

After that, run either `python barfbow.py ...` from the repository or the installed `barfbow ...` command.

## Quick Start

Run with the default command:

```bash
python barfbow.py
```

Save a PNG preview:

```bash
python barfbow.py --save-png --png-path palette.png
```

Save both CSV and PNG:

```bash
python barfbow.py --save-csv --csv-path palette.csv --save-png --png-path palette.png
```

The current no-argument default is:

```bash
python3 barfbow.py --N 100 --H-orbits 2.5 --h1 90 --L1 30 --L2 85 --L-cycles 3.5 --c1 85 --deltaC -30 --C-mode L
```

## Parameters

- `--N`: number of colors.
- `--H-orbits`: number of Hue orbits around the 360 degree Hue wheel. Negative values reverse direction.
- `--h1`: initial Hue angle in degrees.
- `--L1` / `--L2`: OKLCh luminance endpoints, as percentages.
- `--L-cycles`: number of luminance cycles from `L1` to `L2` and back.
- `--c1`: initial barfbow chroma percentage, clamped to `0..100`.
- `--deltaC`: chroma change between blocks. Use a number such as `-30`, or use `none` to halve each new block.
- `--C-mode`: chroma progression mode.
- `--save-csv` / `--csv-path`: write the generated table.
- `--save-png` / `--png-path`: save the PNG preview.

## Chroma Scale

barfbow chroma is a friendly `0..100` design scale. Internally, it maps to OKLCh chroma like this:

```text
OKLCh C = barfbow C% * 0.0032
```

So `--c1 100` requests OKLCh `C = 0.32`, which is 80% of an OKLCh `C = 0.4` reference scale. A few examples:

```text
barfbow C 100 -> OKLCh C 0.320 -> 80% of 0.4
barfbow C 85  -> OKLCh C 0.272 -> 68% of 0.4
barfbow C 50  -> OKLCh C 0.160 -> 40% of 0.4
```

Some OKLCh colors are outside what regular sRGB screens can display. When that happens, barfbow keeps the requested `L` and Hue, then reduces the rendered chroma just enough to fit inside sRGB. The terminal and CSV `C%` column still show the requested barfbow chroma value.

## C-mode

`--C-mode` controls when chroma advances from one block to the next:

- `--C-mode L`: shift chroma after each full luminance cycle.
- `--C-mode H`: shift chroma after each full Hue orbit.
- `--C-mode k`: shift chroma every `k` colors, for example `--C-mode 12`. Non-integers are rounded down, negative values are made positive, and values below `1` become `1`.

Chroma values are generated as:

```text
c1, c1 + deltaC, c1 + 2 * deltaC, ...
```

and clamped to the `0..100` range. With `--deltaC none`, they become:

```text
c1, c1 / 2, c1 / 4, ...
```

## Output

The PNG preview includes:

- original color swatches;
- protanopia, deuteranopia, and tritanopia simulations;
- a monochrome row;
- nearby color names from `color_names_meodai.csv`;
- sequence labels;
- OKLCh wheel views showing the full walk and each chroma block.

The color-name dataset is bundled locally in `color_names_meodai.csv` and is derived from the open `meodai/color-names` project.

## License

MIT. See `LICENSE`.

<p align="center">
  <img src="docs/barfbow_logo2.png" alt="barfbow frog wizard logo" width="420">
</p>
