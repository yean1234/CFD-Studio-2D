# Chen et al. (2026) Independent Reproduction Assumptions

This directory is an independent OpenFOAM reproduction workspace. It is not an author-provided case and must not be described as an exact reproduction of Chen et al.

## Published inputs used directly

- Silo outer diameter 1.0 m and total height 1.4 m.
- Cylindrical storage diameter 0.8 m and height 1.2 m.
- Grain height 1.0 m and central lower duct diameter 0.300 m.
- Inlet speed 3 m/s, rho 1.177 kg/m3, mu 1.85e-5 Pa s, nu 1.5718e-5 m2/s.
- Corn porous resistance: d=1.22569631e7 1/m2 and f=3797.1 1/m.
- Source numerics: ANSYS Fluent 2023, pressure-velocity coupled algorithm, standard wall k-epsilon, and second-order upwind.

## Independent OpenFOAM mapping

- Independent OpenFOAM mapping: OpenFOAM v2312 simpleFoam/SIMPLE with kEpsilon and an isotropic Darcy-Forchheimer grain cellZone. This is not a published source-solver setting.

## Inputs intentionally left unset

- Cone angle and cone height.
- Recirculation duct section, length, port count per layer, layer locations, and circumferential positions.
- Lower outlet locations and fan flow split.
- The physical inlet reference area for the reported 3 m/s.
- CV detection surfaces are published as one YX section and ZX sections at axial Y=0.01, 0.5, and 0.6 m. The paper does not publish the exact transverse coordinate of the YX section, interpolation method, surface extent, or number and distribution of detection points. CFD Studio maps the paper axial Y direction to model z and reports nearest-cell equivalent sections separately from whole-volume diagnostics. The published statistic uses detection-point speed and sample standard deviation with denominator n-1.
- Boundary-layer mesh, mesh-quality limits, turbulence inlet quantities, and convergence thresholds.

The case builder preserves these fields as null in `config.json`. It creates only the published material/porosity dictionaries and DOE folders. It does not create operational initial fields or solver-control dictionaries until reviewed mesh and solver contracts are supplied. OpenFOAM mapping choices are recorded separately from published Fluent settings. This prevents invented geometry or numerical values from producing a result presented as paper data.
