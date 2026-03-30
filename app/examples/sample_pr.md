# Sample PR Draft

## Summary
Adds CSV export capability to the reports page and threads current table filters into the exported dataset.

## Implementation Notes
- Added UI button and export action wiring.
- Extended serializer to support filtered export payload.
- Updated report service endpoint handling.

## Test Evidence
- `pytest -q` passed.
- Existing report tests still green.

## Risks
- CSV format assumptions may vary for very large datasets.

## Follow-ups
- Consider background export jobs for long-running exports.
