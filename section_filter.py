from openai import OpenAI
import logging

logger = logging.getLogger(__name__)

_FILTER_PROMPT = """You are a text filter for scientific papers. Extract and return ONLY the text relevant to a proteomics or mass spectrometry (MS) experiment.

Include verbatim:
1. Proteomics/MS methodology text: sample preparation for MS, LC-MS/MS instrument operation, protein/peptide identification, database search parameters, quantification methods.
2. Biological sample/subject descriptions for samples specifically analyzed by MS: patient cohorts, cell lines, tissues, organisms, disease conditions, treatment groups — but only those that underwent MS analysis.
3. Cohort descriptions, patient demographics, and sample collection text even if MS is not explicitly mentioned in that section, provided the paper's proteomics experiment uses those samples. The link to MS may be implicit from the overall study design.

Exclude:
- Non-MS techniques (RNA-seq, flow cytometry, western blot, microscopy, ELISA) unless those samples were ALSO analyzed by MS.
- General introduction or background not tied to the proteomics experiment.

For multi-omics papers, include only the arms involving mass spectrometry.

Return text verbatim. Do not summarize or paraphrase. If no proteomics content is found, return only: NO PROTEOMICS CONTENT

TEXT:
{text}"""


def filter_proteomics_sections(text: str, base_url: str, model: str, api_key: str = "") -> str:
    """
    Pass 1: filter manuscript text to proteomics-relevant sections only.

    Returns filtered verbatim text, or empty string if no proteomics content detected.
    Always runs at temperature=0.0 (deterministic selection, not extraction).
    """
    client = OpenAI(base_url=base_url, api_key=api_key)

    response = client.chat.completions.create(
        messages=[{"role": "user", "content": _FILTER_PROMPT.format(text=text)}],
        model=model,
        temperature=0.0,
    )

    result = response.choices[0].message.content.strip()

    if result == "NO PROTEOMICS CONTENT":
        logger.warning("Filter returned NO PROTEOMICS CONTENT — paper may not contain MS data")
        return ""

    return result
