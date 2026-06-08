# PR Test Detection — Auto-detect Table (Step 2a)

| Indicator | Command |
|---|---|
| `Taskfile.yml` with a `test:` task | `task test` |
| `Makefile` with a `test:` target | `make test` |
| `package.json` with `"test"` script + `pnpm-lock.yaml` | `pnpm test` |
| `package.json` with `"test"` script + `yarn.lock` | `yarn test` |
| `package.json` with `"test"` script (else) | `npm test` |
| `Cargo.toml` | `cargo test` |
| `go.mod` | `go test ./...` |
| `pyproject.toml` with pytest config | `pytest` |
