from pathlib import Path
import json
from .llm import LLMClient
from .logging import get_logger
from validation.validator import ValidationAgent

logger = get_logger(__name__)


def normalize_output(data: dict) -> dict:
    """
    Post-processor to fix common LLM output format issues:
    1. Remove unwanted keys (THOUGHT PROCESS, FINAL JSON, raw_output)
    2. Flatten nested arrays [[val, ev]] -> [val, ev]
    3. Fix single values without evidence [val] -> [val, ""]
    4. Validate evidence contains the extracted value
    """
    if "raw_output" in data:
        # Can't normalize raw output, return as-is
        return data
    
    normalized = {}
    unwanted_keys = {"THOUGHT PROCESS", "FINAL JSON", "raw_output", "pmid"}
    
    for field, value in data.items():
        # Skip unwanted keys
        if field in unwanted_keys:
            continue
        
        # Handle different value formats
        if isinstance(value, list):
            # Fix: nested arrays [[val, ev]] → [val, ev]
            if len(value) == 1 and isinstance(value[0], list):
                value = value[0]
            
            # Fix: multiple nested arrays [[val1, ev1], [val2, ev2]] → take first
            if len(value) > 0 and isinstance(value[0], list):
                value = value[0]
            
            # Fix: single value without evidence [val] → [val, ""]
            if len(value) == 1 and isinstance(value[0], str):
                value = [value[0], ""]
            
            # Validate: evidence must contain value (for non-unknown values)
            if len(value) == 2 and isinstance(value[0], str) and isinstance(value[1], str):
                val, evidence = value
                if val != "unknown" and val and evidence:
                    # Check if value appears in evidence
                    if val.lower() not in evidence.lower():
                        logger.warning("Evidence mismatch for '%s': '%s' not in evidence", field, val)
                        # Keep the value but note the mismatch (don't reset to unknown)
        
        normalized[field] = value
    
    return normalized


class BaseExtractor:
    def __init__(self, input_dir: str, output_dir: str, temperatures=None, use_validation=False):
        self.input_path = Path(input_dir)
        self.output_path = Path(output_dir)
        self.temperatures = temperatures or [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]
        self.llm = LLMClient()
        self.validator = ValidationAgent() if use_validation else None

    def get_prompt(self, text: str) -> str:
        """Override this method in subclasses to return the specific prompt"""
        raise NotImplementedError

    def run(self):
        logger.info("Processing with temperatures: %s", self.temperatures)
        logger.info("Base output folder: %s", self.output_path)
        
        all_results = {}
        for temp in self.temperatures:
            logger.info("="*60)
            logger.info("Running with temperature: %.1f", temp)
            logger.info("="*60)
            
            temp_folder = self.output_path / f"temp_{temp:.1f}"
            temp_folder.mkdir(parents=True, exist_ok=True)
            
            results = self.process_files(temp_folder, temp)
            all_results[temp] = results
            
            logger.info("Completed temperature %.1f: %d files processed", temp, len(results))
            
        return all_results

    def process_files(self, output_folder: Path, temperature: float) -> dict:
        files = list(self.input_path.glob('**/*.txt'))
        if not files:
            logger.warning("No .txt files found in %s", self.input_path)
            return {}
            
        results = {}
        for file in files:
            logger.info("Processing: %s (temperature=%.1f)", file.name, temperature)
            text = self.get_text_from_docs(file)
            prompt = self.get_prompt(text)
            
            # Call LLM
            metadata = self.llm.get_completion([{"role": "user", "content": prompt}], temperature)
            
            # --- START AGENTIC PARSING ---
            # Extract JSON more robustly - find the LAST complete JSON object
            json_str = None
            
            # First try: split on "FINAL JSON:" and get the last one
            if "FINAL JSON:" in metadata:
                parts = metadata.split("FINAL JSON:")
                # Take the last part (in case there are multiple)
                json_str = parts[-1].strip()
                thought_process = parts[0].replace("THOUGHT PROCESS:", "").strip()
                logger.debug("Agent thoughts: %s...", thought_process[:100])
            
            # Extract just the JSON object using bracket matching
            if json_str:
                # Find the first '{' and match to closing '}'
                start_idx = json_str.find('{')
                if start_idx != -1:
                    # Count braces to find matching close
                    brace_count = 0
                    end_idx = start_idx
                    for i, char in enumerate(json_str[start_idx:], start=start_idx):
                        if char == '{':
                            brace_count += 1
                        elif char == '}':
                            brace_count -= 1
                            if brace_count == 0:
                                end_idx = i + 1
                                break
                    json_str = json_str[start_idx:end_idx]
            else:
                # Fallback: find the last complete JSON object in the entire output
                start_idx = metadata.rfind('{')
                if start_idx != -1:
                    brace_count = 0
                    end_idx = len(metadata)
                    for i, char in enumerate(metadata[start_idx:], start=start_idx):
                        if char == '{':
                            brace_count += 1
                        elif char == '}':
                            brace_count -= 1
                            if brace_count == 0:
                                end_idx = i + 1
                                break
                    json_str = metadata[start_idx:end_idx]
            # --- END AGENTIC PARSING ---
            
            try:
                # Try to sanitize common JSON issues before parsing
                if json_str:
                    # Fix: escaped quotes inside strings that break JSON
                    # Replace backslash-quote with single quotes temporarily
                    import re
                    
                    # First attempt: direct parse
                    try:
                        metadata_json = json.loads(json_str)
                    except json.JSONDecodeError:
                        # Second attempt: try to extract using regex pattern for our format
                        # Pattern: "field": ["value", "evidence"]
                        extracted = {}
                        pattern = r'"([^"]+)":\s*\["([^"]*)",\s*"([^"]*)"\]'
                        matches = re.findall(pattern, json_str, re.DOTALL)
                        
                        if matches:
                            for field, value, evidence in matches:
                                extracted[field] = [value, evidence]
                            metadata_json = extracted
                            print(f"  [Recovered {len(matches)} fields using regex]")
                        else:
                            # Third attempt: try to fix common issues
                            fixed_json = json_str.replace('\\"', "'")  # Replace \" with '
                            try:
                                metadata_json = json.loads(fixed_json)
                            except json.JSONDecodeError:
                                raise  # Re-raise to trigger fallback
                else:
                    metadata_json = {}
                
                # Run Validation if enabled
                if self.validator:
                    print(f"  Validating {file.name}...")
                    metadata_json = self.validator.validate(text, metadata_json)
                
                # Run post-processor to normalize output format
                metadata_json = normalize_output(metadata_json)
                    
            except json.JSONDecodeError:
                print(f"Warning: Could not parse JSON for {file}. Saving raw output.")
                metadata_json = {"raw_output": metadata}
            
            output_filename = file.stem + ".json"
            output_file_path = output_folder / output_filename
            
            with open(output_file_path, 'w') as f:
                json.dump(metadata_json, f, indent=2)
            
            results[str(file)] = metadata_json
            print(f"Saved: {output_file_path}")
            
        return results

    def get_text_from_docs(self, path) -> str:
        with open(path, 'r') as file:
            text = file.read()
        return text

