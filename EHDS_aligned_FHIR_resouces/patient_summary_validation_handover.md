# Patient Summary Validation Handover

This note summarises the Patient Summary FHIR bundles prepared for Diana Ferreira and Patrick Murphy.

The project now contains two types of output:

- **Rich EHDS-aligned bundles**: these retain the fuller clinical content and the CTS/NMPC enrichment traceability.
- **Gazelle validator-facing bundles**: these are refined copies prepared specifically to pass the selected Gazelle IPS and EU-EPS validators.

## Files to Share

### Diana Ferreira

Rich EHDS-aligned bundle:

- `EHDS_aligned_FHIR_resouces/Diana_Ferreira_bundle_ehds_aligned.json`

Gazelle validator-facing bundles:

- `EHDS_aligned_FHIR_resouces/gazelle/Diana_Ferreira_bundle_ips_gazelle.json`
- `EHDS_aligned_FHIR_resouces/gazelle/Diana_Ferreira_bundle_eps_gazelle.json`

Validation evidence:

- IPS validation: https://ehds.gazelle-platform.net/evs/report.seam?oid=1.3.6.1.4.1.12559.11.55.1.13.2089&privacyKey=OBiYNwp8rhKox5sQ
- EU-EPS validation: https://ehds.gazelle-platform.net/evs/report.seam?oid=1.3.6.1.4.1.12559.11.55.1.13.2096&privacyKey=0b3ugVVh80YzfOVH

Result:

- IPS: passed Gazelle validation.
- EU-EPS: passed Gazelle validation.

### Patrick Murphy

Rich EHDS-aligned bundle:

- `EHDS_aligned_FHIR_resouces/Patrick_Murphy_bundle_ehds_aligned.json`

Gazelle validator-facing bundles:

- `EHDS_aligned_FHIR_resouces/gazelle/Patrick_Murphy_bundle_ips_gazelle.json`
- `EHDS_aligned_FHIR_resouces/gazelle/Patrick_Murphy_bundle_eps_gazelle.json`

Validation evidence:

- IPS validation: https://ehds.gazelle-platform.net/evs/report.seam?oid=1.3.6.1.4.1.12559.11.55.1.13.2090&privacyKey=ZzUHhvP2OgQWVnUU
- EU-EPS validation: https://ehds.gazelle-platform.net/evs/report.seam?oid=1.3.6.1.4.1.12559.11.55.1.13.2097&privacyKey=bqQrX45XkpMvRwml

Result:

- IPS: passed Gazelle validation.
- EU-EPS: passed Gazelle validation.

## What Changed

The rich EHDS-aligned bundles were enhanced using:

- Irish HSE Central Terminology Service (CTS), where safe, to complete missing semantic coding metadata such as code displays.
- Irish National Medicinal Product Catalogue (NMPC), where safe, to enrich medication coding and identify Irish medicinal product candidates.
- Structural alignment against Patient Summary expectations, including adding explicit empty sections where required content was absent from the source data.

The Gazelle validator-facing bundles were then prepared as cleaner submission copies. These remove local enrichment audit details and profile-unfriendly local artefacts that are useful internally but not recognised by the selected Gazelle validators.

For the EU-EPS validator, the refined EPS copies are intentionally narrower than the rich bundles. Some optional IPS-style sections were filtered from the EPS submission copy because the current EU-EPS alpha validator expects a stricter profile shape.

## Practical Interpretation

Use the rich EHDS-aligned bundles when reviewing the fullest available patient summary content.

Use the Gazelle validator-facing bundles when demonstrating conformance to the selected Gazelle validators.

In short:

- The rich bundles are better for clinical and terminology review.
- The Gazelle bundles are better for validation evidence.
- Both Diana and Patrick now have passing IPS and EU-EPS Gazelle validation reports.

