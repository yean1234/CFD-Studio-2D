# Repository work

- Preserve existing uncommitted work, user projects, Raw data, results and caches
- Work in this Git checkout; do not copy it to another directory
- Do not terminate user browsers or active CFD calculations
- Stage only the task's changes; exclude user projects and machine settings
- UI follows Template and solver definitions, not project names

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
