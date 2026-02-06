"""
Integration Agent for enriching LLM-extracted metadata with runassessor data.
Uses PMID as the matching key and confidence-scored conflict resolution.
"""

import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional


class IntegrationAgent:
    """
    Enriches extracted metadata with runassessor data using PMID matching.
    Resolves conflicts using confidence scoring with full provenance tracking.
    """
    
    def __init__(self, runassessor_dir: str):
        self.runassessor_path = Path(runassessor_dir)
        self.pmid_index = self._build_pmid_index()
        self.pxd_index = self._build_pxd_index()
        
    def _build_pmid_index(self) -> dict[int, Path]:
        """Build PMID -> runassessor file mapping."""
        index = {}
        for json_file in self.runassessor_path.glob("*.json"):
            try:
                with open(json_file, 'r') as f:
                    data = json.load(f)
                # Extract pubmedID from pride_metadata.references
                references = data.get("pride_metadata", {}).get("references", [])
                for ref in references:
                    pmid = ref.get("pubmedID")
                    if pmid:
                        index[int(pmid)] = json_file
            except (json.JSONDecodeError, KeyError) as e:
                print(f"Warning: Could not parse {json_file}: {e}")
        print(f"Built PMID index with {len(index)} entries")
        return index
    
    def _build_pxd_index(self) -> dict[str, Path]:
        """Build PXD -> runassessor file mapping for new aggregated format."""
        index = {}
        # Match new format: PXD*_aggregated_results.json
        for json_file in self.runassessor_path.glob("PXD*_aggregated_results.json"):
            # Extract PXD ID from filename
            pxd_match = re.search(r'(PXD\d+)', json_file.name)
            if pxd_match:
                pxd_id = pxd_match.group(1)
                index[pxd_id] = json_file
        print(f"Built PXD index with {len(index)} entries")
        return index
    
    def load_by_pmid(self, pmid: int) -> Optional[dict]:
        """Load runassessor data by PMID."""
        file_path = self.pmid_index.get(pmid)
        if not file_path:
            return None
        with open(file_path, 'r') as f:
            return json.load(f)
    
    def load_by_pxd(self, pxd_id: str) -> Optional[dict]:
        """Load runassessor data by PXD ID (new aggregated format)."""
        file_path = self.pxd_index.get(pxd_id)
        if not file_path:
            return None
        with open(file_path, 'r') as f:
            return json.load(f)
    
    def _normalize_cv_item(self, item: dict) -> dict:
        """
        Normalize both old and new CvParam formats to a standard structure.
        
        Handles:
        - New format: {"@type": "CvParam", "cvLabel": "NEWT", "accession": "9606", "name": "Homo sapiens"}
        - Old format: {"name": "Homo sapiens", "accession": "9606"}
        
        Returns:
            Standardized dict with 'value', 'accession', 'score' keys
        """
        if not item:
            return None
        return {
            "value": item.get("name"),
            "accession": item.get("accession"),
            "cv_label": item.get("cvLabel"),
            "score": 1.0
        }
    
    def _get_top_organism(self, data: dict) -> Optional[dict]:
        """Extract highest-scored organism from organism_identification."""
        org_results = data.get("organism_identification", {}).get("results", [])
        top_org = None
        top_score = 0
        for result in org_results:
            for entry in result.get("data", []):
                score = entry.get("score", 0)
                if score > top_score:
                    top_score = score
                    top_org = {
                        "value": entry.get("taxon_name"),
                        "score": score,
                        "taxon_id": entry.get("taxon_id")
                    }
        return top_org
    
    def _get_instruments(self, data: dict) -> list[dict]:
        """Extract instrument info from pride_metadata."""
        instruments = data.get("pride_metadata", {}).get("instruments", [])
        return [self._normalize_cv_item(inst) for inst in instruments if inst]
    
    def _get_organisms(self, data: dict) -> list[dict]:
        """Extract organism info from pride_metadata."""
        organisms = data.get("pride_metadata", {}).get("organisms", [])
        return [self._normalize_cv_item(org) for org in organisms if org]
    
    def _get_ptms(self, data: dict) -> list[str]:
        """Extract PTM annotations."""
        ptms = data.get("pride_metadata", {}).get("identifiedPTMStrings", [])
        return [ptm.get("name") for ptm in ptms if ptm.get("name")]
    
    def _get_ptms_with_accessions(self, data: dict) -> list[dict]:
        """Extract PTMs with accessions."""
        ptms = data.get("pride_metadata", {}).get("identifiedPTMStrings", [])
        return [self._normalize_cv_item(ptm) for ptm in ptms if ptm.get("name")]
    
    def _get_tissues(self, data: dict) -> list[dict]:
        """Extract tissue/organism part from pride_metadata."""
        parts = data.get("pride_metadata", {}).get("organismParts", [])
        return [self._normalize_cv_item(part) for part in parts if part.get("name")]
    
    def _get_diseases(self, data: dict) -> list[dict]:
        """Extract disease annotations from pride_metadata."""
        diseases = data.get("pride_metadata", {}).get("diseases", [])
        return [self._normalize_cv_item(d) for d in diseases if d.get("name")]
    
    def _get_fragmentation(self, data: dict) -> dict:
        """Extract fragmentation method from spectra stats."""
        files_data = data.get("runAssessor", {}).get("files", {})
        for file_path, file_data in files_data.items():
            stats = file_data.get("spectra_stats", {})
            frag_tag = stats.get("fragmentation_tag")
            if frag_tag:
                return {
                    "value": frag_tag,
                    "score": 1.0
                }
        return None
    
    def _get_quantification(self, data: dict) -> list[dict]:
        """Extract quantification methods from pride_metadata."""
        methods = data.get("pride_metadata", {}).get("quantificationMethods", [])
        return [self._normalize_cv_item(m) for m in methods if m.get("name")]
    
    def _get_experiment_types(self, data: dict) -> list[str]:
        """Extract experiment types."""
        types = data.get("pride_metadata", {}).get("experimentTypes", [])
        return [t.get("name") for t in types if t.get("name")]
    
    def _get_keywords(self, data: dict) -> list[str]:
        """Extract keywords."""
        return data.get("pride_metadata", {}).get("keywords", [])
    
    def _get_spectra_stats(self, data: dict) -> dict:
        """Extract aggregated spectra statistics."""
        files_data = data.get("runAssessor", {}).get("files", {})
        # Aggregate from first file as representative
        for file_path, file_data in files_data.items():
            stats = file_data.get("spectra_stats", {})
            return {
                "acquisition_type": stats.get("acquisition_type"),
                "fragmentation_tag": stats.get("fragmentation_tag"),
                "n_ms2_spectra": stats.get("n_ms2_spectra"),
                "n_spectra": stats.get("n_spectra")
            }
        return {}
    
    def resolve_field(self, field_name: str, llm_value: dict, ra_value: dict) -> dict:
        """
        Resolve conflict between LLM and runassessor values.
        Returns confidence-scored merge with full provenance tracking.
        """
        # Normalize LLM value (may be [value, evidence] list format)
        if isinstance(llm_value, list) and len(llm_value) >= 2:
            llm_value = {"value": llm_value[0], "evidence": llm_value[1]}
        elif isinstance(llm_value, list) and len(llm_value) == 1:
            llm_value = {"value": llm_value[0], "evidence": ""}
        elif not isinstance(llm_value, dict):
            llm_value = {"value": str(llm_value) if llm_value else None, "evidence": ""}
        
        # Get values for comparison
        llm_val = llm_value.get("value") if llm_value else None
        ra_val = ra_value.get("value") if ra_value else None
        
        # Handle "unknown" as null
        if llm_val == "unknown":
            llm_val = None
        
        # Determine agreement status
        if llm_val and ra_val:
            # Both have values - check if they agree
            llm_normalized = str(llm_val).lower().strip()
            ra_normalized = str(ra_val).lower().strip()
            
            # Check exact match, substring match, or fuzzy match
            if llm_normalized == ra_normalized:
                status = "AGREE"
            elif llm_normalized in ra_normalized or ra_normalized in llm_normalized:
                status = "AGREE"
            elif self._fuzzy_match(llm_val, ra_val) >= 0.7:
                status = "AGREE"  # Fuzzy match (handles abbreviations)
            else:
                status = "DISAGREE"
        elif llm_val and not ra_val:
            status = "LLM_ONLY"
        elif ra_val and not llm_val:
            status = "RUNASSESSOR_ONLY"
        else:
            status = "UNKNOWN"
        
        # Default: prefer runassessor for structured data (higher confidence)
        ra_score = ra_value.get("score", 1.0) if ra_value else 0
        llm_score = 0.5  # Default LLM confidence
        
        # PRIORITIZE RUNASSESSOR: If RA value exists, use it regardless of score
        if ra_val:
            resolved = ra_val
            confidence = ra_score
        elif llm_val:
            resolved = llm_val
            confidence = llm_score
        else:
            resolved = None
            confidence = 0
            
        return {
            "resolved": resolved,
            "confidence": confidence,
            "status": status,
            "sources": {
                "runassessor": {
                    "value": ra_val,
                    "accession": ra_value.get("accession") if ra_value else None,
                    "taxon_id": ra_value.get("taxon_id") if ra_value else None,
                    "score": ra_score if ra_value else None
                } if ra_value else None,
                "llm": {
                    "value": llm_value.get("value") if llm_value else None,
                    "evidence": llm_value.get("evidence") if llm_value else None
                } if llm_value else None
            }
        }
    
    def _fuzzy_match(self, s1: str, s2: str) -> float:
        """
        Fuzzy string similarity for abbreviation matching.
        E.g., 'P. falciparum' matches 'Plasmodium falciparum'.
        
        Returns:
            Similarity ratio (0-1)
        """
        if not s1 or not s2:
            return 0.0
        
        if not isinstance(s1, str) or not isinstance(s2, str):
            return 0.0
        
        s1_lower = str(s1).lower().strip()
        s2_lower = str(s2).lower().strip()
        
        # Exact match
        if s1_lower == s2_lower:
            return 1.0
        
        # Check for abbreviation pattern: "X. name" vs "Xfullname name"
        abbrev_score = self._check_abbreviation(s1_lower, s2_lower)
        if abbrev_score > 0.8:
            return abbrev_score
        
        # Standard fuzzy match
        return SequenceMatcher(None, s1_lower, s2_lower).ratio()
    
    def _check_abbreviation(self, short: str, long: str) -> float:
        """
        Check if short is an abbreviation of long.
        E.g., 'p. falciparum' matches 'plasmodium falciparum'
        """
        # Pattern: "X. rest" where X is first letter
        abbrev_pattern = re.match(r'^([a-z])\. (.+)$', short)
        if abbrev_pattern:
            first_letter = abbrev_pattern.group(1)
            rest = abbrev_pattern.group(2)
            
            # Check if long starts with that letter and contains rest
            parts = long.split()
            if parts and parts[0].startswith(first_letter):
                long_rest = ' '.join(parts[1:])
                if rest == long_rest or SequenceMatcher(None, rest, long_rest).ratio() > 0.9:
                    return 0.95
        
        # Also check reverse
        abbrev_pattern = re.match(r'^([a-z])\. (.+)$', long)
        if abbrev_pattern:
            first_letter = abbrev_pattern.group(1)
            rest = abbrev_pattern.group(2)
            
            parts = short.split()
            if parts and parts[0].startswith(first_letter):
                short_rest = ' '.join(parts[1:])
                if rest == short_rest or SequenceMatcher(None, rest, short_rest).ratio() > 0.9:
                    return 0.95
        
        return 0.0
    
    # Agent-Specific Field Lists
    BIOLOGICAL_FIELDS = [
        'species', 'organism', 'tissue', 'organ', 'cell_type', 'cell_line', 
        'disease', 'disease_state', 'age', 'BMI', 'sex', 'strain', 'sample_source'
    ]
    
    TECHNICAL_FIELDS = [
        'instrument', 'detector', 'source', 'analyzer', 'chromatography', 
        'column', 'injection_volume', 'flow_rate', 'gradient', 'solvent_A', 
        'solvent_B', 'MS1_range', 'MS2_range', 'fragmentation', 
        'precursor_selection', 'resolution', 'software', 'database', 
        'processing_parameters', 'ptm', 'modification'
    ]
    
    EXPERIMENTAL_FIELDS = [
        'experiment_type', 'experimental_design', 'control_group', 
        'treatment_group', 'replicates', 'time_points', 
        'quantification_method', 'statistical_test', 'software_used'
    ]
    
    # Combined for fallback
    ALL_FIELDS = BIOLOGICAL_FIELDS + TECHNICAL_FIELDS + EXPERIMENTAL_FIELDS

    def enrich(self, identifier: int | str, extracted: dict, agent_type: str = 'all') -> dict:
        """
        Enrich extracted metadata with runassessor data.
        Returns standardized schema filtered by agent_type.
        
        Args:
            identifier: PubMed ID (int) or PXD ID (str like 'PXD001856')
            extracted: Metadata dict
            agent_type: 'BiologicalAgent', 'TechnicalAgent', 'ExperimentalDesignAgent', or 'all'
        """
        ra_data = None
        
        # Try loading by PXD first (new format), then by PMID (old format)
        if isinstance(identifier, str) and identifier.upper().startswith('PXD'):
            ra_data = self.load_by_pxd(identifier.upper())
            if not ra_data:
                print(f"No runassessor data found for PXD {identifier}")
        else:
            # Treat as PMID
            pmid = int(identifier) if isinstance(identifier, str) else identifier
            ra_data = self.load_by_pmid(pmid)
            if not ra_data:
                print(f"No runassessor data found for PMID {pmid}")
        
        if not ra_data:
            ra_data = {} 
        
        enriched = {}
        
        # Determine target fields based on agent type
        if 'Biological' in agent_type:
            target_fields = self.BIOLOGICAL_FIELDS
        elif 'Technical' in agent_type:
            target_fields = self.TECHNICAL_FIELDS
        elif 'Experimental' in agent_type:
            target_fields = self.EXPERIMENTAL_FIELDS
        else:
            target_fields = self.ALL_FIELDS
            
        # Field mapping to RunAssessor getters
        ra_map = {
            'species': self._get_organisms,
            'organism': self._get_organisms,
            'tissue': self._get_tissues,
            'organ': self._get_tissues,
            'disease': self._get_diseases,
            'disease_state': self._get_diseases,
            'instrument': self._get_instruments,
            'fragmentation': self._get_fragmentation,
            'experiment_type': self._get_experiment_types,
            'experimental_design': self._get_experiment_types,
            'ptm': self._get_ptms_with_accessions,
            'modification': self._get_ptms_with_accessions,
            'quantification_method': self._get_quantification,
        }

        # Iterate ONLY over target fields for this agent
        for field in target_fields:
            # 1. Get LLM Value
            llm_value = extracted.get(field)
            
            # 2. Get RunAssessor Value
            ra_value = None
            if ra_data:
                getter = ra_map.get(field)
                if getter:
                    raw_ra = getter(ra_data)
                    if isinstance(raw_ra, list) and raw_ra:
                        val = raw_ra[0]
                        if isinstance(val, dict):
                            ra_value = val
                        else:
                            ra_value = {"value": val, "score": 1.0}
                    elif isinstance(raw_ra, dict) and raw_ra:
                        ra_value = raw_ra

            # 3. Special Handling Cases
            if field in ['species', 'organism'] and ra_data:
                top_organism = self._get_top_organism(ra_data)
                if top_organism:
                    ra_value = top_organism
            if field == 'instrument' and ra_value:
                ra_value['score'] = 1.0

            # 4. Resolve and Standardize
            enriched[field] = self.resolve_field(field, llm_value, ra_value)

        # Preserve unrelated fields (internal metadata)
        for k, v in extracted.items():
            if k.startswith('_'):
                enriched[k] = v
        
        # Enrich with additional metadata (from runassessor only - additive)
        if ra_data:
            enriched["_runassessor_data"] = {
                "ptms": self._get_ptms(ra_data),
                "experiment_types": self._get_experiment_types(ra_data),
                "keywords": self._get_keywords(ra_data),
                "spectra_stats": self._get_spectra_stats(ra_data),
                "quantification_methods": [m.get("value") for m in self._get_quantification(ra_data)]
            }
            
            # Add provenance
            # Get PMID from references if available
            pmid_value = None
            if isinstance(identifier, str) and identifier.upper().startswith('PXD'):
                refs = ra_data.get("pride_metadata", {}).get("references", [])
                if refs:
                    pmid_value = refs[0].get("pubmedID")
            else:
                pmid_value = identifier
            
            enriched["_enrichment"] = {
                "identifier": str(identifier),
                "pmid": pmid_value,
                "pxd_id": ra_data.get("pxd_id"),
                "runassessor_version": ra_data.get("pipeline_version")
            }
        
        return enriched
    
    def enrich_batch(self, results: dict[str, dict], agent_name: str = 'all') -> dict[str, dict]:
        """
        Enrich a batch of extracted results.
        
        Args:
            results: Dict of {filename: extracted_metadata}
            agent_name: Name of the agent (e.g., 'BiologicalAgent') to determine schema.
            
        Returns:
            Dict of {filename: enriched_metadata}
        """
        enriched_results = {}
        for filename, extracted in results.items():
            # Try to get PMID from filename (e.g., '/path/to/24657495.txt' -> 24657495)
            from pathlib import Path
            file_stem = Path(filename).stem
            identifier = None
            
            # 1. Check if filename is a valid PMID (numeric)
            if file_stem.isdigit():
                identifier = int(file_stem)
            
            # 2. Check for PXD ID (e.g., PXD012345)
            elif 'PXD' in file_stem:
                import re
                pxd_match = re.search(r'(PXD\d+)', file_stem)
                if pxd_match:
                    identifier = pxd_match.group(1)
            
            # 3. Check for PMID in filename (e.g., PMC123_12345678.txt)
            if not identifier:
                 import re
                 # Look for 8 digit number that might be PMID
                 pmid_match = re.search(r'(\d{8})', file_stem)
                 if pmid_match:
                     identifier = int(pmid_match.group(1))

            if identifier:
                enriched_results[filename] = self.enrich(identifier, extracted, agent_type=agent_name)
            else:
                print(f"Could not extract Identifier from filename {filename}, skipping enrichment")
                enriched_results[filename] = extracted
        return enriched_results
