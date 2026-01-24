"""
Validation agent for extraction quality assurance.

Provides schema validation, evidence checking, and confidence scoring
to ensure extraction quality without always requiring LLM calls.
"""

import json
import re
from typing import Dict, List, Any, Optional, Tuple

from core.llm import LLMClient
from core.logging import get_logger
from .schema import (
    ValidationMode, FieldSchema, ValidationResult, ConfidenceMetrics,
    ALL_FIELDS, BIOLOGICAL_FIELDS, TECHNICAL_FIELDS
)

logger = get_logger(__name__)


# ============================================================================
# LLM Validation Prompt
# ============================================================================

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
    """
    Validates and scores extraction quality.
    
    Supports three modes:
    - SCHEMA_ONLY: Fast rule-based validation (no LLM)
    - LLM_ONLY: LLM-based validation (original behavior)
    - HYBRID: Schema first, LLM for low-confidence cases
    """
    
    def __init__(self, mode: ValidationMode = ValidationMode.SCHEMA_ONLY):
        """
        Initialize the validation agent.
        
        Args:
            mode: Validation strategy to use
        """
        self.mode = mode
        self._llm: Optional[LLMClient] = None
    
    @property
    def llm(self) -> LLMClient:
        """Lazy-load LLM client only when needed."""
        if self._llm is None:
            self._llm = LLMClient()
        return self._llm
    
    # ========================================================================
    # Main Validation Methods
    # ========================================================================
    
    def validate(self, text: str, metadata: dict, 
                 mode: Optional[ValidationMode] = None) -> dict:
        """
        Validate and optionally correct extracted metadata.
        
        Args:
            text: Source document text
            metadata: Extracted metadata dict
            mode: Override default validation mode
            
        Returns:
            Validated (and possibly corrected) metadata
        """
        mode = mode or self.mode
        
        logger.info("Validating extraction (mode=%s)", mode.value)
        
        if mode == ValidationMode.SCHEMA_ONLY:
            result = self.validate_schema(metadata)
            corrected = self._fix_format_errors(metadata, result)
            return self._add_confidence(corrected, text)
        
        elif mode == ValidationMode.LLM_ONLY:
            return self._validate_with_llm(text, metadata)
        
        elif mode == ValidationMode.HYBRID:
            # First do schema validation
            result = self.validate_schema(metadata)
            confidence = self.calculate_confidence(metadata, text)
            
            # If confidence is low, use LLM
            if confidence.overall < 0.7 or not result.is_valid:
                logger.info("Low confidence (%.2f), using LLM validation", 
                           confidence.overall)
                return self._validate_with_llm(text, metadata)
            
            corrected = self._fix_format_errors(metadata, result)
            return self._add_confidence(corrected, text)
        
        return metadata
    
    def validate_schema(self, metadata: dict) -> ValidationResult:
        """
        Validate metadata against format rules (dynamic - checks all fields).
        
        Args:
            metadata: Extracted metadata dict
            
        Returns:
            ValidationResult with errors and warnings
        """
        errors = []
        warnings = []
        field_scores = {}
        
        # Dynamically validate ALL fields in metadata
        for field_name, value in metadata.items():
            # Skip internal metadata fields
            if field_name.startswith('_'):
                continue
            
            # Check format
            is_valid, error = self._validate_field_format(field_name, value)
            
            if not is_valid:
                errors.append(error)
                field_scores[field_name] = 0.0
            else:
                field_scores[field_name] = 1.0
        
        # Also check for missing predefined fields (as warnings only)
        for field_name, schema in ALL_FIELDS.items():
            if field_name not in metadata and schema.required:
                warnings.append(f"Missing field: {field_name}")
        
        is_valid = len(errors) == 0
        
        return ValidationResult(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            field_scores=field_scores,
            confidence=sum(field_scores.values()) / max(len(field_scores), 1)
        )
    
    def _validate_field_format(self, field_name: str, value: Any) -> tuple:
        """
        Validate a single field's format. Accepts:
        - List format: [value, evidence]
        - Normalized object: {value, evidence, ontology_id, ...}
        - Resolved object: {resolved, confidence, status, sources, ...}
        
        Returns:
            (is_valid, error_message)
        """
        if value is None:
            return False, f"{field_name}: Value is None"
        
        # Accept normalized/enriched object format
        if isinstance(value, dict):
            # Normalized format: {value, evidence, ontology_id, ...}
            if 'value' in value or 'resolved' in value:
                val = value.get('value') or value.get('resolved')
                evidence = value.get('evidence', '')
                
                # Check for unknown with evidence
                if val == "unknown" and evidence:
                    return False, f"{field_name}: 'unknown' values must have empty evidence"
                
                return True, ""
            else:
                return False, f"{field_name}: Dict missing 'value' or 'resolved' key"
        
        # Accept list format: [value, evidence]
        if isinstance(value, list):
            if len(value) != 2:
                return False, f"{field_name}: Expected [value, evidence], got {len(value)} elements"
            
            val, evidence = value
            
            if not isinstance(val, str):
                return False, f"{field_name}: Value should be string"
            
            if not isinstance(evidence, str):
                return False, f"{field_name}: Evidence should be string"
            
            # Unknown with evidence is invalid
            if val == "unknown" and evidence:
                return False, f"{field_name}: 'unknown' values must have empty evidence"
            
            return True, ""
        
        # String alone is not valid format
        if isinstance(value, str):
            return False, f"{field_name}: Expected [value, evidence] or object, got string"
        
        return False, f"{field_name}: Unknown format {type(value).__name__}"
    
    def validate_evidence(self, metadata: dict, text: str) -> Dict[str, float]:
        """
        Check if evidence strings actually contain extracted values.
        Handles both list format and normalized object format.
        
        Args:
            metadata: Extracted metadata
            text: Source document text
            
        Returns:
            Dict of field_name -> evidence_score (0-1)
        """
        scores = {}
        text_lower = text.lower()
        
        for field_name, value in metadata.items():
            if field_name.startswith('_'):  # Skip metadata fields
                continue
            
            # Extract val and evidence from different formats
            val, evidence = self._extract_value_evidence(value)
            
            if val is None:
                scores[field_name] = 0.0
                continue
            
            # Unknown values with empty evidence are valid
            if val == "unknown" and not evidence:
                scores[field_name] = 1.0
                continue
            
            score = 0.0
            
            # Check 1: Value appears in source text
            if val.lower() in text_lower:
                score += 0.5
            
            # Check 2: Value appears in evidence
            if evidence and val.lower() in evidence.lower():
                score += 0.3
            
            # Check 3: Evidence appears in source text
            if evidence and evidence.lower() in text_lower:
                score += 0.2
            
            scores[field_name] = min(score, 1.0)
        
        return scores
    
    def _extract_value_evidence(self, value: Any) -> tuple:
        """
        Extract (value, evidence) from various formats.
        
        Returns:
            (value_str, evidence_str) or (None, None) if invalid
        """
        if isinstance(value, list) and len(value) == 2:
            return value[0], value[1]
        
        if isinstance(value, dict):
            val = value.get('value') or value.get('resolved')
            evidence = value.get('evidence', '')
            return val, evidence
        
        return None, None
    
    def calculate_confidence(self, metadata: dict, text: str) -> ConfidenceMetrics:
        """
        Calculate confidence metrics for an extraction.
        
        Args:
            metadata: Extracted metadata
            text: Source document text
            
        Returns:
            ConfidenceMetrics object
        """
        # Schema validation
        schema_result = self.validate_schema(metadata)
        format_score = schema_result.confidence
        
        # Evidence checking
        evidence_scores = self.validate_evidence(metadata, text)
        evidence_score = (sum(evidence_scores.values()) / 
                         max(len(evidence_scores), 1))
        
        # Completeness (non-unknown fields)
        known_fields = 0
        total_fields = 0
        for field_name, value in metadata.items():
            if field_name.startswith('_'):
                continue
            total_fields += 1
            
            val, _ = self._extract_value_evidence(value)
            if val and val != "unknown":
                known_fields += 1
        
        completeness = known_fields / max(total_fields, 1)
        
        # Overall confidence (weighted average)
        overall = (
            format_score * 0.3 +
            evidence_score * 0.5 +
            completeness * 0.2
        )
        
        return ConfidenceMetrics(
            overall=overall,
            evidence_score=evidence_score,
            completeness=completeness,
            format_score=format_score,
        )
    
    # ========================================================================
    # Helper Methods
    # ========================================================================
    
    def _validate_with_llm(self, text: str, metadata: dict) -> dict:
        """Use LLM to validate and correct metadata."""
        json_str = json.dumps(metadata, indent=2)
        prompt = VALIDATION_PROMPT.format(text=text, json_data=json_str)
        
        logger.debug("Calling LLM for validation...")
        
        corrected_json_str = self.llm.get_completion(
            [{"role": "user", "content": prompt}], 
            temperature=0.0
        )
        
        try:
            # Extract JSON from response
            corrected = self._extract_json(corrected_json_str)
            return self._add_confidence(corrected, text)
        except json.JSONDecodeError:
            logger.warning("Validator returned invalid JSON, keeping original")
            return self._add_confidence(metadata, text)
    
    def _extract_json(self, text: str) -> dict:
        """Extract JSON object from LLM response."""
        # Find JSON object using brace matching
        start_idx = text.find('{')
        if start_idx == -1:
            raise json.JSONDecodeError("No JSON found", text, 0)
        
        brace_count = 0
        end_idx = start_idx
        for i, char in enumerate(text[start_idx:], start=start_idx):
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    end_idx = i + 1
                    break
        
        json_str = text[start_idx:end_idx]
        return json.loads(json_str)
    
    def _fix_format_errors(self, metadata: dict, 
                           result: ValidationResult) -> dict:
        """Auto-fix common format errors."""
        fixed = {}
        
        for field_name, value in metadata.items():
            if field_name.startswith('_'):
                fixed[field_name] = value
                continue
            
            # Fix: Not a list → wrap in list with empty evidence
            if not isinstance(value, list):
                if isinstance(value, str):
                    fixed[field_name] = [value, ""]
                    logger.debug("Fixed %s: wrapped string in list", field_name)
                else:
                    fixed[field_name] = ["unknown", ""]
                continue
            
            # Fix: Single element list → add empty evidence
            if len(value) == 1:
                fixed[field_name] = [value[0], ""]
                logger.debug("Fixed %s: added empty evidence", field_name)
                continue
            
            # Fix: Nested list [[val, ev]] → [val, ev]
            if len(value) == 1 and isinstance(value[0], list):
                fixed[field_name] = value[0]
                logger.debug("Fixed %s: flattened nested list", field_name)
                continue
            
            fixed[field_name] = value
        
        return fixed
    
    def _add_confidence(self, metadata: dict, text: str) -> dict:
        """Add confidence metrics to metadata."""
        confidence = self.calculate_confidence(metadata, text)
        metadata['_confidence'] = confidence.to_dict()
        return metadata
    
    # ========================================================================
    # Convenience Methods
    # ========================================================================
    
    def get_confidence(self, metadata: dict, text: str) -> float:
        """Get overall confidence score for an extraction."""
        return self.calculate_confidence(metadata, text).overall
    
    def is_high_quality(self, metadata: dict, text: str, 
                        threshold: float = 0.7) -> bool:
        """Check if extraction meets quality threshold."""
        return self.get_confidence(metadata, text) >= threshold
