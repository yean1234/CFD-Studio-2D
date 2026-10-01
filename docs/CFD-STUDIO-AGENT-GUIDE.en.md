# AI Agent Guide

[한국어](CFD-STUDIO-AGENT-GUIDE.md) · [English](CFD-STUDIO-AGENT-GUIDE.en.md) · [日本語](CFD-STUDIO-AGENT-GUIDE.ja.md)

## Quick start

1. Start CFD Studio and select the project to use
2. Open **Settings → LLM agent → Agent guide → Copy agent prompt**
3. Give the prompt and your task to the agent, then connect it to the Studio tab you are viewing
4. Follow the actions on screen and the **Agent operating** indicator at the top
5. Select **Stop agent** at the top right to pause commands, then **Resume agent** to continue

- Copying the prompt does not connect the browser automatically · Follow your agent tool's connection procedure
- Command names and JSON keys stay the same in every interface language

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
