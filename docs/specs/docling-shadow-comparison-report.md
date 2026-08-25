# Docling shadow comparison

This report is for ingestion maintainers comparing legacy parsing with Docling on the sample corpus.

## HR-Special-Leave-Policy-v1.0.docx

- verdict: **no content loss**
- token recall: 1.0000
- elements: legacy 22 -> docling 22
- distinct content tokens: legacy 152 -> docling 152
- tokens missing from docling: 0
- tokens added by docling: 0
- legacy element types: {'heading': 8, 'paragraph': 14}
- docling element types: {'heading': 7, 'paragraph': 14, 'title': 1}
- fragment resolution failures: legacy 0, docling 0

## IT-Security-Incident-Emergency-Access-Policy-v1.0.docx

- verdict: **no content loss**
- token recall: 1.0000
- elements: legacy 25 -> docling 41
- distinct content tokens: legacy 169 -> docling 172
- tokens missing from docling: 0
- tokens added by docling: 3
- legacy element types: {'heading': 9, 'paragraph': 12, 'table_row': 4}
- docling element types: {'heading': 8, 'paragraph': 12, 'table_cell': 20, 'title': 1}
- fragment resolution failures: legacy 0, docling 0
- sample added tokens: ['contact', 'description', 'sla']

## Workplace-Hardware-Provisioning-Policy-v3.2.docx

- verdict: **no content loss**
- token recall: 1.0000
- elements: legacy 190 -> docling 280
- distinct content tokens: legacy 773 -> docling 779
- tokens missing from docling: 0
- tokens added by docling: 6
- legacy element types: {'heading': 79, 'list_item': 11, 'paragraph': 76, 'table_row': 24}
- docling element types: {'heading': 79, 'list_item': 11, 'paragraph': 96, 'table_cell': 94}
- fragment resolution failures: legacy 0, docling 0
- sample added tokens: ['definition', 'indicative', 'resolution', 'summary', 'target', 'turnaround']

## Workplace-Hardware-Provisioning-Policy-v3.3.docx

- verdict: **no content loss**
- token recall: 1.0000
- elements: legacy 193 -> docling 285
- distinct content tokens: legacy 786 -> docling 792
- tokens missing from docling: 0
- tokens added by docling: 6
- legacy element types: {'heading': 80, 'list_item': 11, 'paragraph': 77, 'table_row': 25}
- docling element types: {'heading': 80, 'list_item': 11, 'paragraph': 97, 'table_cell': 97}
- fragment resolution failures: legacy 0, docling 0
- sample added tokens: ['definition', 'indicative', 'resolution', 'summary', 'target', 'turnaround']

## HR-Guide-Policy-and-Procedure-Template.pdf

- verdict: **no content loss**
- token recall: 1.0000
- elements: legacy 550 -> docling 782
- distinct content tokens: legacy 2491 -> docling 2494
- tokens missing from docling: 0
- tokens added by docling: 3
- legacy element types: {'heading': 202, 'list_item': 88, 'paragraph': 260}
- docling element types: {'heading': 203, 'list_item': 148, 'paragraph': 349, 'table_cell': 82}
- fragment resolution failures: legacy 0, docling 0
- sample added tokens: ['rightspolicies', 'safetyact', 'standardsact']

## Verdict

No document lost content under Docling.
