# CEREBRO — LikeC4 model

Three layers of the same system, in one model:

| File | Layer | Answers |
| --- | --- | --- |
| `business.c4` | Business | Who it serves, what it promises, the rules knowledge must satisfy |
| `application.c4` | Application | Containers and components, named after the modules they describe |
| `technology.c4` | Technology | Compose and Kubernetes, with the images and ports that are really used |
| `views.c4` | — | One view per question, including five dynamic flows |
| `specification.c4` | — | Element kinds, tags and styling |

Validated with the real parser, not assumed:

```
✓ Valid (5 files) — 63 elements, 75 relations, 16 views
```

## Looking at it

```bash
npx likec4 start architecture/likec4      # browser, hot reload
npx likec4 export png -o architecture/diagrams architecture/likec4
npx likec4 validate architecture/likec4   # parse and check references
```

No dependency is added to the repository: `npx` fetches LikeC4 on demand.

## What the model claims

Only what exists. Components correspond to modules — `api.search` is
`backend/app/services/search.py` — so a diagram can be checked against the
source rather than believed. Anything not yet built would carry `#planned`
and be drawn pale; nothing does today.

Three tags carry meaning rather than decoration:

- `#integrity` — the element enforces approval, provenance or grounding.
  `view integrity_controls` shows them together.
- `#local-only` — it runs on the user's machine. `view local_processing`
  is the answer to "where does my data go": there is no cloud path to draw.
- `#optional` — deployed only when enabled, such as MinIO.

## The five flows

The dynamic views walk a real request path, so each can be checked against
the code:

| View | Answers |
| --- | --- |
| `ingestion` | How a document becomes knowledge that may be trusted |
| `ask` | Why Ask CEREBRO retrieves before it generates, and abstains without evidence |
| `search_flow` | Two retrievals, fused by rank rather than by score |
| `cv_anchor` | How a CV anchors the timeline without a second ingestion path |
| `measurement` | How accuracy is computed from the review loop rather than asserted |

## Relationship to the Structurizr model

`architecture/structurizr/workspace.dsl` remains the source for the C4
diagrams committed under `architecture/diagrams`, which `make diagrams`
regenerates. This LikeC4 model covers the same system at three layers rather
than four C4 levels, and is the better starting point for the business and
technology views. Keep them consistent by changing both when a container
appears or disappears; they describe one system.
