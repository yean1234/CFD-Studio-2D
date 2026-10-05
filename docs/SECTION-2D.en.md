# Immersion Tank 2D Section

[한국어](SECTION-2D.md) · [English](SECTION-2D.en.md) · [日本語](SECTION-2D.ja.md)

- Generates the TMC-49 dual-immersion tank Config as a 2D OpenFOAM case on the **vertical y–z section through a CPU centre**
- Exports per-cell vapour fraction and wall heat flux of the coarse (2–3 mm) CFD in the input format of the bubble-field research pipeline
- The 3D Config remains the single source of geometry, properties and run settings; 2D only adds `case_dimension` and `section_2d`
- 3D defaults and generated files are unchanged; 2D is generated only when selected explicitly

## Research link

- Pipeline: coarse CFD → per-cell `(α, q″)` → correlation bubble specification → synthetic bubble field → heat-flux model check
- The 2D section supplies the **application path** input in the same dimension as the BubbleML 2D reference data
- `coarse_inputs.csv` uses the same columns as `coarse_inputs.csv` of the Cooper gate code (`cooperval.coarsen`)
- Coarse inputs from BubbleML (validation path) remain in the Cooper gate code; this repository produces the tank CFD side only

## Section and axes

| OpenFOAM axis | Tank coordinate | Note |
| --- | --- | --- |
| x | depth z (0 = back wall, 70 mm = front wall) | board z 15–23 mm, CPU face z = 23 mm |
| y | height y | gravity −y · interface 400 mm · open top 800 mm |
| z | one cell (`frontAndBack` = `empty`) | default thickness = `mesh.dx_mm` |

- Section position: `section_2d.x_mm`; empty uses the x centre of `heater.cpus[cpu_index]` (default CPU0, 185 mm)
- Only the y–z section keeps the CPU heated face as a wall; in an x–y front section the CPU face is normal to the plane
- A section that misses every CPU fails before generation; board and coil become solids only where the section crosses them
- Default Config: 6,140 cells · 13 heater faces (3.08 mm) · about 6 s wall time per 0.1 s (serial, environment below)

## Run

```bash
cd tmc49_full_tank
MODE=2D ./Allrun                                  # overrides case_dimension in the Config
python3 tools/build_case.py --dimension 2D --check # validate without writing
python3 tools/export_coarse_2d.py --out export_2d  # export coarse inputs after the run
```

- With `"case_dimension": "2D"` in the Config, `./Allrun` and Studio runs also use the 2D generator
- The bundled Studio Config `immersion_2d` contains these settings
- 2D runs cap parallel ranks at `NP2D_MAX` (default 4) to avoid communication overhead on a few thousand cells
- Measured condition rows: `CONDITION=C3_T20 MODE=2D ./Allrun`
- A later 3D build removes `constant/section2d.json` so no stale 2D grid map remains

## 3D → 2D scaling

| `heat_rule` | Preserves | 2D heater (default Config) | Heat per width |
| --- | --- | --- | --- |
| `local_flux` (default) | CPU heat flux and heated height | 72.0 kW/m² · 40 mm | 2,880 W/m (4.96 × tank-width average) |
| `width_average` | heated height and tank power per width | 14.5 kW/m² · 40 mm | 581 W/m |
| `flux_and_power` | CPU heat flux and tank power per width | 72.0 kW/m² · 8.07 mm (shrunk about the CPU centre) | 581 W/m |

- Width for power per width: `represented_width_mm`; empty uses the tank width of 456 mm
- The CPU face uses `externalWallHeatFluxTemperature` in `flux` mode, independent of the extrusion thickness
- Coil UA target = 3D `UA_target_W_K` × (2D heat per width ÷ 3D heat), keeping the upper-liquid equilibrium `Ta + Q/UA` of 3D
- Coil UA is limited to 90 % of the grid cap, as in the 3D generator; explicit value: `section_2d.coil_UA_W_mK`
- `local_flux` exceeds the 3 mm coil cap (about 52 W/(m·K)); the upper liquid initially warms by about 0.02 K/s and reaches the TMC-49 boiling point of 47 °C after about 730 s
- Use `flux_and_power` or local coil refinement for long thermal equilibrium; the generator prints these numbers on every build

## Exported files

| File | Content |
| --- | --- |
| `fields_2d.h5` (`.npz` without h5py) | `temperature`, `velx`, `vely`, `alpha_vapour`, `alpha_water` (frame, y, x) · solid cells NaN · `mask`, coordinates, nondimensional scales |
| `heater_wall_2d.csv` | per frame and heater face: q″, wall-adjacent cell temperature, CFD wall temperature, vapour fraction, mean lower-liquid temperature |
| `coarse_inputs.csv` | `case_id, coarse_cell, x_m, q_W_m2, vapor_fraction` · time averaged · same columns as the Cooper gate |
| `coarse_inputs_extended.csv` | above plus wall temperature, superheat, subcooling and averaged frame count |
| `export_manifest.json` | section, scaling, coil, fluid values, frames used and assumptions |

- Time average drops the first 30 % of frames (`--skip-initial`); the initial `0` directory is excluded by default
- `x_m`: position along the heater, which is the height y [m] in this case
- `--coarse-dx-mm`: averages heater faces over a coarser length; the partial tail is dropped as in the Cooper gate
- Subcooling: TMC-49 boiling point minus the area-weighted temperature of lower-layer cells with liquid fraction ≥ 0.9
- ASCII and binary fields are read without OpenFOAM; cell order comes from the grid map `constant/section2d.json`

## Verification

- Basis: 2026-10-05 · Linux container · OpenCFD OpenFOAM v2312 · default `immersion_2d` Config
- `blockMesh` and `checkMesh`: Mesh OK · 2 solution directions · 13 `cpu` faces · `frontAndBack` empty
- Serial run to 0.1 s completed; vapour forms in the cells in front of the CPU (peak vapour fraction about 0.6)
- Energy gain of the lower liquid (y < 300 mm) matches the CPU input within 2 % (0.1 s: 0.882 J vs 0.864 J)
- `MODE=2D ./Allrun` with 4 ranks to 0.05 s: decomposition, solve, reconstruction and VTK conversion completed; cell values match the serial run (correlation 1.0)
- 3D generated files are byte-identical to the previous code (default Config and `C3_T20`)
- Unit tests `tests/test_section_2d.py`: 9 passed
- No long run, grid/time convergence, experimental comparison or bubble-statistics validation was performed

## Limits

- The 2D section does not represent flow or bubble spreading along the tank x direction; vapour holdup in the 47 mm gap in front of the board may be overestimated
- The CPU wall temperature is a boundary-model value of about 1,100–1,500 K on 3 mm cells, not a physical wall superheat
- ΔT_sup for the bubble specification must come from Cooper inversion of q″ or a wall-function path; the 3D model uses the same cell size and boundary
- The TMC-49 critical pressure has no Config source, so `p_critical_Pa = null`; confirm a source before computing the Cooper reduced pressure
- Display of the 2D section in the Studio 3D Viewer is unverified; use the exported files for research analysis
- The research_preliminary status of the 3D Config (Lee coefficients, vapour transport properties, interfacial tensions) is inherited unchanged

## Sources

- Design inspiration (not measured results): research notes on coarse-input definitions, one representative value per condition and the BubbleML 2D/3D roles
- Column layout: `coarse_inputs.csv` of the Cooper gate code `cooperval/coarsen.py`
- Array layout: (time, y, x) field layout of the BubbleML dataset — Hassan et al., *BubbleML*, NeurIPS 2023 Datasets and Benchmarks
- Correlation: Cooper, M. G. (1984), *Saturation nucleate pool boiling — a simple correlation*, IChemE Symp. Ser. 86
- Measured values: only the verification results above were run in this repository
