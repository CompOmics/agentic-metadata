"""Approach A — experimental design agent: section_filter -> strict extraction."""
import re, json, argparse, anthropic
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

_EXTRACT_MODEL = "claude-sonnet-4-6"
_DEFAULT_OUTPUT = Path(__file__).parent / "two_pass_experimental"

_PROMPT = """You are a scientific metadata extraction agent. Extract values from the text, using inference ONLY where indicated.

This paper may describe multiple experimental techniques. Extract ONLY from sections describing the proteomics or mass spectrometry experiment. Ignore all other experimental contexts.

FIELDS TO EXTRACT:
- biological_replicate: Type of distinct biological unit (e.g. "mouse", "patient", "cell line", "cell culture").
  Name the unit type only — not the count, not the full sample description.
  (can INFER from "3 mice", "n=5 patients", "cultured cells")
- technical_replicate: Repeated LC-MS/MS injections of the same biological material.
  NOT different experimental conditions — those belong in factor_value.
  (can INFER from "triplicate injections", "analyzed in duplicate")
- experimental_design: Study structure (INFER from context — must be ONE of: "treated vs control",
  "case vs control", "time course", "dose response", "cross-sectional", "longitudinal", "unknown")
- factor_value: The variable manipulated between experimental groups (treatment, genotype, condition,
  MS acquisition method). NOT the sample name, organism species, or strain identifier.
- number_of_fractions: Offline fractions per sample that separate peptides by chemical properties
  (SCX, high-pH RP, gel bands, OFFGEL). Identical aliquots split for replicate injections are NOT
  fractions. If multiple fractionation schemes described, use the largest. If none → "1"
- number_of_technical_replicates: Count of repeated injections per biological sample.
  Must be consistent with technical_replicate — if technical_replicate is unknown, return "1"
- number_of_biological_replicates: Count of independent biological preparations. If none described → "1"
- number_of_samples: Count of distinct biological preparations run on the MS.
  Do NOT multiply by technical replicates or fractions.

For EACH field output a 2-element list: [value, evidence_sentence].
- Element 0: SHORT, CLEAN value (max ~5 words). No reasoning text.
- Element 1: evidence sentence (put reasoning HERE, not in element 0).
- Element 0: the value. If copied verbatim from text, write it as-is. If inferred or calculated, prefix with "inferred: ". For number_of_* fields the value is always a plain number.
- Element 1: always a verbatim sentence from the paper — no reasoning, no prefix, regardless of whether the value was inferred. For number_of_* fields the sentence must contain the relevant number.
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


def extract_metadata(descriptor, model=_EXTRACT_MODEL):
    client = anthropic.Anthropic()
    r = client.messages.create(model=model, max_tokens=2048,
        messages=[{"role": "user", "content": _PROMPT.format(descriptor=descriptor)}])
    return r.content[0].text


def process_files(input_dir, output_dir, limit=None, model=_EXTRACT_MODEL):
    files = sorted(Path(input_dir).glob("**/*.txt"))
    if limit: files = files[:limit]
    if not files: print(f"No .txt files in {input_dir}"); return
    output_dir.mkdir(parents=True, exist_ok=True)
    for file in files:
        print(f"[experimental] {file.name}")
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
    p.add_argument("--model", default=_EXTRACT_MODEL)
    a = p.parse_args()
    process_files(a.input, Path(a.output), a.limit, a.model)
