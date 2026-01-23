"""
Integration Agent for enriching LLM-extracted metadata with runassessor data.
Uses PMID as the matching key and confidence-scored conflict resolution.
"""

import json
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
            if llm_normalized == ra_normalized or llm_normalized in ra_normalized or ra_normalized in llm_normalized:
                status = "AGREE"
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
        
        # Resolve species/organism (LLM uses "species", runassessor has "organisms")
        llm_species = extracted.get("species") or extracted.get("organism")
        ra_organisms = self._get_organisms(ra_data)
        top_organism = self._get_top_organism(ra_data)
        ra_organism = top_organism if top_organism else (ra_organisms[0] if ra_organisms else None)
        if ra_organism:
            ra_organism["score"] = ra_organism.get("score", 1.0)
        enriched["species"] = self.resolve_field("species", llm_species, ra_organism)
        
        # Resolve instrument
        llm_instrument = extracted.get("instrument")
        ra_instruments = self._get_instruments(ra_data)
        ra_instrument = ra_instruments[0] if ra_instruments else None
        if ra_instrument:
            ra_instrument["score"] = 1.0  # Validated accession = high confidence
        enriched["instrument"] = self.resolve_field("instrument", llm_instrument, ra_instrument)
        
        # Enrich with additional metadata (from runassessor only - additive)
        enriched["_runassessor_data"] = {
            "ptms": self._get_ptms(ra_data),
            "experiment_types": self._get_experiment_types(ra_data),
            "keywords": self._get_keywords(ra_data),
            "spectra_stats": self._get_spectra_stats(ra_data)
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
