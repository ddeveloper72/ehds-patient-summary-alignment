# Niamh Kelly

Synthetic Irish Patient Summary generated from reusable building blocks.

## Scenario

Maternity and hypothyroidism Patient Summary

## Source

- Scenario definition: `scenarios/niamh-kelly.json` or matching source copy.
- Demographics are synthetic and can be replaced with Gazelle DDS demographics.
- Clinical resources are curated synthetic examples intended for IPS/EHDS builder testing.

## Variants

- `fhir/ehds-aligned/bundle.json`: rich builder bundle.
- `fhir/ips-gazelle/bundle.json`: current copy for IPS validator-facing work.
- `fhir/eu-eps-gazelle/bundle.json`: current copy for EU-EPS validator-facing work.

## Enrichment Notes

- Medication resources include NMPC search hints, not asserted NMPC product codes.
- Assert NMPC codings only after a single unambiguous NMPC match.
- Clinical codes and observation units should be validated through CTS before formal validation.
