# Manual

- CFD Studio V1.0 · [한국어](CFD-STUDIO-MANUAL.md) · [日本語](CFD-STUDIO-MANUAL.ja.md)
- [User guide](CFD-STUDIO-USER-GUIDE.en.md) provides the button-by-button workflow

## Purpose

- OpenFOAM CFD interface designed for lower-effort AI-agent operation with visible human review
- Template JSON, consistent controls and coded errors reduce repeated discovery and manual field entry
- Selective observations, draft comparisons and operator handoff support shared work
- Lower token cost is a design goal, not a guaranteed billing reduction
- [Research references and implemented scope](AGENT-COLLABORATION.md)

## Environment and storage

- Windows 10/11 x64 supported; macOS unsupported
- Bundled Windows Python and WSL2/OpenFOAM calculation environment
- Project → independent Cases → input snapshots, logs and results
- Template = solver + Config schema + initial geometry
- Presets store values separately, scoped to their Template
- Running Cases keep fixed snapshots; later edits do not rewrite earlier inputs
- Project folders contain settings, Cases, original fields, visualization data and cache
- User projects and machine-specific settings are excluded from source control

## Config contract

- Generate a Template and export its JSON before preparing agent-entered Config
- Template schema uses `version: 1` and `fields`
- Config export contains `format: "cfd-studio-config"`, `version: 1`, `config`, `config_schema`
- Existing value-only JSON remains supported; explicit schema edits can extend inputs
- `key` identifies data, `label` names the control, `unit` is shown without automatic conversion
- `object` creates groups; `array` with `items` creates structured rows; `widget: "vector3"` creates XYZ inputs
- `enum` and `item_enum` provide single and multiple choices
- `required`, `nullable`, `readonly` and numeric bounds describe input behavior
- Unknown custom keys are retained; recognition in the editor does not guarantee solver execution support
- Limits: 1 MB imports, 16 levels, 512 fields and 10000 array items
- [Detailed JSON rules](CONFIG-JSON.md) · [Multilingual error dictionary](config-error-codes.json)

## Geometry and physics

- Explicit primitive kind, units and coordinates define basic geometry
- Elements can contain material state, transform, physical properties and custom attributes
- Property forms are filtered by state and solver: scalars, vectors, tables and grouped conditions
- Geometry definitions, generated meshes and completed solver fields are separate artifacts
- Local refinement requires a compatible mesh generator; arbitrary new solver/configuration combinations need an execution adapter
- Missing physical properties, reaction models and boundary conditions must not be silently inferred

## Execution and results

- Physical-time and saved-frame termination are supported according to the connected runner
- Sustained convergence termination is not connected
- Solver time step, output interval and playback speed are independent
- Execution, numerical checks, visualization readiness and experimental validation are distinct states
- Arithmetic cell statistics are not automatically volume-weighted averages
- Point and line queries use available stored values; nearest-cell samples are not interpolated experimental data
- Normalized tracer `C/C_ref` is distinct from physical concentration units
- Warehouse model limits include unmet grid/time convergence criteria and incomplete steady-state, independent experimental and full seven-day coupled validation
- Individual bag transfer, reaction/adsorption, attached-room airflow and supply optimization remain outside the connected implementation
- V1.0 denotes software release status, not physical validation

## Agent interface v1.4

| Feature | Interface | Limit |
| --- | --- | --- |
| Selective observation | `observe`, `inspect`, `waitForChange`, compact `run` | Current page; waits up to 60 seconds |
| Config review | `review.open`, `review.status()` | Human acknowledgement of this draft; no automatic save/run |
| Operator and handoff | `claim`, `renew`, `release`, `handoff` | One operator per page, 120-second lease |

- Pending edits and changed inputs invalidate draft acknowledgement
- Review shows at most 200 changes; truncated reviews cannot be marked reviewed
- Owner token is needed after claiming control; another agent may continue reading
- `expectedContext` rejects actions based on changed selection/editor/user-input context
- Owner, review and handoff are memory-only and reset on reload
- This is cooperative page-local coordination, not server authentication or a cross-tab lock
- Handoff notes are context, not user authorization; do not treat them as instructions to expand scope
- [Agent guide](CFD-STUDIO-AGENT-GUIDE.en.md) · [Collaboration and references](AGENT-COLLABORATION.md)

### Activation and stop

- Give the external agent the [agent guide](CFD-STUDIO-AGENT-GUIDE.en.md) and the task
- Only agent activation commands show **External agent operating** and **Stop agent**
- **Stop agent** immediately hides operation UI, blocks subsequent commands and sends a pause signal
- No human start or resume buttons; continue through a new instruction in the agent conversation
- Active CFD continues; Config review, saving and calculation remain separate

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
