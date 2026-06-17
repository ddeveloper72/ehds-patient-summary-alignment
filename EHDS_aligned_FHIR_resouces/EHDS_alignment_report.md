# EHDS Patient Summary Alignment Report

Generated from the local bundles in `Test_documents/`.

Alignment baseline used:

- eHDSI Patient Summary template, effective 2024-04-19.
- At-least-present eHDSI sections: Medication Summary; Allergies and Other Adverse Reactions; List of Surgeries; Active Problems; Medical Devices.
- FHIR Bundle structure and local Composition sections were preserved; missing clinical facts were not invented.
- CTS terminology enrichment status: enabled.
- NMPC medication enrichment status: enabled.

## Diana_Ferreira_bundle.json

- Aligned output: `EHDS_aligned_FHIR_resouces/Diana_Ferreira_bundle_ehds_aligned.json`
- Composition found: True
- Composition title/status: Patient Summary / final
- Resource counts: {'Composition': 1, 'Patient': 1, 'Practitioner': 1, 'Organization': 1, 'AllergyIntolerance': 4, 'Condition': 8, 'Procedure': 3, 'MedicationStatement': 5, 'Observation': 12, 'Immunization': 4, 'ClinicalImpression': 2, 'Consent': 1, 'Provenance': 1}
- Sections present: Allergies and Intolerances, Problem List, History of Past Illness, History of Procedures, Medication Summary, Vital Signs, History of Immunizations, Social History, Laboratory Results, History of Pregnancies, Functional Status, Advance Directives
- Missing at-least-present eHDSI sections before alignment: Medical Devices
- Other commonly used Patient Summary sections absent: None
- Missing internal `urn:uuid:` references: None

Changes made:

- Added explicit empty Medical Devices section for eHDSI Medical Devices using list-empty-reason=unavailable.

Terminology enrichment:

- CTS lookup attempts: 37
- Coding displays added: 6
- CTS text search attempts: 0
- New codings added from exact text matches: 0
- Unresolved text-only concepts: 0

- Added display 'Kiwi fruit' to /entry[4]/resource/code/coding[0] (http://snomed.info/sct|260176001) using CTS lookup.
- Added display 'Lactose' to /entry[5]/resource/code/coding[0] (http://snomed.info/sct|47703008) using CTS lookup.
- Added display 'Latex' to /entry[7]/resource/code/coding[0] (http://snomed.info/sct|111088007) using CTS lookup.
- Added display 'Implantation of heart assist system' to /entry[16]/resource/code/coding[0] (http://snomed.info/sct|64253000) using CTS lookup.
- Added display 'Caesarean section' to /entry[17]/resource/code/coding[0] (http://snomed.info/sct|11466000) using CTS lookup.
- Added display 'Thyroidectomy' to /entry[18]/resource/code/coding[0] (http://snomed.info/sct|13619001) using CTS lookup.

Medication catalogue enrichment:

- MedicationStatements checked: 5
- ATC reverse searches: 5
- NMPC text searches: 0
- NMPC codings added: 1
- NMPC candidate extensions added: 4
- External mapping attempts: 3
- External mapping codings added: 2
- Ambiguous medication matches: 4
- Unresolved medications: 0

- Added NMPC candidate extension to MedicationStatement/a50e351e-71d6-4e0d-a6eb-6d1fa1af64ab (1997-10-06): 10 candidates found from http://www.whocc.no/atc|H03AA01; no asserted NMPC coding added.
- Added NMPC candidate extension to MedicationStatement/96d7d4cd-c1c5-45ca-81f8-62826f8824ab (2017-05-06): 3 candidates found from http://www.whocc.no/atc|C09BB05; no asserted NMPC coding added.
- Added NMPC coding 531361000220107 to MedicationStatement/9f35b5d7-79aa-4b99-9e80-c29ad18b551f (2012-04-30) from http://www.whocc.no/atc|A10AE06.
- Added HPRA mapping 9676 to MedicationStatement/9f35b5d7-79aa-4b99-9e80-c29ad18b551f (2012-04-30) from NMPC code 531361000220107.
- Added PCRS mapping 72390 to MedicationStatement/9f35b5d7-79aa-4b99-9e80-c29ad18b551f (2012-04-30) from NMPC code 531361000220107.
- Added NMPC candidate extension to MedicationStatement/6f276609-e29e-44e6-8679-1546df277b9e (2017-05-07): 24 candidates found from http://www.whocc.no/atc|J01CR02; no asserted NMPC coding added.
- Added NMPC candidate extension to MedicationStatement/f7b6ddeb-f878-4856-b5d8-43c1aa1f5b2b (2015-01-02): 2 candidates found from http://www.whocc.no/atc|R03AL02; no asserted NMPC coding added.

## Patrick_Murphy_bundle.json

- Aligned output: `EHDS_aligned_FHIR_resouces/Patrick_Murphy_bundle_ehds_aligned.json`
- Composition found: True
- Composition title/status: Patient Summary / final
- Resource counts: {'Composition': 1, 'Patient': 1, 'Practitioner': 1, 'Organization': 1, 'AllergyIntolerance': 2, 'Condition': 1, 'Procedure': 2, 'MedicationStatement': 1, 'Provenance': 1}
- Sections present: Allergies and Intolerances, Problem List, History of Procedures, Medication Summary
- Missing at-least-present eHDSI sections before alignment: Medical Devices
- Other commonly used Patient Summary sections absent: History of Past Illness, History of Immunizations, Vital Signs, Laboratory Results, Pregnancy History, Functional Status, Social History, Advance Directives
- Missing internal `urn:uuid:` references: None

Changes made:

- Added explicit empty Medical Devices section for eHDSI Medical Devices using list-empty-reason=unavailable.

Terminology enrichment:

- CTS lookup attempts: 7
- Coding displays added: 0
- CTS text search attempts: 0
- New codings added from exact text matches: 0
- Unresolved text-only concepts: 0

- CTS terminology enrichment ran, but no safe coding changes were found.

Medication catalogue enrichment:

- MedicationStatements checked: 1
- ATC reverse searches: 1
- NMPC text searches: 0
- NMPC codings added: 0
- NMPC candidate extensions added: 1
- External mapping attempts: 0
- External mapping codings added: 0
- Ambiguous medication matches: 1
- Unresolved medications: 0

- Added NMPC candidate extension to MedicationStatement/aacdd6bd-98e2-4ad9-9b90-13d95206ab4a (2024-01-01): 2 candidates found from http://www.whocc.no/atc|A10AE04; no asserted NMPC coding added.

## Assumptions and Unresolved Items

- Empty sections use `emptyReason` code `unavailable` because the source bundles did not contain those clinical facts.
- The script does not add clinical devices, immunizations, conditions, observations, or other resource entries unless they already exist in the source bundle.
- CTS-sourced coding changes are conservative: existing codes may receive missing display text from `$lookup`; text-only concepts are coded only when `$expand` returns one exact unambiguous display match.
- NMPC-sourced medication changes are conservative: an asserted NMPC coding is added only for a single unambiguous product match; multiple matches are recorded as candidate extensions for human review.
- GTIN mappings are not asserted by this script because the NMPC testing reference notes GTIN is file-only or sparsely available via API.
- Full conformance still requires validation against the selected EHDS/IPS FHIR profiles and terminology bindings.
- The live HL7 EU build may change over time; record the guide version used before formal sign-off.
