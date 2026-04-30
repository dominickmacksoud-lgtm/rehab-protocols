# Protocols Workflow

This workspace now includes the source-of-truth CSV file and a script to regenerate `protocols.js`.

## Files

- `protocols-import.csv` — master protocol metadata source (source of truth)
- `generate-protocols.py` — Python script that converts the CSV into `protocols.js`

## How to regenerate `protocols.js`

1. Update `protocols-import.csv` with new protocol rows.
2. Run the generator:

```powershell
cd C:\Users\iprom\Documents\my-pt-website
python generate-protocols.py
```

3. Commit the updated `protocols-import.csv` and `protocols.js`.

## Notes

- The generator outputs 13 structured fields per protocol: `url`, `category`, `name`, `type`, `sourceOrganization`, `sourceType`, `surgeons`, `publicationDate`, `wbStatus`, `wbInitial`, `keyRestrictions`, `timelinePhases`, `notes`, `isPdf`.
- `wbInitial` is extracted from `wbStatus` and used for badge color coding on the site.
- `sourceType` is inferred from the URL/org name (academic / hospital / surgeon / clinic).
