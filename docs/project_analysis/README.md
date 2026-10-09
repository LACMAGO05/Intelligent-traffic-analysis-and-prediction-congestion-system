# Historical project analysis archive

This directory preserves dated engineering analysis, proposed work, and phase changelogs. These files are useful for understanding project history, but several describe earlier code and should not be used as current setup, architecture, database, deployment, or ML instructions.

For current guidance, use:

- [Current architecture](../ARCHITECTURE.md)
- [Current database and persistence](../DATABASE.md)
- [Current ML pipeline](../ML_PIPELINE.md)
- [Current deployment overview](../DEPLOYMENT.md)
- [Repository entry point](../../README.md)

## Historical current-state analyses

The following dated analyses describe the code as inspected at the time they were written. In particular, they may refer to the old CSV persistence path, Supabase analytics, removed collector modules, or earlier ML artifacts and behavior. Retain them as historical records; consult the current guides above for the implementation now represented by the repository.

- [Repository map](REPOSITORY_MAP.md)
- [System architecture](SYSTEM_ARCHITECTURE.md)
- [Backend flow](BACKEND_FLOW.md)
- [Frontend flow](FRONTEND_FLOW.md)
- [Database structure](DATABASE_STRUCTURE.md)
- [ML pipeline](ML_PIPELINE.md)
- [Third-party services](THIRD_PARTY_SERVICES.md)
- [Engineering audit](ENGINEERING_AUDIT.md)

## Historical planning and change records

- [Implementation roadmap](IMPLEMENTATION_ROADMAP.md) — proposed work and sequencing at the time of writing; later phase notes record some subsequent changes.
- [Phase 1 changelog](PHASE1_CHANGELOG.md)
- [Phase 2 changelog](PHASE2_CHANGELOG.md)
- [Phase 3 changelog](PHASE3_CHANGELOG.md)
- [Phase 4 changelog](PHASE4_CHANGELOG.md)
- [Phase 5 changelog](PHASE5_CHANGELOG.md)

The changelogs describe implementation history, not a guarantee that every stated validation or deployment step has been repeated against the current checkout. The Phase 5 metrics differ from the currently checked-in model schema/card; see the [current ML guide](../ML_PIPELINE.md) for that distinction.
