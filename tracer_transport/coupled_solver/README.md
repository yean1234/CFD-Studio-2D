# warehouseBuoyantFoam

Based on **OpenFOAM v2312 buoyantBoussinesqPimpleFoam** (OpenCFD / OpenFOAM Foundation). Original copyright notices are retained. This solver, including the added headers, is licensed under **GPL-3.0-or-later**; see `COPYING`. OpenFOAM itself is an external build dependency.

Upstream source: https://develop.openfoam.com/Development/openfoam/-/tree/OpenFOAM-v2312/applications/solvers/heatTransfer/buoyantBoussinesqPimpleFoam

Changes:

- `UEqn.H`: cellwise linear Brinkman resistance `drag*U`.
- `TEqn.H`: effective bulk heat capacity/conductivity, local thermal equilibrium, and discretized boundary energy accounting.
- `CEqn.H`: conservative passive species transport using the corrected volume flux, porosity storage, temperature-dependent molecular diffusivity and free-air turbulent diffusivity.
- `diagnostics.H`: inventory, energy, velocity, temperature, concentration and continuity diagnostics.
- The pressure correction retains the upstream PIMPLE algorithm. This case uses a static mesh; moving mesh and restarts have **not** been validated for the added porous fields.

Equations (U: superficial velocity; phi: conservative face volume flux):

```
div(U) = 0
dU/dt + div(U U) = viscous/RANS stress - grad(p) + thermal buoyancy - nu/permeability * U
heatCapacityRatio * dT/dt + div(U T) = div(alphaEffective * grad(T))
eps * dC/dt + div(U C) = div(DEffective * grad(C))
```

`heatCapacityRatio = eps + (1-eps)*(solid volumetric heat capacity)/(air volumetric heat capacity)`.
`alphaEffective = bulk conductivity/(air volumetric heat capacity) + freeGas*nut/Prt`.
`DEffective = diffusionFactor*D(T) + freeGas*nut/Sct`.

The standard k-epsilon closure is used without a calibrated porous turbulence model or extra buoyancy production term. This is a Darcy–Brinkman penalty approximation; inertial porous drag, bag membranes, reaction, sorption, leakage, moisture, solar radiation and solutal buoyancy are omitted. None of the provisional rice/envelope parameters are claimed to be empirical measurements. No dose control or optimization is implemented.

Run the tests in `tracer_transport.verify_coupled` before interpreting the pilot. These validate restricted analytical laminar limits, not the warehouse turbulence model.
