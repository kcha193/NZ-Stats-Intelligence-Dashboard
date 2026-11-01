# API generator security-audit remediation

1 November 2026. Base: main `c09a759`, after PR #33. Separate from Phase 4J processing and display permissions.

The required `npm audit --audit-level=low` fails through
`openapi-typescript@7.13.0 → @redocly/openapi-core@1.34.20 → minimatch@5.1.9`
([GHSA-g3hv-75wg-m249](https://github.com/advisories/GHSA-g3hv-75wg-m249)).
The current 7.x generator has no compatible dependency update. Redocly 2.x changes its exported internals;
overriding it breaks generation, as the PR #33 audit records.

The remediation pins `openapi-typescript@6.7.6` and regenerates the declarations. Its defaulted fields must use
`--default-non-nullable` to retain the 7.x required-field semantics. Without that flag, 15 component schemas
become more permissive; TypeScript checking alone misses this because the project disables strict null checks.
The complete generated component declaration, including all 101 schemas, is equivalent to the original after
TypeScript printer normalisation without comments. The large generated diff also removes unsupported HTTP
methods represented as optional `never` properties by 7.x; no handwritten API types change.

Version 6 brings an older Undici dependency with separate Busboy advisories. A scoped override pins only the
generator's Undici to `7.30.1`, already used by the test environment. Its Node floor is 20.18.1; local Node
20.20.2 and the workflow's current Node 20 satisfy it. This crosses Undici's major-version range, so generation
and HTTP schema loading need verification. No audit threshold, advisory suppression or CI job is changed.

Validation and independent Codex High review are recorded in the PR. Reproduction:

```sh
cd frontend
npm ci
npm audit --audit-level=low
npm run gen:api                 # activate the backend Python 3.12 environment first
git diff --exit-code -- src/api/schema.d.ts  # after committing the regenerated declarations
npm run typecheck
npm run lint
npm test
npm run build
```

Rollback is the package manifest, lockfile and generated declaration together. It restores the old audit failure.
An eventual supported generator release can replace this pinned toolchain after equivalent checks.
