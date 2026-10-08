# Data selection and provenance

Decision date: 8 October 2026 (Australia/Brisbane).

The core case study uses French motor third-party liability rather than home insurance. A linked public frequency/severity source allows exposure-aware pricing with a defensible count–cost relationship.

| Candidate | Fit for the requested project | Decision |
|---|---|---|
| freMTPL2: OpenML 41214 and 41215, version 1 | Policy exposure, original counts, risk factors, linked positive claim amounts | Selected; verified files downloaded and audited |
| freMTPL2: current R CASdatasets | Authoritative documentation, but snapshot versions can differ | Reference only; do not mix with pinned OpenML data |
| Allstate Claims Severity, Kaggle | Severity competition; anonymised categorical/continuous predictors | Alternative severity exercise; not our policy frequency/exposure source |

Primary references:

- [OpenML frequency metadata](https://www.openml.org/api/v1/json/data/41214)
- [OpenML severity metadata](https://www.openml.org/api/v1/json/data/41215)
- [CASdatasets description and fields](https://dutangc.github.io/CASdatasets/reference/freMTPL.html)
- [CASdatasets source repository](https://github.com/dutangc/CASdatasets)
- [Allstate competition data page](https://www.kaggle.com/competitions/allstate-claims-severity/data)
- [scikit-learn frequency/severity example](https://scikit-learn.org/stable/auto_examples/linear_model/plot_tweedie_regression_insurance_claims.html)

CASdatasets documents approximately 2011–2013 observation years for freMTPL2, and notes that some amounts reflect French claims conventions. This is historical liability cover, with cost amounts in source EUR; there are no record-level dates here. Current CASdatasets and this older OpenML version are not interchangeable.

The pipeline uses the OpenML Parquet mirrors advertised in the metadata. Both metadata responses identify their datasets as version 1 with CC0 licensing. OpenML's MD5 refers to ARFF, so the project separately pins Parquet SHA-256 hashes in `configs/source_lock.json`. `reports/data_manifest.json` contains dataset IDs, URLs, source licence declarations, citations, sizes and hashes. No data is fetched from third-party Kaggle repackagings.

The downloaded frequency table has 678,013 distinct policy IDs, rather than the 677,991 policies in the description. Claims join by `IDpol` only. A full audit is required whenever changing either source version; do not replace one table independently.

No redistribution of raw records is needed for reproducibility. Git stores the downloader, source lock, transformations, tests, and aggregate reports. Users fetch the verified public sources locally.

Optional Australian market context will use separately verified APRA/ICA/BOM sources after the core model. No geographic mapping of French regions to Australian weather or catastrophe exposure is valid. Aggregate Australian series can contextualise trends, but cannot supply individual Australian risk factors to these French policies.
