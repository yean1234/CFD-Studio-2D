# Repository work

- Preserve existing uncommitted work, user projects, Raw data, results and caches
- Work in this Git checkout; do not copy it to another directory
- Do not terminate user browsers or active CFD calculations
- Stage only the task's changes; exclude user projects and machine settings
- UI follows Template and solver definitions, not project names

## Agent progress

- Report development and operation stages with `cfd_studio/internal/agent_progress.py` as described in `docs/CFD-STUDIO-AGENT-GUIDE.md`
- Check pause before each bounded action; do not continue edits or commands after `PAUSED` until a new explicit user instruction arrives; then use the documented agent-only activate command with the current stop revision
- Use `--wait-visible` before claiming a stage appeared in Studio; file changes alone do not update the interface
- If the progress endpoint or current tab is unavailable, report that limitation in chat; do not claim attachment or restart a live Studio blindly
- Progress reports never replace visible Config review or authorize CFD execution

## Documentation updates

When the user requests “문서 업데이트” (update documentation), treat the following as one task:

- Update the user guide and manual
- Update the AI agent guide, its prompts and supported commands
- Update Korean, English and Japanese documents and in-app help
- Update interface translations for changed labels, messages and descriptions
- Update the repository README, documentation index and relevant installation/release notes
- Check links, UI wording and documented behavior against the current implementation
- Record sources for research-informed features and distinguish design inspiration from measured results
- Include concise verification results and remaining limits; never claim a CFD run occurred unless it did
- Use official third-person wording, concise bullets and plain headings
- Keep personal execution records, project data and unrelated research edits out of the publication
- Commit and upload when publication is already authorized by the user's instructions

## Product purpose

CFD Studio is an OpenFOAM CFD interface designed to reduce the effort and context cost of AI-agent operation while letting people follow and review the same visible workflow. Avoid unsupported claims about token savings, universal solver support or physical validation.

## Code conventions

- Follow [docs/code-conventions.md](docs/code-conventions.md) for naming, module boundaries, data contracts, error handling and verification
- Write concise English source comments explaining intent, units, coordinate transforms or non-obvious constraints
- Keep interface text in the Korean/English/Japanese translation system
- Preserve public JSON keys and execution behavior during comment-only cleanup
- Do not reformat unrelated legacy code or edit third-party comments and license notices

## Development documentation

- Start development handoffs at `docs/development/README.md`
- Map behavior changes to requirement IDs in `docs/development/capabilities.json` and keep status/evidence current
- Update affected contracts, tests, UI guidance, backlog and ADRs in the same change
- Run `python tools/check_development_docs.py`; regenerate the inventory after staging intended new or moved files
