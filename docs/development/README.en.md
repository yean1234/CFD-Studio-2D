# Developer documentation

- 2026-10-05 · V1.0 · baseline `e861572`
- The detailed technical baseline is maintained in Korean. This English entry point describes scope and navigation; it is not a complete translation.

[한국어](README.md) · [English](README.en.md) · [日本語](README.ja.md)

- [Environment and first change](ONBOARDING.md)
- [Requirements and acceptance criteria](REQUIREMENTS.md)
- [System and component boundaries](ARCHITECTURE.md)
- [Config, project storage and results](DATA-CONTRACTS.md)
- [States, APIs and visible agent operation](RUNTIME-API.md)
- [Testing and numerical/experimental evidence](VERIFICATION.md)
- [Installation, recovery, release and rollback](OPERATIONS.md)
- [Known gaps and proposed priorities](BACKLOG.md)
- [Boundary layers and AMR proposals](MESH-ROADMAP.md)
- [Handoff and documentation maintenance](MAINTENANCE.md)
- [Architectural decisions](decisions/README.md)
- [Research and documentation references](REFERENCES.md)

```bash
python tools/check_development_docs.py
```

- Preserve projects, results and uncommitted changes
- Solver installation, execution integration, visualization readiness and physical validation are separate states
- The documentation does not claim completed AMR, wall-layer integration, experimental validation or universal solver support
