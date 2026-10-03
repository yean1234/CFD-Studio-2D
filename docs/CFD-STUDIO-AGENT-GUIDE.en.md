# AI Agent Guide

- CFD Studio V1.0 · Agent interface v1.3

[한국어](CFD-STUDIO-AGENT-GUIDE.md) · [English](CFD-STUDIO-AGENT-GUIDE.en.md) · [日本語](CFD-STUDIO-AGENT-GUIDE.ja.md)

## Visible progress

- File inspection, code edits and tests require explicit progress reports; changing files alone does not update the interface
- Run `cfd_studio\Setup\Python312\python.exe cfd_studio\internal\agent_progress.py` from the repository root
- Create an ignored `output` directory if missing; `start` requires a new `--session-file output\agent-session.json` and never overwrites it
- Before work: `start --session-file output\agent-session.json --mode development --stage review --detail "Reviewing inputs" --wait-visible`
- Before each step: `update --session-file output\agent-session.json --stage test --detail "Running relevant tests" --wait-visible`
- Read `status` between bounded actions; update at least every 60 seconds during longer work
- Finish: `finish --session-file output\agent-session.json --stage completed --detail "Tests passed; CFD not run"`
- Modes: `development` for source work, `operation` for Studio UI work
- Stages: `review`, `draft`, `debug`, `test`, `ui`, `waiting`, `blocked`; finish with `completed` or `failed`
- Keep details brief and in the user's language; never include credentials or complete Config values
- Exit `3` or `PAUSED`: stop further edits and actions, read status only, wait for the user's Resume
- Exit `2`: inspect the error; exit `4`: no visible-tab render receipt, do not claim it appeared
- `displayed: true` acknowledges rendering by a visible Studio tab; it does not prove intended-tab attachment, user review or permission to calculate
- After 120 seconds without updates: Agent disconnected; HTTP failure: Progress connection lost; waiting, blocked and terminal states do not blink
- Progress, the last 20 entries and pause live in server memory, survive page reload, and reset on server restart
- Pause cannot forcibly suspend an external LLM, in-flight command or solver; the controller checks it between bounded actions
- This transport reports status only; use the existing visible-tab commands for Config, saving and CFD execution
- Updates are not injected into running servers or tabs; preserve unsaved edits and running calculations before restarting Studio and reloading the page
- [Progress error codes](AGENT-PROGRESS.md)

## Connection checks and recovery

1. Check whether the automation tool starts
2. Check Studio HTTP and agent script responses
3. Read `CFDAgent.describe()` and `CFDAgent.observe()` in the user's visible tab
4. Match the returned session, project and Case to the screen before acting

| Check | Evidence | Does not prove |
| --- | --- | --- |
| Automation host | Successful tool call | Studio access |
| Server and scripts | `agent_diagnostics.py` | Current-tab access or user review |
| Current tab | Tab-local describe/observe and screen comparison | Permission to save or calculate |
| Applied draft | Reread JSON, notices and 3D | Saved Case or completed CFD |

- Diagnostic `stages`: automation_host / studio_http / agent_scripts / current_tab
- HTTP success still reports `current_tab: not_checked`; exit code 0 does not mean tab attachment
- Port follows `CFD_STUDIO_PORT`, otherwise `studio_config.json`; run diagnostics in the Windows execution environment
- `APP-A001`: external automation workspace error before Studio access; follow bounded tool recovery, then stop unchanged retries
- Changing the local workspace is a recovery hypothesis, not a guaranteed fix
- `APP-N001`: server access failed; distinguish starting a stopped server from restarting a running one
- Do not stop a healthy server, user browser or solver to repair an external tool failure
- If a question widget is missing, repeat the essential question in ordinary chat; no reply is not review or authorization

### Operation and development

- Normal operation uses public CFDAgent commands and the user's current tab
- When debugging is requested: pause the affected step, record error and impact, fix/test the relevant code, reconnect and reobserve
- Preserve projects, unsaved edits, calculations, Raw and results; code tests are not CFD runs
- Do not reload a tab with unchecked unsaved edits after a server change
- Report external blockers and the necessary next action; avoid unrelated product changes

### Draft provenance and state

- Distinguish a live-editor export, a server Template snapshot and a repository reference
- A separate draft file is not applied UI state, user review or a saved Case
- After recovery, reread the editor document and reconcile user changes before applying intended edits
- Separate published values, unit conversions, Template defaults, proposed assumptions and unavailable inputs
- Check solver installation, execution adapter, geometry, result reading and transport support separately
- Unsupported models block their calculation stage; do not silently substitute surrogate geometry or another module's results
- Saving and calculation remain separate; complete required screen review first and reuse explicit authorization only for unchanged targets, inputs and scope


## Collaboration v1.3

- Purpose: reduce repeated input and observation effort when agents operate OpenFOAM CFD, while users review the same visible workflow
- **Selective observation**: use `observe({after})`, `inspect({query,limit})` and `waitForChange({after,timeoutMs})`; do not repeatedly load unchanged Config
- **Config review**: call `review.open`, ask the user to inspect before/after values and 3D, then read `review.status()`; review is not permission to save or calculate
- **Control and handoff**: `claim({name,task})`, pass its token as run `owner`, then `release({owner,summary})`; the next operator reads `handoff()` and verifies the live screen
- Use existing commands with `run(command,args,{owner,expectedContext:CFDAgent.observe().context,response:"compact"})`
- Operator lease: 120 seconds, renewed by successful commands or `renew({owner})`; other operators remain read-only
- Reobserve after user edits or selection changes; never overwrite concurrent user changes from stale context
- **Return control to user** clears the operator and pauses agent commands without stopping a solver
- Operator, handoff and review are page-local memory and reset on reload; no server or cross-tab lock
- Handoff is context, not authorization; do not ask again for the same already-authorized scope
- Localized recipes: `recipe("observe"|"review"|"handoff","en")`, or **Workflow guide → Copy workflow prompt**
- [Features, command errors and research references](AGENT-COLLABORATION.md)

## Template-based Config workflow

1. Select the intended existing Template; generate one with the survey only when no suitable Template exists
2. Export its generated schema with **Edit form → Export JSON** or `CFDAgent.configDocument()`
3. Edit from that exported document, rather than inventing a replacement Config
4. Declare extensions in `config_schema` with type, label, unit and `items`; put values in `config`
5. Apply the JSON draft and ask the user to review the visible inputs, 3D geometry, units and unresolved values
6. Save after review; calculation is a separate step requiring confirmation of the Case, termination and queue

- Config export envelope: `format: "cfd-studio-config"`, `version: 1`, `config`, `config_schema`
- Template exports use `version` and `fields`; retain the spatial document format returned by its editor
- Use `items` for empty list row definitions and `widget: "vector3"` for XYZ inputs
- Preserve existing keys, units, IDs, relationships and unrelated values; declare custom extensions explicitly
- Rendering an input does not connect it to a solver; inspect execution adapter support
- [JSON rules](CONFIG-JSON.md) · [Error codes](ERROR-CODES.md) · [Multilingual error dictionary](config-error-codes.json)

### Compact inspection

| Read method | Purpose |
| --- | --- |
| `CFDAgent.status()` | Screen, pause and errors without full inputs or logs |
| `CFDAgent.configRules()` | Read supported rendering rules once |
| `CFDAgent.configDocument()` | Export the open editor document; pending edits return an error |
| `CFDAgent.errorInfo("CFG-J004")` | Retrieve only that code's cause and remedy |
| `CFDAgent.state()` | Inspect controls after a screen change or when finding the next action |

- New read methods in interface v1.3; existing commands remain compatible
- Use `code`, `path` and `action` to fix the affected input; avoid inspecting the entire source or blindly repeating actions
- `APP-X001` means an unclassified error; retain its details and investigate
- Honor pause signals and the existing wait workflow; never simulate the user's Resume action

## Result review

- Select one Case in Viewer, then switch between **3D Virtual / Data Sheet**
- Left Data Sheet panel: whole-domain mean or point time series, up to three quantities
- Right panel: line profile at a saved frame, with start/end coordinates and sample count
- Line values use the nearest saved cell; do not describe them as spatial or temporal interpolation
- Enter JSON for the whole Config, complete spatial document or major section; individual properties do not each have a JSON button
- Creating a Template does not add an execution adapter; inspect the actual execution connection


## Quick start

1. Start CFD Studio and select the project to use
2. Open **Settings → LLM agent → Agent guide → Copy agent prompt**
3. Give the prompt and your task to the agent, then connect it to the Studio tab you are viewing
4. Follow the actions on screen and the **Agent operating** indicator at the top
5. Select **Stop agent** at the top right to pause commands, then **Resume agent** to continue

- Copying the prompt does not connect the browser automatically · Follow your agent tool's connection procedure
- Command names and JSON keys stay the same in every interface language

## JSON entry and guided review

- Agent interface **v1.1** provides dedicated commands for Config and spatial JSON
- Submit JSON in bulk instead of filling individual fields · Review the resulting Config and 3D preview on the same screen
- Uses the current tab's editor and validation · No direct file changes or separate server connection required

| Stage | Agent action | User review |
| --- | --- | --- |
| 1 | Identify project, Case, CFD Template, solver and task | Confirm the target and analysis purpose |
| 2 | Read the actual Template schema and spatial JSON | Supply missing dimensions, properties and conditions |
| 3 | Prepare and apply spatial JSON to the draft | Check the 3D shape, region names, units and solid/liquid/gas assignments |
| 4 | Prepare the remaining Config JSON using the actual schema | Check each setting's meaning, value, unit, basis and unresolved inputs |
| 5 | Summarize changes and ask whether to save | Wait for confirmation before final Config/Case saving |
| 6 | Explain termination, output intervals and the complete queue order | Wait for confirmation before queueing and starting calculations |
| 7 | Inspect logs, Case status and results | Report completion, failure and validation status |

- Explain each stage's result before proceeding · A request to prepare Config does not authorize calculation
- User review is an agent workflow instruction, not a program-enforced approval check
- **Save JSON** applies a draft · It is separate from final Config saving, Case saving and queue start
- For a read-only execution snapshot, use **New Case from this Config** to edit a copy

### Dedicated commands

| Command | Function | Arguments |
| --- | --- | --- |
| `config.json.open` | Open Config or the complete spatial JSON document | `scope: "config"` or `"geometry"` |
| `config.json.fill` | Populate the JSON edit buffer in bulk | `value`: JSON string · Maximum 1 MB |
| `config.json.apply` | Validate and apply JSON to the draft | None |

- `CFDAgent.state().json` exposes `scope`, `title`, `value`, `readonly` and `dirty` · Returns `null` when no JSON pane is open
- Open the intended Config editor before `config.json.open` · These commands do not choose a project or Case
- Copy the actual JSON and change only the intended values · Preserve names, types, units, identifiers, relationships and metadata
- A Template schema with `version` and `fields`, a Config value object and a complete spatial document are different formats · Keep the format you read
- Ask the user for missing schema information or required inputs · Do not invent missing values
- Use Config JSON for properties or calculation conditions outside the spatial document
- An `apply` receipt with `dispatched` does not confirm acceptance · Check `notices`, reread JSON and inspect the 3D preview
- Correct syntax or type errors in the same draft · Read-only and pause restrictions remain effective
- `apply` does not finalize a save or start CFD

### JSON example

- Read the complete spatial document from an already open Config editor

```javascript
await CFDAgent.run('config.json.open', { scope: 'geometry' });
const current = CFDAgent.state().json;
if (!current || current.readonly) throw new Error('Editable JSON required');
const document = JSON.parse(current.value);
// Edit document using the actual schema and user-provided dimensions/conditions
```

- Submit the edited document through this function, then ask the user to inspect the screen

```javascript
async function applyDraft(document) {
  const fill = await CFDAgent.run('config.json.fill', {
    value: JSON.stringify(document, null, 2)
  });
  if (fill.status !== 'dispatched') return fill;
  return await CFDAgent.run('config.json.apply');
}
// Inspect the returned state.json and state.notices
// Do not finalize, queue.add or queue.start before user confirmation
```

- For general Config, use `scope: "config"` and repeat the process with the newly read document
- Ask the user to check the target shape, dimensions and units, materials and properties, initial/boundary conditions, time step, termination, output interval, changes and assumptions

## Requirements

- Start Studio using `cfd_studio/실행.bat`
- Supported platform: Windows 10/11 x64 · macOS is not supported
- Use an LLM agent with a browser interaction tool
- Connect to **the same CFD Studio tab the user is viewing**
- Commands sent in another browser window only change that window
- Install the LLM tool, sign in and establish the browser connection through the agent tool
- Studio does not expose an HTTP/MCP command server or enable a remote debugging port
- Before running CFD, check solver installation, Studio execution support, Config, termination conditions and the queue

## Agent prompt

- Open **Settings → LLM agent → Agent guide** at the top right
- Select **Copy agent prompt** and paste it into the agent conversation
- If clipboard access is unavailable, select **Show guide** and copy the text manually
- **Alt + Shift + A** opens or closes the guide panel
- The prompt contains preparation steps, commands, input rules and checks for execution results
- The generated agent prompt is in English · Interface buttons support Korean, English and Japanese
- The prompt asks the agent to report in the user's language and preserve user-defined names and Config values

## On-screen controls

| Control or indicator | Function |
| --- | --- |
| Blue outline | Highlights the button or input being operated |
| **Agent operating** at the top center | Blinks during agent activity · Remains static with reduced motion enabled |
| **Stop agent** at the top right | Blocks subsequent commands and sends a pause signal |
| **Resume agent** in the same position | Sends a resume signal |
| Panel at the bottom right | Shows the current command and recent delivery records |
| **Pause commands** / **Allow commands** | Pauses or resumes command acceptance |
| **×** | Hides the guide panel without pausing commands |

- Commands act on the actual project, Case, Config and Viewer controls
- Pausing does not cancel an action already delivered or stop a running CFD calculation
- If the user changes a selection or input, the agent must read the current screen again before continuing
- The following screenshots show the Korean interface · Control positions are shared across languages

![Agent activity indicator](assets/agent-controls/banner.png)

![Agent guide panel](assets/agent-controls/guide.png)

## Commands

- Use `window.CFDAgent` through the JavaScript evaluation feature of the connected browser tab
- Operate existing screens without editing Studio source or project files
- `CFDAgent.describe()`: interface version, command list and prompt
- `CFDAgent.state()`: current project, Case, queue, screen, inputs, buttons, notices and log
- `CFDAgent.prompt()`: the prompt to copy
- `CFDAgent.history()`: up to 100 recent command records
- `CFDAgent.waitForResume({timeoutMs:30000})`: wait for user resume · Maximum wait per call is 60 seconds
- `CFDAgent.finish()`: clear the activity indicator while preserving a user pause
- `await CFDAgent.run(command, args)`: operate a screen control
- The guide panel also accepts JSON through **Command input → Run command**

```javascript
// Read the current screen and real project identifiers
const state = CFDAgent.state();

// Example: select the first listed project only if it is the requested one
const project = state.workspace?.projects?.[0];
if (!project) throw new Error('No project available');
await CFDAgent.run('project.select', { id: project.id });

// Open Config for the selected Case, then inspect current controls
await CFDAgent.run('config.open');
CFDAgent.state().controls;
```

| Command | Action | Arguments |
| --- | --- | --- |
| `cfd.open` | Open CFD | None |
| `viewer.open` | Open the selected Case in Viewer or prepare its results | None |
| `project.select` | Select a project | `id` |
| `project.find` / `project.new` | Open Find project / New project | None · Use from the CFD screen |
| `project.manage` | Open project management | None |
| `case.select` | Select a Case in the current project | `id` |
| `case.new` | Open Config for a new Case | None |
| `config.open` | Edit or view Config | None |
| `template.new` | Open a new CFD Template | None |
| `queue.add` | Add the selected draft to the queue | None |
| `queue.start` | Start or resume the entire displayed queue | None |
| `queue.pause` | Pause before the next calculation | None |
| `case.stop` | Stop the selected running Case | None |
| `case.recovery` | Open failure details and recovery options | None |
| `queue.skip` | Skip the failed Case in the queue | None |
| `result.open` | Use the Create / Update / Open result button | None |
| `result.refresh` | Reload Viewer results | None |
| `result.csv` | Export all CSV data for the selected Case | None |
| `viewer.mode` | Select Viewer mode | `mode: "3d"` or `"data"` |
| `settings.open` | Open Settings | None |
| `ui.click` | Click a button or expand/collapse a section | `target` |
| `ui.fill` | Enter a string in an input | `target`, `value` |
| `ui.select` | Change a select control | `target`, `value` |
| `ui.check` | Set a checkbox or radio selection | `target`, `checked` |

## Entering values

- Read `target`, `label`, `value`, `options`, `disabled` and `readonly` from `state().controls`
- Read the controls again after changing dialogs or sections
- Do not reuse a `target` after its control has been replaced
- Pass numbers as strings: `value: "0.01"`
- For a select control, use `options[].value`, not its displayed label
- Invalid number syntax is rejected · Correct range errors shown beside the input
- Use the browser tool's file upload feature for file inputs
- Saved execution snapshots are read only · Use **New Case from this Config** to edit a copy
- Filling an input does not save it · Use the screen's **Save** button
- Do not invent geometry, material properties or boundary conditions

```javascript
const field = CFDAgent.state().controls.find(item => item.label === 'Project name');
if (!field) throw new Error('Read the current controls first');
await CFDAgent.run('ui.fill', { target: field.target, value: 'Heat transfer comparison' });
```

- Labels depend on the interface language · Read the actual label before selecting a control
- JSON example for the guide panel

```json
{"command":"config.open","args":{}}
```

## Checking results

- `status: "dispatched"` means the UI action was delivered
- **It does not confirm that saving, exporting or a CFD calculation succeeded**
- For asynchronous operations, check notices, the queue, Case status and logs using `state()`
- Inspect an error before continuing · Do not resend a timed-out action automatically
- Start, retry or stop calculations only within the user's requested scope
- Starting the queue can affect Cases from other projects · Check the complete queue first
- Report visualization readiness, numerical checks, calculation completion and experimental validation separately

| Status or error | Response |
| --- | --- |
| `rejected` | Inspect the returned `error` |
| `BUSY` | Inspect the current action, then issue commands sequentially |
| `PAUSED` | Wait for the user to resume |
| `STALE_TARGET` / `CONTROL_NOT_VISIBLE` | Read the screen again and select a current control |
| `CONTROL_DISABLED` | Check the requirements displayed on screen |
| `INVALID_INPUT` / `INPUT_INVALID` | Correct the input format or range |

## Pause and resume

- Pausing sets `state().paused` to `true` and emits `cfd-agent-pause`
- Resuming emits `cfd-agent-resume` · Signals include the session, sequence number and time
- Read the state before every command · Wait after a pause signal or a `PAUSED` response
- Handle the wait in the agent's browser controller

```javascript
while (CFDAgent.state().paused) {
  const signal = await CFDAgent.waitForResume({ timeoutMs: 30000 });
  if (signal.status === 'resumed') break;
}
// Recheck the screen and any user edits before choosing the next action
const current = CFDAgent.state();
```

- Call `CFDAgent.finish()` when the requested work is complete
- If the agent is unresponsive, **Stop agent** blocks further interface commands
- Studio cannot suspend the external LLM process itself · The connected controller must honor the pause signal
- Previously delivered actions and CFD calculations continue · Use the Case's calculation stop control to stop CFD
- Do not bypass a pause by opening another tab, reloading, calling internal UI functions or resuming automatically

## Scope and limitations

- Commands use the same tab's existing controls and input events, including validation, saving and snapshot rules
- Concurrent commands are rejected · No automatic resending
- State inspection includes Config values · Check which information will be shared with the connected agent
- Activity records contain commands, target identifiers and delivery status, not input values
- Records are held in tab memory and reset on reload
- The session identifier changes on reload · Previous control identifiers must not be reused
- If JavaScript evaluation is unavailable, an agent can use a screen interaction tool to operate the same buttons
- Browser connection, file uploads, native folder selection and operating system permissions depend on the browser and agent tool
- If `CFDAgent` is unavailable, preserve unsaved edits before reloading · Restart Studio only when idle, without stopping a running solver or closing the user's browser

## Connection diagnostics

- Use `agent_diagnostics.py` to separate Studio HTTP failures from agent-host workspace failures
- HTTP success does not prove attachment to the user tab; do not restart the browser or calculation
- `APP-A001`: host workspace URI failure · `APP-A002`: port/script issue · `APP-N001`: HTTP failure
- [Commands and silo execution limits](silo-agent-debug-20261003.md)

```bat
cfd_studio\Setup\Python312\python.exe cfd_studio\internal\agent_diagnostics.py
```

- Launching again preserves an existing Studio server and opens its address · A conflicting service returns APP-A002 · No automatic port switching or process termination
