"""Approach B — technical agent: single prompt with built-in proteomics section detection."""
import re, os, json, argparse, anthropic
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

_MODEL = "claude-sonnet-4-6"
_DEFAULT_OUTPUT = Path(__file__).parent / "builtin_filter_technical"

_PROMPT = """You are a scientific metadata extraction agent specializing in mass spectrometry.

CRITICAL FIRST STEP — IDENTIFY PROTEOMICS SECTIONS:
Before extracting, read ALL sections and identify which describe LC-MS/MS or mass spectrometry experiments.
Extract ONLY from those sections. IGNORE non-MS techniques (PCR, western blot, ELISA, IHC, sequencing,
flow cytometry, microscopy) even if they describe protein or reagent use.
For multi-technique papers, focus exclusively on the LC-MS/MS sample preparation and instrument sections.

FIELDS TO EXTRACT (from MS sections only):
- acquisition_method: MS acquisition strategy (DDA, DIA, PRM, SRM, targeted)
- alkylation_reagent: Cysteine alkylation chemical (iodoacetamide, chloroacetamide, NEM). NOT fluorescent dyes.
- alkylation_concentration: Concentration of alkylation reagent
- cleavage_agent: Protease(s) used (trypsin, Lys-C, chymotrypsin, GluC)
- collision_energy: Fragmentation energy (NCE, eV values)
- enrichment_method: Enrichment technique (IMAC, TiO2, antibody, affinity)
- fractionation_method: Pre-MS fractionation (SCX, high-pH, bRP, gel). 2D-DIGE is NOT LC-MS fractionation.
- fragmentation_method: MS fragmentation type (HCD, CID, ETD, EThcD)
- instrument: PRIMARY LC-MS/MS mass spectrometer model. NOT secondary validation instruments.
- ionization_type: Ionization source (ESI, nanoESI, MALDI)
- labeling: Quantification method (TMT, iTRAQ, SILAC, label-free)
- reduction_reagent: Disulfide reduction chemical (DTT, TCEP, BME)
- reduction_concentration: Concentration of reduction reagent

LABELING INFERENCE RULE:
If no labeling strategy is mentioned (no TMT, iTRAQ, SILAC, dimethyl, ICAT), infer "label-free".
Prefix evidence with "inferred: " followed by a verbatim supporting quote.

For EACH field output a 2-element list: [value, evidence_sentence].
- Copy values EXACTLY as written in text
- If not found in MS sections → ["unknown", ""]
- Evidence MUST contain the extracted value as a substring (except inferred).

REQUIRED OUTPUT FORMAT (return ONLY this JSON):
{{
  "acquisition_method": ["unknown", ""],
  "alkylation_reagent": ["unknown", ""],
  "alkylation_concentration": ["unknown", ""],
  "cleavage_agent": ["unknown", ""],
  "collision_energy": ["unknown", ""],
  "enrichment_method": ["unknown", ""],
  "fractionation_method": ["unknown", ""],
  "fragmentation_method": ["unknown", ""],
  "instrument": ["unknown", ""],
  "ionization_type": ["unknown", ""],
  "labeling": ["unknown", ""],
  "reduction_reagent": ["unknown", ""],
  "reduction_concentration": ["unknown", ""]
}}
TEXT:
{descriptor}"""


def _parse_json(raw):
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    if m:
        try: return json.loads(m.group(1).strip())
        except json.JSONDecodeError: pass
    try: return json.loads(raw.strip())
    except json.JSONDecodeError: return {"raw_output": raw}


def extract_metadata(descriptor, model=_MODEL):
    client = anthropic.Anthropic()
    r = client.messages.create(model=model, max_tokens=2048,
        messages=[{"role": "user", "content": _PROMPT.format(descriptor=descriptor)}])
    return r.content[0].text


def process_files(input_dir, output_dir, limit=None, model=_MODEL):
    files = sorted(Path(input_dir).glob("**/*.txt"))
    if limit: files = files[:limit]
    if not files: print(f"No .txt files in {input_dir}"); return
    output_dir.mkdir(parents=True, exist_ok=True)
    for file in files:
        print(f"[technical-builtin] {file.name}")
        text = file.read_text(encoding="utf-8", errors="replace")
        result = _parse_json(extract_metadata(text, model=model))
        out = output_dir / (file.stem + ".json")
        out.write_text(json.dumps(result, indent=2))
        print(f"  saved: {out.name}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--input", default="/media/volume/bert_training_data_models/docs/")
    p.add_argument("--output", default=str(_DEFAULT_OUTPUT))
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--model", default=_MODEL)
    a = p.parse_args()
    process_files(a.input, Path(a.output), a.limit, a.model)
