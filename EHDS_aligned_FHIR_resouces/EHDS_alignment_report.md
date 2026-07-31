# EHDS Patient Summary Alignment Report

Generated from the local bundles in `Test_documents/`.

Alignment baseline used:

- eHDSI Patient Summary template, effective 2024-04-19.
- At-least-present eHDSI sections: Medication Summary; Allergies and Other Adverse Reactions; List of Surgeries; Active Problems; Medical Devices.
- FHIR Bundle structure and local Composition sections were preserved; missing clinical facts were not invented.
- CTS terminology enrichment status: enabled.
- NMPC medication enrichment status: enabled.
- HAPI FHIR validation status: disabled: run with --validate-hapi to enable public HAPI validation.

## Diana_Ferreira_bundle.json

- Aligned output: `EHDS_aligned_FHIR_resouces/patients/diana-ferreira/fhir/ehds-aligned/bundle.json`
- Composition found: True
- Composition title/status: Patient Summary / final
- Resource counts: {'Composition': 1, 'Patient': 1, 'Practitioner': 1, 'Organization': 1, 'AllergyIntolerance': 4, 'Condition': 8, 'Procedure': 3, 'MedicationStatement': 5, 'Observation': 12, 'Immunization': 4, 'ClinicalImpression': 2, 'Consent': 1, 'Provenance': 1}
- Sections present: Allergies and Intolerances, Problem List, History of Past Illness, History of Procedures, Medication Summary, Vital Signs, History of Immunizations, Social History, Laboratory Results, History of Pregnancies, Functional Status, Advance Directives
- Missing at-least-present eHDSI sections before alignment: Medical Devices
- Other commonly used Patient Summary sections absent: None
- Missing internal `urn:uuid:` references: None

Changes made:

- Modelled implant procedure evidence as Medical Devices entries: Heart assist system from Procedure/bd39b363-0202-469e-bd93-d71c852439ca; set Procedure/bd39b363-0202-469e-bd93-d71c852439ca performedDateTime to 2014-10-20.
- Replaced Condition/ed389c36-72ff-4c2d-8bfd-e180558d00c5 epSOS placeholder code 199 with SNOMED CT 40354009 | Cornelia de Lange syndrome |; retained the source epSOS coding in the aligned bundle for traceability.
- Updated the Problem List narrative/table to publish Cornelia de Lange syndrome as an active rare disease rather than only a paragraph-level note.

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

Gazelle validator-facing outputs:

- `EHDS_aligned_FHIR_resouces/patients/diana-ferreira/fhir/ips-gazelle/bundle.json`
- Created IPS Gazelle validator-facing copy.
- Gazelle IPS validation passed on 2026-07-09T14:46:48.581Z using Matchbox 4.1.11, validator `http://hl7.org/fhir/uv/ips/StructureDefinition/Bundle-uv-ips` version 2.0.0: 39 constraints checked, 0 errors, 0 warnings.
- Removed local CTS/NMPC audit and candidate extensions.
- Removed NMPC HPRA/PCRS codings and NMPC-added Irish Drug Module codings that Gazelle validates as SNOMED International.
- Removed the validator-unresolvable epSOS placeholder coding after adding SNOMED CT 40354009 for Cornelia de Lange syndrome.
- Updated the Problem List narrative/table to publish Cornelia de Lange syndrome as an active rare disease.
- Changed Provenance/6c939b65-8b3e-4782-afc5-59de9e4fa062 activity display from 'Update' to 'revise'.
- `EHDS_aligned_FHIR_resouces/patients/diana-ferreira/fhir/eu-eps-gazelle/bundle.json`
- Created EU-EPS Gazelle validator-facing copy.
- Gazelle EU-EPS validation passed on 2026-07-09T14:58:27.761Z using Matchbox 4.1.11, validator `http://hl7.eu/fhir/eps/StructureDefinition/bundle-eu-eps` version 1.0.0-alpha: 22 constraints checked, 0 errors, 0 warnings.
- Removed local CTS/NMPC audit and candidate extensions.
- Removed NMPC HPRA/PCRS codings and NMPC-added Irish Drug Module codings that Gazelle validates as SNOMED International.
- Removed the validator-unresolvable epSOS placeholder coding after adding SNOMED CT 40354009 for Cornelia de Lange syndrome.
- Updated the Problem List narrative/table to publish Cornelia de Lange syndrome as an active rare disease.
- Changed Provenance/6c939b65-8b3e-4782-afc5-59de9e4fa062 activity display from 'Update' to 'revise'.
- Removed optional sections from EU-EPS validator copy: History of Past Illness, History of Immunizations, Social History, History of Pregnancies, Advance Directives.
- Pruned unreferenced resources after EU-EPS section filtering so the Bundle only contains the Composition graph submitted for validation.

## Patrick_Murphy_bundle.json

- Aligned output: `EHDS_aligned_FHIR_resouces/patients/patrick-murphy/fhir/ehds-aligned/bundle.json`
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

Gazelle validator-facing outputs:

- `EHDS_aligned_FHIR_resouces/patients/patrick-murphy/fhir/ips-gazelle/bundle.json`
- Created IPS Gazelle validator-facing copy.
- Removed local CTS/NMPC audit and candidate extensions.
- Removed NMPC HPRA/PCRS codings and NMPC-added Irish Drug Module codings that Gazelle validates as SNOMED International.
- Changed Provenance/0c347627-a407-4af6-a335-5263b248aabb activity display from 'Update' to 'revise'.
- `EHDS_aligned_FHIR_resouces/patients/patrick-murphy/fhir/eu-eps-gazelle/bundle.json`
- Created EU-EPS Gazelle validator-facing copy.
- Removed local CTS/NMPC audit and candidate extensions.
- Removed NMPC HPRA/PCRS codings and NMPC-added Irish Drug Module codings that Gazelle validates as SNOMED International.
- Changed Provenance/0c347627-a407-4af6-a335-5263b248aabb activity display from 'Update' to 'revise'.
- No EU-EPS-specific optional sections required filtering.

## Assumptions and Unresolved Items

- Empty sections use `emptyReason` code `unavailable` because the source bundles did not contain those clinical facts.
- Implant-like Procedure evidence may be remodelled into a Medical Devices `DeviceUseStatement` and supporting `Device` when a conservative known mapping is available. Other clinical devices, immunizations, conditions, observations, or resources are not invented.
- CTS-sourced coding changes are conservative: existing codes may receive missing display text from `$lookup`; text-only concepts are coded only when `$expand` returns one exact unambiguous display match.
- NMPC-sourced medication changes are conservative: an asserted NMPC coding is added only for a single unambiguous product match; multiple matches are recorded as candidate extensions for human review.
- GTIN mappings are not asserted by this script because the NMPC testing reference notes GTIN is file-only or sparsely available via API.
- HAPI public server validation is useful for base FHIR R4 structure checks, but it may not validate EHDS/HL7 Europe EPS profiles unless the relevant ImplementationGuide packages are available on that server.
- IPS Gazelle output is a validator-facing copy. It removes local enrichment trace extensions and candidate data that are useful internally but not known to the selected Gazelle profile.
- Do not send real patient-identifiable data to public validation servers.
- Full conformance still requires validation against the selected EHDS/IPS FHIR profiles and terminology bindings.
- The live HL7 EU build may change over time; record the guide version used before formal sign-off.
