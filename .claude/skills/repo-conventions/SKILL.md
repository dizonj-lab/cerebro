---
name: repo-conventions
description: Apply this repository's conventions when adding a new module, service, or feature directory. Use when scaffolding new code, choosing where a file belongs, or naming modules, tests and exports.
---

# Repo conventions

> Scaffolded example skill. Replace the TODO sections with this project's real
> conventions — a skill is only useful once it encodes something Claude cannot
> infer from reading the code.

## When this applies

Creating a new module, package, service, or feature directory in this repo.

## Directory shape

TODO: the canonical layout of a new module, e.g.

```
src/<feature>/
├── index.<ext>        # public surface — nothing else is imported from outside
├── <feature>.<ext>    # implementation
└── <feature>.test.<ext>
```

## Rules

1. TODO: what may import what (module boundaries).
2. TODO: naming — files, types, exported symbols.
3. TODO: where tests live and what the minimum coverage is.
4. TODO: how errors are surfaced (thrown, returned, logged).

## Checklist before finishing

- [ ] Public surface exports only what callers need
- [ ] Tests colocated per the rule above and passing
- [ ] Lint and typecheck clean
