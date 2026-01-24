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
    
    def load_by_pmid(self, pmid: int) -> Optional[dict]:
        """Load runassessor data by PMID."""
        file_path = self.pmid_index.get(pmid)
        if not file_path:
            return None
        with open(file_path, 'r') as f:
            return json.load(f)
    
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
        return [
            {
                "value": inst.get("name"),
                "accession": inst.get("accession")
            }
            for inst in instruments
        ]
    
    def _get_organisms(self, data: dict) -> list[dict]:
        """Extract organism info from pride_metadata."""
        organisms = data.get("pride_metadata", {}).get("organisms", [])
        return [
            {
                "value": org.get("name"),
                "accession": org.get("accession")
            }
            for org in organisms
        ]
    
    def _get_ptms(self, data: dict) -> list[str]:
        """Extract PTM annotations."""
        ptms = data.get("pride_metadata", {}).get("identifiedPTMStrings", [])
        return [ptm.get("name") for ptm in ptms if ptm.get("name")]
    
    def _get_ptms_with_accessions(self, data: dict) -> list[dict]:
        """Extract PTMs with accessions."""
        ptms = data.get("pride_metadata", {}).get("identifiedPTMStrings", [])
        return [
            {
                "value": ptm.get("name"),
                "accession": ptm.get("accession"),
                "score": 1.0
            }
            for ptm in ptms if ptm.get("name")
        ]
    
    def _get_tissues(self, data: dict) -> list[dict]:
        """Extract tissue/organism part from pride_metadata."""
        parts = data.get("pride_metadata", {}).get("organismParts", [])
        return [
            {
                "value": part.get("name"),
                "accession": part.get("accession"),
                "score": 1.0
            }
            for part in parts if part.get("name")
        ]
    
    def _get_diseases(self, data: dict) -> list[dict]:
        """Extract disease annotations from pride_metadata."""
        diseases = data.get("pride_metadata", {}).get("diseases", [])
        return [
            {
                "value": d.get("name"),
                "accession": d.get("accession"),
                "score": 1.0
            }
            for d in diseases if d.get("name")
        ]
    
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
        return [
            {
                "value": m.get("name"),
                "accession": m.get("accession"),
                "score": 1.0
            }
            for m in methods if m.get("name")
        ]
    
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
        
        if ra_val and ra_score >= llm_score:
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
    
    def enrich(self, pmid: int, extracted: dict) -> dict:
        """
        Enrich extracted metadata with runassessor data.
        
        Args:
            pmid: PubMed ID to match
            extracted: LLM-extracted metadata dict
            
        Returns:
            Enriched dict with confidence-scored fields
        """
        ra_data = self.load_by_pmid(pmid)
        
        if not ra_data:
            print(f"No runassessor data found for PMID {pmid}")
            return extracted
        
        enriched = extracted.copy()
        
        # ================================================================
        # Resolve species/organism
        # ================================================================
        llm_species = extracted.get("species") or extracted.get("organism")
        ra_organisms = self._get_organisms(ra_data)
        top_organism = self._get_top_organism(ra_data)
        ra_organism = top_organism if top_organism else (ra_organisms[0] if ra_organisms else None)
        if ra_organism:
            ra_organism["score"] = ra_organism.get("score", 1.0)
        enriched["species"] = self.resolve_field("species", llm_species, ra_organism)
        
        # ================================================================
        # Resolve tissue
        # ================================================================
        llm_tissue = extracted.get("tissue")
        ra_tissues = self._get_tissues(ra_data)
        ra_tissue = ra_tissues[0] if ra_tissues else None
        if llm_tissue or ra_tissue:
            enriched["tissue"] = self.resolve_field("tissue", llm_tissue, ra_tissue)
        
        # ================================================================
        # Resolve disease
        # ================================================================
        llm_disease = extracted.get("disease") or extracted.get("disease_state")
        ra_diseases = self._get_diseases(ra_data)
        ra_disease = ra_diseases[0] if ra_diseases else None
        if llm_disease or ra_disease:
            enriched["disease"] = self.resolve_field("disease", llm_disease, ra_disease)
        
        # ================================================================
        # Resolve instrument
        # ================================================================
        llm_instrument = extracted.get("instrument")
        ra_instruments = self._get_instruments(ra_data)
        ra_instrument = ra_instruments[0] if ra_instruments else None
        if ra_instrument:
            ra_instrument["score"] = 1.0
        enriched["instrument"] = self.resolve_field("instrument", llm_instrument, ra_instrument)
        
        # ================================================================
        # Resolve fragmentation method
        # ================================================================
        llm_frag = extracted.get("fragmentation method") or extracted.get("fragmentation")
        ra_frag = self._get_fragmentation(ra_data)
        if llm_frag or ra_frag:
            enriched["fragmentation"] = self.resolve_field("fragmentation", llm_frag, ra_frag)
        
        # ================================================================
        # Resolve experiment type
        # ================================================================
        llm_exp_type = extracted.get("experiment_type") or extracted.get("experimental_design")
        ra_exp_types = self._get_experiment_types(ra_data)
        ra_exp_type = {"value": ra_exp_types[0], "score": 1.0} if ra_exp_types else None
        if llm_exp_type or ra_exp_type:
            enriched["experiment_type"] = self.resolve_field("experiment_type", llm_exp_type, ra_exp_type)
        
        # ================================================================
        # Resolve or merge PTMs (multiple values)
        # ================================================================
        llm_ptm = extracted.get("ptm") or extracted.get("modification")
        ra_ptms = self._get_ptms_with_accessions(ra_data)
        ra_ptm = ra_ptms[0] if ra_ptms else None
        if llm_ptm or ra_ptm:
            enriched["ptm"] = self.resolve_field("ptm", llm_ptm, ra_ptm)
        
        # Enrich with additional metadata (from runassessor only - additive)
        enriched["_runassessor_data"] = {
            "ptms": self._get_ptms(ra_data),
            "experiment_types": self._get_experiment_types(ra_data),
            "keywords": self._get_keywords(ra_data),
            "spectra_stats": self._get_spectra_stats(ra_data),
            "quantification_methods": [m.get("value") for m in self._get_quantification(ra_data)]
        }
        
        # Add provenance
        enriched["_enrichment"] = {
            "pmid": pmid,
            "pxd_id": ra_data.get("pxd_id"),
            "runassessor_version": ra_data.get("pipeline_version")
        }
        
        return enriched
    
    def enrich_batch(self, results: dict[str, dict]) -> dict[str, dict]:
        """
        Enrich a batch of extracted results.
        
        Args:
            results: Dict of {filename: extracted_metadata}
            
        Returns:
            Dict of {filename: enriched_metadata}
        """
        enriched_results = {}
        for filename, extracted in results.items():
            # Try to get PMID from filename (e.g., '/path/to/24657495.txt' -> 24657495)
            from pathlib import Path
            file_stem = Path(filename).stem
            pmid = None
            
            # Check if filename is a valid PMID (numeric)
            if file_stem.isdigit():
                pmid = int(file_stem)
            
            if pmid:
                enriched_results[filename] = self.enrich(pmid, extracted)
            else:
                print(f"Could not extract PMID from filename {filename}, skipping enrichment")
                enriched_results[filename] = extracted
        return enriched_results
