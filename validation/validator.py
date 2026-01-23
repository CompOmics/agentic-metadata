import json
from core.llm import LLMClient

VALIDATION_PROMPT = """You are a QA Critic for scientific metadata extraction.
Your job is to verify that the extracted JSON metadata matches the Source Text and follows the Strict Rules.

SOURCE TEXT:
{text}

EXTRACTED JSON:
{json_data}

STRICT RULES TO ENFORCE:
1. All values must be EXPLICITLY in the text (exact substring match). Do not allow abbreviation expansions.
2. If not in text, value must be "unknown".
3. No hallucinations or inferred values that aren't supported by text.
4. "unknown" values must have empty evidence string "".
5. Each value must be a list: [value_string, evidence_string]. If it is not a list, FIX IT.

TASK:
- Review each field in the EXTRACTED JSON.
- If a value violates the rules (e.g. it is not in the text, or should be "unknown"), CORRECT it.
- If the extraction is perfect, return it as is.
- Return ONLY the final corrected JSON.

CORRECTED JSON:"""

class ValidationAgent:
    def __init__(self):
        self.llm = LLMClient()

    def validate(self, text: str, metadata: dict) -> dict:
        """
        Validates and corrects the metadata using the LLM.
        """
        json_str = json.dumps(metadata, indent=2)
        prompt = VALIDATION_PROMPT.format(text=text, json_data=json_str)
        
        # We use a low temperature for validation to be strict
        corrected_json_str = self.llm.get_completion(
            [{"role": "user", "content": prompt}], 
            temperature=0.0
        )
        
        try:
            return json.loads(corrected_json_str)
        except json.JSONDecodeError:
            print("Warning: Validator returned invalid JSON. Keeping original.")
            return metadata
