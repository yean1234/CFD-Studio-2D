# Grain Silo Reference Files

This folder retains the source values, DOE tables, and assumption register used to prepare the grain-silo settings. CFD Studio does not create a separate project type or store active projects here.

Grain-silo calculations use the normal CFD Studio `Project` and Raw-data paths. The selected grain-silo config changes the generated OpenFOAM case and available output fields, while project creation, execution, resume, stop, and storage remain shared with every other CFD project.

The source study used ANSYS Fluent 2023 with pressure-velocity coupled calculation, standard wall k-epsilon, and second-order upwind. The independent OpenFOAM v2312 mapping uses the single-phase steady `simpleFoam` solver with SIMPLE, `kEpsilon`, and `explicitPorositySource` with an isotropic `DarcyForchheimer` source in `grainZone`.

The paper records seven mesh-independence levels: 604k, 608k, 666k, 815k, 1.056M, 1.400M, and 1.747M cells. The minimum local reproduction plan checks 604k, 815k, and 1.056M while preserving the full source list in `config.json`.

Source: Chen et al. (2026), BioResources 21(1), 420-438, DOI 10.15376/biores.21.1.420-438.
