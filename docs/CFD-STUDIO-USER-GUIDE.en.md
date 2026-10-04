# User guide

- CFD Studio V1.0 · Agent interface v1.4
- [한국어](CFD-STUDIO-USER-GUIDE.md) · [日本語](CFD-STUDIO-USER-GUIDE.ja.md)
- OpenFOAM CFD interface designed to reduce AI-agent operating effort while keeping people in the same visible workflow

## Start

1. Download the complete repository
2. Prepare WSL2 Ubuntu and its user account
3. Run `cfd_studio/설치.bat` for the initial setup
4. Run `cfd_studio/실행.bat` and open the Studio browser page

- Windows 10/11 x64 supported · macOS unsupported
- Windows Python is bundled; WSL installation, dedicated solver builds and GPU setup are separate
- [Installation details](../cfd_studio/README.md) · Preserve existing calculation folders

## CFD

1. **New project**: enter name, project folder and description; select CFD Template and optional preset
2. **Enter Config**: fill required values, review geometry, then save the project
3. **+ CFD Case**: give the run a name and independent Config, termination and goals; select **Save Case**
4. Select the Case → **Add to queue → Start queue**
5. Read Config differences, termination, status, log and result readiness
6. Use **Generate / Update / Open** according to result status

- **Find project** registers a validated existing Studio project folder
- Projects contain independent Cases; a default-preset change affects future Cases only
- Failure pauses the queue; inspect the reason before retrying or skipping
- Queue pause affects the next execution; stopping an active Case is a separate action
- Restart restores records and queue, with subsequent execution paused

## CFD Template and Config

- **CFD Template list → +**: complete the survey, review recommended solvers, select one and generate the input form
- A Template defines solver, Config schema and initial geometry; creating one does not add an execution adapter
- **Installation check** verifies the solver executable, separately from execution support
- Config inputs are on the left, geometry in the center, JSON in the right-hand panel when opened
- Select an element or name tag → name, role, solid/liquid/gas state, transform and properties
- **+ Property → Property type** offers grouped choices filtered by material state and solver
- Numeric properties, XYZ vectors and temperature-property tables have dedicated controls
- Custom property names: double-click, Enter or blur to apply, Esc to cancel
- Base names/types stay fixed; input values remain editable
- **Mesh** contains base spacing and local refinement definitions; calculation support depends on the mesh adapter
- **Import JSON / Export JSON**: Config values plus display schema; use the generated Template JSON as the starting point
- **Save JSON** applies a draft; final Config/Case saving is separate
- **Save as preset** is initially off and creates a separate named preset when selected
- Started Case inputs are read-only; use **New Case from this Config** for changes

## Termination

- Choose physical time or fully saved frame count; check whether the initial frame is included
- Convergence termination remains unavailable until the runner supports a sustained convergence check
- Solver step, output interval, playback speed and termination are separate settings

## Viewer

- Select one Case in the left list; use the circular-arrow control to update visualization readiness
- Readiness gauges describe prepared visualization data, not physical convergence
- **3D Virtual**: choose fields, layers and slices; drag to rotate, wheel to zoom, double-click to reset the camera
- Timeline: choose stored time, playback and speed; Export provides video and image output
- **Data Sheet**: left graph chooses overall mean or specified coordinates, up to three quantities and a graph style
- Right graph: line profile at a saved frame, using start/end coordinates and sample count
- Click or drag the graph to inspect exact displayed X/Y values
- Data Sheet Export provides graph images and CSV; Case-wide CSV export is in CFD
- Line profiles sample the stored-grid sample; interpolation between animation frames does not create new CFD results

## AI agent collaboration

- Give the external agent the [agent guide](CFD-STUDIO-AGENT-GUIDE.en.md) and the task
- Only agent activation commands show **External agent operating** and **Stop agent**
- **Stop agent** immediately hides operation UI, blocks subsequent commands and sends a pause signal
- No human start or resume buttons; continue through a new instruction in the agent conversation
- Active CFD continues; Config review, saving and calculation remain separate

## Errors and storage

- Errors show a code, affected field, details and a remedy; keep the code when requesting assistance
- **Manage project** shows the project folder; settings, Cases, results and caches belong to that project
- Keep original results when relocating a project; active runs prevent relocation
- User projects, results, caches and machine preferences are excluded from Git
- [Manual](CFD-STUDIO-MANUAL.en.md) · [JSON contract](CONFIG-JSON.md) · [Error dictionary](config-error-codes.json)

## Geometry refinement

- **Mesh → Local refinement → Select geometry → Add from geometry**, then enter the finer cell spacing. Use **+ Region** for explicit coordinate bounds. Geometry references follow current dimensions; spheres and cylinders use bounding boxes. Immersion and aligned warehouse generators are connected. The silo surrogate refines selected height intervals and the entire horizontal cross-section to preserve conformal faces. This does not add paper duct geometry or a generic solver adapter. Existing results remain unchanged.
- [Mesh refinement](MESH-REFINEMENT.md)

## Independent mesh size and geometry folders

- Select geometry → **Independent mesh size → On** → enter spacing
- **+ Mesh-only region** adds a transparent refinement volume without materials, walls or physical properties
- Fully contained inner bounds take precedence; conflicting sizes on identical or partially overlapping bounds are rejected
- The current conformal generator rejects a coarser inner region with MESH-R007
- **+ Folder** → enter name → Add; assign each geometry through **Folder**
- Click the folder heading to collapse, double-click to rename, × to remove only the folder
- Save preserves membership and collapsed state; existing results are unchanged
- [Mesh refinement](MESH-REFINEMENT.md)

## Execution adapters and result checks

- After selecting a solver for a new CFD Template, explicitly select a connected schema under **Execution adapter**
- Generic schemas remain disconnected by default; installing a solver alone does not connect execution
- Adapter selection replaces the Config structure; select it before editing and inspect JSON before saving
- The equivalent silo preview shows cylindrical domain and porous extent; detailed ducts, inlet openings and mesh are not shown
- Custom silo dimensions are not limited to optimization candidate lists; original and optimized designs retain separate validation
- Initial-frame exclusion also applies to visualization conversion; legacy results without an explicit policy retain their coverage

- Display-grid statistics exclude empty bins when saved cell centres (`C`) match the grid; genuine zero values remain
- Point and line queries use the nearest occupied display bin; this is distinct from original CFD cells, volume averages or spatial interpolation
- Legacy files without matching centres retain their display-grid lookup; empty-bin detection is not guaranteed


## Warehouse symmetry and mesh planning

- Connected aligned warehouse Config → **Mesh → Computational domain**: select the full domain or one side of the Y midplane
- Enter a positive **Maximum cell edge (m)** · 3 cm is `0.03` · leave blank to retain base spacing and refinement
- **Check mesh plan** reports cell count, planned edge bound, basic array size and cell budget · it does not generate a mesh or start a solver
- Symmetry applies only to the connected model with symmetric loading, initial concentration, material and thermal boundaries · asymmetric flow is excluded
- Exceeding the cell budget blocks generation without silently coarsening the mesh · array size is not total solver memory
- Viewer displays only the computed half and rejects queries in the omitted half · Config geometry editing retains the full physical space
- Local refinement propagates along existing block axes · adaptive mesh refinement and independently coupled fine/coarse 3D halves are unsupported

- [Warehouse symmetry and mesh planning](WAREHOUSE-SYMMETRY.en.md)

## Research-informed mesh transitions

- Config → Mesh → **Use mesh spacing transitions** on/off · when enabled, enter a ratio greater than 1 · disabling preserves the value
- Increase counts on the coarser interval to limit adjacent reference spacings · works with full and symmetry-half domains without coarsening fine input spacing
- **Check mesh plan** reports cell count and X/Y/Z reference ratios · tighter limits can increase cells and computational cost
- Roof Z uses maximum layer height · this does not guarantee all 3D neighbor ratios, wall layers or y+

- [Research-informed mesh transitions](APPLE-STORAGE-METHODS.en.md)
