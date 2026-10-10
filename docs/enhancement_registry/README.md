# Enhancement Registry — PAZUZU-API v2.0

## Honest status: empty by design

**Enhancements E1–E96 were NOT supplied in the source materials.** The supplied
source (`../../_source/audit_issues_1_78.md`) contains audit issues #1–#78 only
and states explicitly: "No E1–E96 enhancements were supplied. Do NOT invent them."

Therefore:
- **No enhancements are registered.** `index.json` is `{"supplied": false, "count": 0, "records": []}`.
- Nothing in this directory describes, summarizes, or invents any E-item.

## What IS ready

- `schema.md` — the registry field specification every enhancement record must
  follow, plus the 12 technical-area groupings it will be filed under.
- `index.json` — the machine-readable index, currently empty.

## When E1–E96 arrive

1. Create one record per enhancement under `records/E001.md … E096.md`
   (zero-padded, matching the audit registry's convention).
2. Each record MUST populate every field in `schema.md`. Fields that cannot be
   determined from the supplied spec are marked `tbd` with a reason — never
   invented.
3. Update `index.json`: set `supplied: true`, `count`, and the `records` array.
4. Cross-link to audit records where an enhancement resolves or depends on a
   registered issue (S001–S078, and S079–S144 once they exist).
