# Warehouse symmetry and mesh planning

[한국어](WAREHOUSE-SYMMETRY.md) · [English](WAREHOUSE-SYMMETRY.en.md) · [日本語](WAREHOUSE-SYMMETRY.ja.md)

- Connected aligned warehouse Config → **Mesh → Computational domain**: select the full domain or one side of the Y midplane
- Enter a positive **Maximum cell edge (m)** · 3 cm is `0.03` · leave blank to retain base spacing and refinement
- **Check mesh plan** reports cell count, planned edge bound, basic array size and cell budget · it does not generate a mesh or start a solver
- Symmetry applies only to the connected model with symmetric loading, initial concentration, material and thermal boundaries · asymmetric flow is excluded
- Exceeding the cell budget blocks generation without silently coarsening the mesh · array size is not total solver memory
- Viewer displays only the computed half and rejects queries in the omitted half · Config geometry editing retains the full physical space
- Local refinement propagates along existing block axes · adaptive mesh refinement and independently coupled fine/coarse 3D halves are unsupported

## Capabilities

| Feature | Status | Scope |
| --- | --- | --- |
| Coupled velocity, temperature and dilute concentration | Connected | Existing assumption-based warehouse model, no external leakage |
| Porous grain stacks | Connected | Homogenized stack envelopes, individual bag membranes unresolved |
| Full domain and Y symmetry halves | Connected | Aligned warehouse generator, either side of the Y midplane |
| Edge bound and preflight plan | Connected | Before cell allocation, explicit cell budget retained |
| Geometry-owned local refinement | Connected | Axis-projected refinement propagating to neighboring strips |
| Mesh-only regions and folders | Connected | No physical walls, folders organize display only |
| Mirroring omitted results | Not implemented | Only the computed domain is displayed and queried |
| AMR and independent fine/coarse 3D coupling | Not implemented | Distinct from static local refinement |
| Arbitrary axes or CAD symmetry | Not implemented | Installing a solver does not connect these features |
| Experimental validation, full seven-day run, steady-state guarantee | Incomplete | Separate from execution and balance checks |

## Symmetry conditions

- Compute one half with OpenFOAM `symmetryPlane` at the midplane, without creating a wall there
- Validate mirrored stack envelopes and the Y-centered initial Gaussian; uniform materials, temperature, zero initial flow and common exterior thermal conditions are constraints of the current adapter
- Geometric symmetry does not guarantee symmetric flow; asymmetric heat, inlets, openings or symmetry breaking require a full-domain assessment
- Volume and total mass refer to the computed half; distinguish totals from per-volume quantities when comparing domains
- Preserve full Config geometry; record actual `computational_domain.bounds_m` and clipped stack envelopes in results
- Errors: `MESH-S001` unsupported model/domain, `MESH-S002` asymmetric loading, `MESH-S003` asymmetric initial concentration, `MESH-S004` missing initial-field symmetry patch

## Mesh cost

- Supplied nominal example: 78×25m, eaves 7.2m, roof rise 3.5m
- 3cm maximum edge: 808,156,608 cells for the full domain, 404,078,304 for one half
- Five float64 components in the half domain alone require 16.16GB; excludes pressure, turbulence, mesh, matrices, temporary arrays and output
- The large 3cm mesh was neither generated nor executed; resource feasibility remains to be assessed
- 30m and 30cm are different inputs; 30m cells cannot resolve half of a 25m-wide domain
- `maximum_cell_edge_m` is an upper bound; a large value does not remove existing block boundaries or base refinement
- Axis propagation preserves conformal block faces; even a small observation box can increase the cell count substantially

## Verification

- OpenFOAM v2312 `blockMesh`, `checkMesh` and coupled solver executed on 1,860 full-domain cells and 930 cells for each half
- One-second development check, three stored frames per calculation, execution checks passed
- Maximum full/half difference at common points and saved times: velocity below 2.67×10⁻⁷ m/s, temperature below 3.36×10⁻⁸ K, concentration below 4.50×10⁻¹⁵ kg/m³
- Relative mass-balance error below 8.68×10⁻¹⁵; this short symmetry check does not establish grid/time convergence, experimental validity or fumigation efficacy
- Mesh planning uses standard Windows Python without NumPy; solver calculations retain the WSL numerical environment
- Reproduce input, volume, initial inventory and budget checks with `python -m unittest discover -s tests -p "test_warehouse_symmetry.py"`

## JSON

```json
{"porous_mesh": {"domain_mode": "symmetry_y_min", "maximum_cell_edge_m": 0.03}}
```

- Partial fields to merge into an actual Template export, not a complete Config · retain `kind`, `base_max_spacing_m`, `refinement` and `maximum_cells`

## References

- [OpenFOAM symmetryPlane](https://doc.openfoam.com/2306/tools/processing/boundary-conditions/rtm/constraint/symmetryPlane/)
- [OpenFOAM blockMesh](https://www.openfoam.com/documentation/user-guide/4-mesh-generation-and-conversion/4.3-mesh-generation-with-the-blockmesh-utility)
- [Dornier et al., Mean Mesh Adaptation for Efficient CFD Simulations with Operating Conditions Variability, 2024](https://arxiv.org/abs/2412.01274)
- The cited condition-sampled mean-error adaptation is background research; its algorithm is not implemented here and does not validate an arbitrary ultrafine/ultracoarse half-domain split

## Research-informed mesh transitions

- [Research-informed mesh transitions](APPLE-STORAGE-METHODS.en.md)

- [Alexander, Jakhar & Dasgupta (2024), Scientific Reports 14, 25402](https://doi.org/10.1038/s41598-024-76385-y)
- [Alexander, Jakhar & Dasgupta (2025), Scientific Reports 15, 11534](https://doi.org/10.1038/s41598-025-95886-y)
