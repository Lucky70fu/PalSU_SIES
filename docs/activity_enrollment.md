# Enrollment Activity Diagram

```mermaid
flowchart TD
 A([Start]) --> B[Student signs in]
 B --> C[Complete / verify profile]
 C --> D[Choose open school term]
 D --> E[Select curriculum subjects and sections]
 E --> F{Prerequisites satisfied?}
 F -- No --> X[Show missing prerequisite] --> E
 F -- Yes --> G{Schedule and capacity valid?}
 G -- No --> Y[Show conflict / full section] --> E
 G -- Yes --> H[Submit enrollment application]
 H --> I[Registrar checks documents and records]
 I --> J{Approved?}
 J -- No --> K[Return for correction / reject] --> Z([End])
 J -- Yes --> L[Generate assessment]
 L --> M[Student pays cashier / configured online gateway]
 M --> N[Update payment ledger and balance]
 N --> O[Confirm enrollment and publish schedule]
 O --> Z([End])
```

Note: The diagram describes the target complete operation. The current starter UI implements application submission and payment recording; subject cart validation, registrar approval actions and automated assessment generation are explicitly listed as completion work in README.
