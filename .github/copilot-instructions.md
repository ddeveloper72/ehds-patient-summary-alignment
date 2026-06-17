# Copilot Instructions

This workspace is for testing and improving Patient Summary FHIR Bundles so they align with the EHDS logical information model for Patient Summary.

## Project Goal

Help validate a Patient Summary FHIR Bundle, inspect its resources, identify gaps against EHDS Patient Summary requirements, and produce an amended copy of the bundle that is better aligned with the logical information model.

When working in this repository:

- Treat the original test bundle as source material. Do not overwrite it unless explicitly asked.
- Create amended or aligned outputs under `EHDS_aligned_FHIR_resouces/`.
- Prefer small, traceable changes that preserve valid FHIR JSON structure.
- Document alignment decisions, assumptions, and any unresolved issues.
- Use the existing Python virtual environment in `.venv/` for local scripts and validation work.

## Key Reference Material

Use these external references when checking alignment:

- XT-EHR Patient Summary overview: https://www.xt-ehr.eu/fhir/models/1.0.0/en/overview-patientsummary.html
- HL7 Europe implementation guides: https://confluence.hl7.org/spaces/HEU/pages/358255737/Implementation+Guides
- HL7 EU ePrescription / Patient Summary build: https://build.fhir.org/ig/hl7-eu/eps/
- ART-DECOR eHDSI Patient Summary template: https://art-decor.ehdsi.eu/publication/epsos-html-20240422T073854/tmp-1.3.6.1.4.1.12559.11.10.1.3.1.1.3-2024-04-19T100332.html

Use this local project as the reference implementation for Irish HSE Central Terminology Service (CTS) access:

- `C:\Users\duncanfalconer\VS_Code_Projects\CTS_testing`

The CTS testing project contains the OAuth2 client-credentials pattern, FHIR terminology operation examples, and search/lookup workflows for SNOMED CT, LOINC, UCUM, and related code systems.

Use this local project as the reference implementation for the Irish National Medicinal Product Catalogue (NMPC) API:

- `C:\Users\duncanfalconer\VS_Code_Projects\NMPC_Testing`

The NMPC testing project contains OAuth2 client-credentials access, product search, `CodeSystem/$lookup`, `ValueSet/$expand`, and `ConceptMap/$translate` examples for NMPC concepts and mappings to HPRA, PCRS, ATC, and GTIN where available.

If the references conflict, call out the conflict clearly and explain which source was followed.

## Test Documents

The main test document is:

- `Test_documents/patient_summary_bundle.json`

Other sample bundles may also be present in the repository root or in `Test_documents/`.

## Expected Workflow

1. Inspect the FHIR Bundle structure and identify the contained resources.
2. Check that key Patient Summary sections and data elements are present.
3. Compare the bundle against the EHDS logical information model and relevant implementation guidance.
4. Report missing, incomplete, inconsistent, or non-conformant elements.
5. Create an amended copy of the bundle in `EHDS_aligned_FHIR_resouces/`.
6. Where CTS credentials are available, use the Irish HSE CTS to complete missing semantic coding metadata such as code system authority, code display, and safe terminology matches.
7. Where NMPC credentials are available, use the Irish NMPC API to enrich medication coding and identify Irish catalogue product candidates.
8. Preserve the original clinical meaning wherever possible.
9. Keep a clear note of changes made and any assumptions used to complete missing data.

## Repository Layout

```text
EHDS_PS_Alignment/
+-- .venv/
+-- .gitignore
+-- .github/
|   +-- copilot-instructions.md
+-- Test_documents/
|   +-- patient_summary_bundle.json
+-- EHDS_aligned_FHIR_resouces/
```

## Coding Guidance

- Use Python for validation, transformation, and reporting scripts.
- Read and write JSON with structured parsers rather than manual string manipulation.
- Keep generated files clearly named, for example `patient_summary_bundle_ehds_aligned.json`.
- Avoid making broad unrelated changes to the repository.
- Where validation cannot be fully automated, provide a human-readable checklist or report.
- Keep CTS credentials in local environment variables or local `.env` files only. Do not commit credentials, access tokens, or exported terminology datasets.
- Terminology enrichment must be conservative and traceable. Prefer exact `CodeSystem/$lookup` for known codes and only add new codings from text when CTS returns one exact, unambiguous match.
- Keep NMPC credentials in local environment variables or local `.env` files only. Do not commit credentials, access tokens, downloaded catalogue files, or exported terminology/product datasets.
- NMPC medication enrichment must be conservative and traceable. Add an asserted NMPC coding only when a single unambiguous product match is found; record multiple possible matches as candidates for human review.
