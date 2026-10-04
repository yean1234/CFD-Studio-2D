# Research-informed mesh transitions

[한국어](APPLE-STORAGE-METHODS.md) · [English](APPLE-STORAGE-METHODS.en.md) · [日本語](APPLE-STORAGE-METHODS.ja.md)

## Prior research

- The 2024 paper's Methods use a symmetry half-domain, homogenized porous crates, near-wall refinement with growth ratio 1.2, and a grid independence study
- The 2025 follow-up uses a symmetry half-domain to compare pallet heights
- Both concern apple cooling; their properties and validation do not establish bagged-grain fumigation transport or reaction behavior

- [Alexander, Jakhar & Dasgupta (2024), Scientific Reports 14, 25402](https://doi.org/10.1038/s41598-024-76385-y)
- [Alexander, Jakhar & Dasgupta (2025), Scientific Reports 15, 11534](https://doi.org/10.1038/s41598-025-95886-y)

## Implementation

- Config → Mesh → **Axis interval spacing ratio limit** · enter a value greater than 1, or leave blank to disable
- Increase counts on the coarser interval to limit adjacent reference spacings · works with full and symmetry-half domains without coarsening fine input spacing
- **Check mesh plan** reports cell count and X/Y/Z reference ratios · tighter limits can increase cells and computational cost
- Roof Z uses maximum layer height · this does not guarantee all 3D neighbor ratios, wall layers or y+
- Generated mesh coordinates use 16-digit output precision with existing check tolerances retained · existing Case inputs are not changed automatically

```json
{"porous_mesh": {"max_axis_spacing_ratio": 1.2}}
```

- Partial fields to merge into an actual Template export, not a complete Config · 1.2 is an example for review, not a validated grain-warehouse default

## Scope

- Independent static axis-interval transition control, not a reproduction of the paper mesh generator
- Uniform subdivision within each block; increase neighboring block counts, with simultaneous updates to avoid directional bias
- Warehouse k-epsilon remains unchanged; the paper SST k-omega, wall inflation and y+<1 control are not connected by this change
- Automatic detailed bag/RVE calculation and resistance transfer to the full model are not implemented
- AMR, independent fine/coarse 3D interfaces and an ultrafine/ultracoarse half split are not implemented
- MESH-R010: invalid ratio · MESH-R011: transition did not settle within 512 passes
- Symmetry assumptions and experimental validation require separate assessment; apple properties are not copied to existing projects

## Checks

- Development warehouse half-domain: 930 baseline cells → 40,986 with ratio 1.2
- Planned X/Y/Z maximum ratios 1.150 / 1.167 / 1.188 · not a guarantee of fewer cells or lower cost
- OpenFOAM v2312 checkMesh passed; volume retained at 8,726.25m³
- One-second, three-frame velocity/temperature/concentration execution checks passed; relative mass balance approximately 9.16e-14
- Does not establish a 3cm research run, paper reproduction, grid convergence or experimental validation
