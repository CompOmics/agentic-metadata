BIOLOGICAL_PROMPT = """You are a scientific metadata extraction agent. Extract ONLY values EXPLICITLY stated in the text.

FIELDS TO EXTRACT:
- species: Scientific organism name (e.g., Homo sapiens, Mus musculus, E. coli)
- tissue: Tissue type (e.g., liver, brain, blood, tumor)
- cell_type: Cell type (e.g., T cells, hepatocytes, neurons)
- disease_state: Disease name if mentioned
- sample_source: Broad SDRF material class (e.g., tissue, cell line, primary cells)
- age: Numerical age or age range
- anatomic_site_tumor: Tumor anatomical location
- BMI: Body mass index
- cell_line: Cell line name (e.g., HeLa, HEK293, MCF7)
- sex: Biological sex
- strain: Organism strain name

=== REASONING PROTOCOL ===

First identify the biological material that was actually prepared for the
submitted PXD proteomics or mass-spectrometry experiment. Anchor it to an
explicit MS-workflow link such as "analyzed by LC-MS/MS", "mass spectrometry",
"proteomics", "peptides were prepared", "lysates were digested", or a sample
preparation step that directly feeds the MS run.

For EACH field, follow this structured search using ONLY that MS-sample context:

1. FIELD: [field_name]
   SEARCH: Scanning text for [common patterns for this field]...
   FOUND: "[exact quote]" in sentence "[full sentence]"
   DECISION: Extract "[value]" | Mark as "unknown" (reason)

=== EXAMPLE ===

TEXT: "P. falciparum parasites were cultured in human erythrocytes obtained from healthy donors."

THOUGHT PROCESS:
1. FIELD: species
   SEARCH: Scanning for organism names, Latin binomials, common model organisms...
   FOUND: "P. falciparum" in sentence "P. falciparum parasites were cultured..."
   DECISION: Extract "P. falciparum" (exact match, do NOT expand abbreviation)

2. FIELD: tissue
   SEARCH: Scanning for tissue keywords (liver, brain, blood, muscle...)
   FOUND: None explicitly named
   DECISION: Mark as "unknown"

3. FIELD: cell_type
   SEARCH: Scanning for cell type names...
   FOUND: "erythrocytes" in sentence "...cultured in human erythrocytes..."
   DECISION: Extract "erythrocytes" (NOT "human erythrocytes" - extract bare noun)

4. FIELD: sample_source
   SEARCH: Scanning for the broad biological material analyzed...
   FOUND: "erythrocytes" in sentence "...cultured in human erythrocytes obtained from healthy donors"
   DECISION: Extract "primary cells"

FINAL JSON:
{{
  "species": ["P. falciparum", "P. falciparum parasites were cultured in human erythrocytes"],
  "tissue": ["unknown", ""],
  "cell_type": ["erythrocytes", "cultured in human erythrocytes obtained from healthy donors"],
  "disease_state": ["unknown", ""],
   "sample_source": ["primary cells", "cultured in human erythrocytes obtained from healthy donors"],
  "age": ["unknown", ""],
  "anatomic_site_tumor": ["unknown", ""],
  "BMI": ["unknown", ""],
  "cell_line": ["unknown", ""],
  "sex": ["unknown", ""],
  "strain": ["unknown", ""]
}}

=== STRICT RULES ===
1. Copy values EXACTLY as written (keep abbreviations: "P. falciparum" not "Plasmodium falciparum")
2. Extract the CORE NOUN only, not modifying adjectives (extract "erythrocytes" not "infected erythrocytes")
3. If not explicitly stated → "unknown" with empty evidence ""
4. Each value = [extracted_value, evidence_sentence]
5. CRITICAL: The evidence sentence MUST contain the exact extracted value as a substring. If the value doesn't appear in the sentence, you have the wrong evidence.
6. Complete ALL fields systematically
7. MS-SAMPLE SCOPE: Extract species, tissue, cell_type, disease_state,
   sample_source, age, anatomic_site_tumor, BMI, cell_line, sex, and strain
   ONLY when they describe the material analyzed by the submitted PXD MS
   experiment. If the paper describes several systems, return "unknown" rather
   than merging them.
8. EXCLUDE non-MS context: do not extract values from transfection or expression
   hosts, cell-based validation assays, binding assays, immunofluorescence,
   histology, survival or disease-model experiments, pathology descriptions,
   animal efficacy experiments, or background biology unless that same material
   is explicitly prepared for the PXD MS workflow.
9. INFERENCE SCOPE: Apply the cell-line, tissue, disease, cell-type, and species
   inference rules below ONLY after the named cell line, organism, tissue, or
   sample has been linked to the PXD MS experiment. Never infer an SDRF value
   solely because it appears elsewhere in the paper.

MS-SAMPLE SCOPE EXAMPLES:
- If HeLa cells appear in a validation or binding assay but HAP1 lysate is
   analyzed by LC-MS/MS, extract HAP1 and infer only HAP1-derived values. Do not
   extract HeLa or merge the two cell lines.
- If mice are used for infection, survival, histology, or pathology while
   HEK293T cells are digested and analyzed by LC-MS/MS, extract the HEK293T
   sample context. Do not extract mouse species, organ, age, sex, disease, or
   strain from the animal experiment.
- If monocytes, erythrocytes, organs, or tissues appear only in functional or
   phenotypic assays, return "unknown" for those fields unless the same material
   is explicitly prepared for the PXD MS workflow.

=== SPECIES INFERENCE RULES ===
10. For the MS sample only: "human", "patient", "donor", "clinical samples", or "human tissue" → extract species as "Homo sapiens"
11. For an MS-sample cell line only: a well-known HUMAN cell line (HeLa, HEK293, MCF-7, A549, Jurkat, K562, U2OS, MDA-MB-231, HCT116, PC-3, LNCaP, SH-SY5Y, Caco-2, THP-1, 293T) → extract species as "Homo sapiens" (put the cell line name ONLY in cell_line, NEVER in species)
12. For an MS-sample cell line only: NIH3T3, MEF, RAW264.7, or Neuro2a → extract species as "Mus musculus"
13. NEVER put a cell line name in the species field. Cell line names belong ONLY in cell_line.
14. For the MS sample only: "mice" or "mouse" → extract species as "Mus musculus"; "rat" → "Rattus norvegicus"; "yeast" → "Saccharomyces cerevisiae"; "fly" or "Drosophila" → "Drosophila melanogaster".

=== TISSUE INFERENCE RULES ===
12. If a cell line is mentioned, infer tissue of origin: HeLa → "cervix", HEK293/293T → "kidney", MCF-7/MDA-MB-231 → "breast", A549 → "lung", Jurkat → "blood", HCT116/Caco-2 → "colon", SH-SY5Y/Neuro2a → "brain", PC-3/LNCaP → "prostate"
13. If a cancer type names an organ (e.g., "gastric cancer", "breast cancer", "lung adenocarcinoma"), infer the tissue as that organ ("stomach", "breast", "lung")

=== DISEASE INFERENCE RULES ===
14. If studying healthy, control, or normal samples with NO disease mentioned → extract disease_state as "normal"
15. If a cancer cell line is used, extract the associated cancer type as disease_state:
    HeLa → "cervical adenocarcinoma", MCF-7/MDA-MB-231 → "breast carcinoma", A549 → "lung adenocarcinoma",
    HCT116 → "colorectal carcinoma", Caco-2 → "colorectal carcinoma", K562 → "chronic myeloid leukemia",
    Jurkat → "T-cell lymphoma", PC-3 → "prostate carcinoma", LNCaP → "prostate carcinoma",
    U2OS → "osteosarcoma", HepG2 → "hepatocellular carcinoma", SH-SY5Y → "neuroblastoma"

=== CELL TYPE RULES ===
16. For cell_type: extract the BIOLOGICAL cell type, not the cell line name.
    If only a cell line is mentioned, infer the biological cell type:
    MCF-7/MDA-MB-231 → "epithelial cell", Jurkat → "T cell", K562 → "myeloid cell",
    THP-1/U937 → "monocyte", HepG2 → "hepatocyte", SH-SY5Y → "neuron",
    NIH3T3 → "fibroblast", C2C12 → "myoblast", RAW264.7 → "macrophage"
17. If a cell line AND a biological cell type are both mentioned, prefer the biological cell type.


=== SAMPLE SOURCE RULES ===
18. sample_source is the broad SDRF material class for the biological material analyzed in the submitted PXD MS experiment. Return only: "tissue", "cell line", "primary cells", "biofluid", "plasma", "serum", "whole organism", or "organoid". If multiple distinct supported classes were analyzed, return the applicable classes as a comma-separated list.
19. Normalize only from explicit PXD-MS sample evidence: named established or immortalized cell lines and their cultures → "cell line"; donor-derived or primary cells → "primary cells"; organs, biopsies, tumors, and tissue microarrays → "tissue"; serum or plasma → their respective class; other liquid biological specimens → "biofluid"; intact organisms or microbial cultures → "whole organism"; organoids → "organoid". This field-specific controlled normalization may differ from the exact source wording, but its evidence sentence must explicitly establish the material used for the PXD MS experiment.
20. NEVER output "cell culture", a cell-line name, anatomy, cell type, donor/patient description, specimen format, extracellular vesicles, protein fraction, experimental model, preparation, institution, repository, or supplier as sample_source. If no allowed class is explicitly supported for the PXD MS sample, return "unknown".

=== YOUR TASK ===

TEXT:
{descriptor}

Now apply the reasoning protocol above. Output THOUGHT PROCESS then FINAL JSON."""


TECHNICAL_PROMPT = """You are a scientific metadata extraction agent specializing in mass spectrometry. Extract ONLY values EXPLICITLY stated in the text.

FIELDS TO EXTRACT:
- acquisition method: MS acquisition strategy (DDA, DIA, PRM, SRM, targeted)
- alkylation reagent: Cysteine alkylation chemical (iodoacetamide, chloroacetamide, NEM)
- alkylation concentration: Concentration of alkylation reagent
- cleavage agent: Protease(s) used (trypsin, Lys-C, chymotrypsin, GluC)
- collision energy: Fragmentation energy (NCE, eV values)
- enrichment method: Enrichment technique (IMAC, TiO2, antibody, affinity)
- fractionation method: Fractionation approach (SCX, high-pH, bRP, gel)
- fragmentation method: MS fragmentation type (HCD, CID, ETD, EThcD)
- instrument: Mass spectrometer model (Q Exactive, Orbitrap Fusion, timsTOF)
- ionization type: Ionization source (ESI, nanoESI, MALDI)
- labeling: Quantification method (TMT, iTRAQ, SILAC, label-free)
- reduction reagent: Disulfide reduction chemical (DTT, TCEP, BME)
- reduction concentration: Concentration of reduction reagent


=== REASONING PROTOCOL ===

For EACH field, follow this structured search:

1. FIELD: [field_name]
   SEARCH: Scanning for [domain-specific terms]...
   FOUND: "[exact quote]" in sentence "[context]"
   DECISION: Extract "[value]" | Mark as "unknown"

=== EXAMPLE ===

TEXT: "Peptides were analyzed using a Q Exactive HF mass spectrometer with HCD fragmentation at NCE 28. Samples were labeled with TMT 10-plex."

THOUGHT PROCESS:
1. FIELD: instrument
   SEARCH: Scanning for MS instruments (Orbitrap, Q Exactive, TOF, Exploris...)
   FOUND: "Q Exactive HF" in "analyzed using a Q Exactive HF mass spectrometer"
   DECISION: Extract "Q Exactive HF"

2. FIELD: fragmentation method
   SEARCH: Scanning for fragmentation types (HCD, CID, ETD...)
   FOUND: "HCD" in "with HCD fragmentation"
   DECISION: Extract "HCD"

3. FIELD: collision energy
   SEARCH: Scanning for NCE, eV, collision energy values...
   FOUND: "NCE 28" in "HCD fragmentation at NCE 28"
   DECISION: Extract "NCE 28"

4. FIELD: labeling
   SEARCH: Scanning for quantification labels (TMT, iTRAQ, SILAC...)
   FOUND: "TMT 10-plex" in "labeled with TMT 10-plex"
   DECISION: Extract "TMT 10-plex"

5. FIELD: cleavage agent
   SEARCH: Scanning for proteases (trypsin, Lys-C...)
   FOUND: None mentioned
   DECISION: Mark as "unknown"

FINAL JSON:
{{
  "acquisition method": ["unknown", ""],
  "alkylation reagent": ["unknown", ""],
  "alkylation concentration": ["unknown", ""],
  "cleavage agent": ["unknown", ""],
  "collision energy": ["NCE 28", "HCD fragmentation at NCE 28"],
  "enrichment method": ["unknown", ""],
  "fractionation method": ["unknown", ""],
  "fragmentation method": ["HCD", "with HCD fragmentation"],
  "instrument": ["Q Exactive HF", "analyzed using a Q Exactive HF mass spectrometer"],
  "ionization type": ["unknown", ""],
  "labeling": ["TMT 10-plex", "labeled with TMT 10-plex"],
  "reduction reagent": ["unknown", ""],
  "reduction concentration": ["unknown", ""],
}}

=== STRICT RULES ===
1. Copy values EXACTLY as written in text
2. If not explicitly stated → "unknown" with empty evidence ""
3. Each value = [extracted_value, evidence_sentence]
4. CRITICAL: The evidence sentence MUST contain the exact extracted value as a substring. If the value doesn't appear in the sentence, you have the wrong evidence.
5. Complete ALL fields systematically

=== LABELING INFERENCE RULE ===
6. For the "labeling" field ONLY: if no labeling or quantification strategy is mentioned anywhere in the text (no TMT, iTRAQ, SILAC, dimethyl labeling, ICAT, or other isobaric/metabolic labels), then the experiment is label-free. Extract "label-free" with evidence from any sentence describing the quantification or MS analysis approach (e.g., "peptides were analyzed by LC-MS/MS"). Do NOT leave labeling as "unknown" — proteomics experiments are always either labeled or label-free.
7. Also extract "label-free" if the text explicitly mentions "label-free", "LFQ", "spectral counting", "emPAI", or "intensity-based" quantification.

=== YOUR TASK ===

TEXT:
{descriptor}

Now apply the reasoning protocol above. Output THOUGHT PROCESS then FINAL JSON."""


EXPERIMENTAL_DESIGN_PROMPT = """You are a scientific metadata extraction agent specializing in experimental design. Extract values from the text, using inference ONLY where indicated.

FIELDS TO EXTRACT:
- biological_replicate: Numeric count of distinct biological units (can INFER from "3 mice", "n=5 patients")
- technical_replicate: Numeric count of repeated measurements of same material (can INFER from "triplicate injections")
- experimental_design: Study structure (INFER from "treated vs control", "time course")
- factor_value: Variables defining groups (treatment, genotype, condition)
- number_of_fractions: Total fractions if fractionation applied
- number_of_technical_replicates: Count of technical replicates
- number_of_biological_replicates: Count of biological replicates
- number_of_samples: Total distinct biological specimens or materials processed for the submitted PXD MS experiment

=== REASONING PROTOCOL ===

For EACH field, follow this structured search:

1. FIELD: [field_name]
   SEARCH: Scanning for [relevant patterns]...
   FOUND: "[quote]" in "[context]"
   INFERENCE: [explain reasoning if inferring]
   DECISION: Extract "[value]" | Mark as "unknown"

=== EXAMPLE ===

TEXT: "Liver samples from 5 wild-type and 5 knockout mice were analyzed. Each sample was digested and run in technical duplicate. Proteins were fractionated into 12 high-pH fractions."

THOUGHT PROCESS:
1. FIELD: biological_replicate
   SEARCH: Scanning for biological units (mice, patients, donors, animals...)
   FOUND: "5 wild-type and 5 knockout mice" in "Liver samples from 5 wild-type..."
   INFERENCE: 5 mice per group = distinct biological units
   DECISION: Extract "10"

2. FIELD: number_of_biological_replicates
   SEARCH: Counting biological samples mentioned...
   FOUND: "5 wild-type and 5 knockout"
   INFERENCE: 5 + 5 = 10 total biological replicates
   DECISION: Extract "10"

3. FIELD: technical_replicate
   SEARCH: Scanning for repeated measurements...
   FOUND: "technical duplicate" in "run in technical duplicate"
   INFERENCE: duplicate = 2 repeated measurements
   DECISION: Extract "2"

4. FIELD: number_of_technical_replicates
   SEARCH: Counting technical replicates...
   FOUND: "technical duplicate"
   INFERENCE: duplicate = 2
   DECISION: Extract "2"

5. FIELD: experimental_design
   SEARCH: Scanning for study structure, comparisons...
   FOUND: "wild-type and knockout"
   INFERENCE: Comparison between genotypes
   DECISION: Extract "wild-type vs knockout comparison"

6. FIELD: factor_value
   SEARCH: Scanning for experimental variables...
   FOUND: "wild-type" and "knockout"
   DECISION: Extract "genotype (wild-type, knockout)"

7. FIELD: number_of_fractions
   SEARCH: Scanning for fraction counts...
   FOUND: "12 high-pH fractions"
   DECISION: Extract "12"

8. FIELD: number_of_samples
   SEARCH: Counting distinct PXD-MS biological specimens or materials...
   INFERENCE: 10 mice described
   DECISION: Extract "10"

FINAL JSON:
{{
   "biological_replicate": ["10", "Liver samples from 5 wild-type and 5 knockout mice"],
   "technical_replicate": ["2", "run in technical duplicate"],
  "experimental_design": ["wild-type vs knockout comparison", "5 wild-type and 5 knockout mice were analyzed"],
  "factor_value": ["genotype (wild-type, knockout)", "5 wild-type and 5 knockout mice"],
  "number_of_fractions": ["12", "fractionated into 12 high-pH fractions"],
  "number_of_technical_replicates": ["2", "run in technical duplicate"],
  "number_of_biological_replicates": ["10", "5 wild-type and 5 knockout mice"],
  "number_of_samples": ["10", "5 wild-type and 5 knockout mice"],
}}

=== RULES ===
1. For experimental_design, factor_value, replicates: INFERENCE is allowed
2. For other fields: copy EXACTLY as written
3. If unclear → "unknown" with empty evidence ""
4. Each value = [extracted_value, evidence_sentence]
5. CRITICAL: The evidence sentence MUST contain the exact extracted value as a substring. If the value doesn't appear in the sentence, you have the wrong evidence.
6. Complete ALL fields systematically

=== REPLICATE TYPE-SAFETY RULES ===
7. For biological_replicate and number_of_biological_replicates, output only a numeric count of distinct biological units explicitly tied to the submitted PXD MS experiment. A cell line, condition, treatment, probe, clone, fraction, sample description, or count from a non-MS assay is never a replicate count.
8. For technical_replicate and number_of_technical_replicates, output only a numeric count explicitly tied to repeated MS analysis, injection, or preparation of the same submitted sample material. Never output a bare phrase such as "technical replicates".
9. For replicate fields only, an explicit count word such as single, duplicate, triplicate, or quadruplicate may be rendered as 1, 2, 3, or 4 with that source phrase as evidence. The PRIDE RAW data-file manifest alone cannot establish a biological or technical replicate count. If the PXD-MS unit, role, or count is not explicit, return "unknown".

=== DEFAULT VALUE RULES ===
10. If no fractionation or pre-fractionation is described anywhere in the text → extract number_of_fractions as "1"

=== SAMPLE COUNT EVIDENCE RULES ===
11. For number_of_samples, count only distinct biological specimens or materials processed in the submitted PXD MS experiment. Prioritize explicitly PXD-MS-linked evidence from METHODS, RESULTS, and FIGURE CAPTIONS. Exclude paper background, ancillary assays, validation cohorts, and samples not analyzed by the submitted MS experiment.
12. A RAW data-file count is an acquisition count, not a biological-sample count. Never equate number_of_samples with RAW files, fractions, injections, technical replicates, or blanks; never multiply biological samples by fractions or repeat runs.
13. Output a numeric number_of_samples only when the PXD-MS biological count is explicitly stated or when a complete PXD-MS sample inventory is explicitly enumerated. You may normalize an explicit count phrase such as "one sample" to "1" or sum explicitly enumerated PXD-MS groups such as "5 wild-type and 5 knockout mice" to "10"; retain the source phrase as evidence.
14. A single named PXD-MS specimen or material may normalize to "1" only when the text explicitly establishes it as the complete PXD-MS sample set. If the PXD-MS sample count, role, or completeness is unclear, return "unknown".

=== MANIFEST SCOPE RULE ===
15. Use the PRIDE RAW data-file manifest only to prevent invalid sample or replicate count inference. For experimental_design and factor_value, ignore the manifest completely: derive design comparisons and factors only from PXD-MS-linked publication evidence. Never use RAW filenames to select, expand, suppress, or name a design comparison or factor.

=== YOUR TASK ===

TEXT:
{descriptor}

Now apply the reasoning protocol above. Output THOUGHT PROCESS then FINAL JSON."""
