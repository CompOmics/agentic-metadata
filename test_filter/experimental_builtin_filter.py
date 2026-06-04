"""Approach B — experimental design agent: single prompt with built-in proteomics section detection."""
import re, os, json, argparse, anthropic
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

_MODEL = "claude-sonnet-4-6"
_DEFAULT_OUTPUT = Path(__file__).parent / "builtin_filter_experimental"

_PROMPT = """You are a scientific metadata extraction agent specializing in experimental design.

CRITICAL FIRST STEP — IDENTIFY PROTEOMICS SECTIONS:
Before extracting, read ALL sections and identify which describe the proteomics or mass spectrometry experiment.
Extract ONLY from those sections. IGNORE experimental design details from non-MS experiments
(e.g., PCR replicates, ELISA sample counts, IHC cohorts) unless those samples were ALSO analyzed by MS.
For multi-technique papers, report values for the primary LC-MS/MS experiment only.

FIELDS TO EXTRACT (from MS experiment sections only):
- biological_replicate: Distinct biological units (can INFER from "3 mice", "n=5 patients")
- technical_replicate: Repeated measurements of same material (can INFER from "triplicate injections")
- experimental_design: Study structure (INFER from context — must be ONE of: "treated vs control",
  "case vs control", "time course", "dose response", "cross-sectional", "longitudinal", "unknown")
- factor_value: Variables defining experimental groups (treatment, genotype, condition)
- number_of_fractions: Total fractions if fractionation applied. If none described → "1"
- number_of_technical_replicates: Count of technical replicates
- number_of_biological_replicates: Count of biological replicates. If none described → "1"
- number_of_samples: Total biological samples run on the mass spectrometer

For EACH field output a 2-element list: [value, evidence_sentence].
- Element 0: SHORT, CLEAN value only (max ~5 words). No reasoning text.
- Element 1: evidence sentence (put reasoning HERE, not in element 0).
- VERBATIM values (number_of_*): plain number. Evidence MUST contain the exact value.
- INFERRED values: prefix evidence with "inferred: " followed by verbatim quote.
- If unclear → ["unknown", ""]

REQUIRED OUTPUT FORMAT (return ONLY this JSON):
{{
  "biological_replicate": ["unknown", ""],
  "technical_replicate": ["unknown", ""],
  "experimental_design": ["unknown", ""],
  "factor_value": ["unknown", ""],
  "number_of_fractions": ["unknown", ""],
  "number_of_technical_replicates": ["unknown", ""],
  "number_of_biological_replicates": ["unknown", ""],
  "number_of_samples": ["unknown", ""]
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
        print(f"[experimental-builtin] {file.name}")
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
