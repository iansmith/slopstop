# Branch-type heuristics

Maps ticket labels and title patterns to a suggested Conventional-Commits branch type prefix.

**Priority:** first label match wins over title match. If multiple labels match different types, prefer: `fix > feat > refactor > perf > docs > chore > test`.

## Label → type

| Label signal | Suggested type |
|---|---|
| `bug`, `regression`, `hotfix`, `defect` | `fix` |
| `feature`, `enhancement`, `story` | `feat` |
| `chore`, `maintenance`, `cleanup`, `tech-debt`, `tech debt` | `chore` |
| `docs`, `documentation` | `docs` |
| `refactor`, `refactoring` | `refactor` |
| `perf`, `performance` | `perf` |
| `test`, `testing`, `qa` | `test` |

## Title → type

| Title pattern | Suggested type |
|---|---|
| Starts with `Fix `, `Bug:`, `Regression:`, or contains ` bug ` | `fix` |
| Starts with `Add `, `Implement `, `Build `, `Create `, `New ` | `feat` |
| Starts with `Refactor `, `Cleanup `, `Rename ` | `refactor` |
| Contains `documentation`, `README`, or `docs` (whole-word) | `docs` |

If no signal matches, offer no suggestion — ask the user to choose.
