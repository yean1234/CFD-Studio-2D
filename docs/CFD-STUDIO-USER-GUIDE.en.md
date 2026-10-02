# User guide

- CFD Studio V1.0 · Agent interface v1.3
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
- Line profiles sample the nearest saved cell; interpolation between animation frames does not create new CFD results

## AI agent collaboration

- **Settings → LLM agent → Agent guide**: copy the main prompt
- **Workflow guide → Copy workflow prompt**: relevant-state reading, Config review, or control and handoff
- **Config → Review changes**: compare original inputs and the draft; **Reviewed** records human review only
- Changed or pending inputs invalidate that review; saving and running remain separate
- **Return control to user** releases the assigned operator and pauses agent commands; an active solver continues
- Operator, review and handoff are page-local memory; recheck after reload
- [Agent guide](CFD-STUDIO-AGENT-GUIDE.en.md) · [Design references and limits](AGENT-COLLABORATION.md)

## Errors and storage

- Errors show a code, affected field, details and a remedy; keep the code when requesting assistance
- **Manage project** shows the project folder; settings, Cases, results and caches belong to that project
- Keep original results when relocating a project; active runs prevent relocation
- User projects, results, caches and machine preferences are excluded from Git
- [Manual](CFD-STUDIO-MANUAL.en.md) · [JSON contract](CONFIG-JSON.md) · [Error dictionary](config-error-codes.json)
