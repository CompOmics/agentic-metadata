#!/usr/bin/env python3
"""
Pre-build ontology indices for faster normalization.

Loads ontologies and builds SapBERT embedding indices, caching them to disk.
Use --ontologies to build a subset; use --slim to strip raw embeddings from
the .pkl files (the .faiss binary is sufficient for search, saving ~50% space).

Usage:
    # Full set
    python -m normalization.build_index

    # Core Docker set (fast, GPU-accelerated)
    python -m normalization.build_index \\
        --ontologies species pride-cv psi-ms unimod doid cl uberon clo \\
        --slim --output-dir docker/prebuilt_indices
"""

import argparse
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

ALL_ONTOLOGIES = {
    'cl':                          'cl.obo',
    'uberon':                      'uberon.obo',
    'species':                     'species.obo',
    'doid':                        'doid.obo',
    'psi-ms':                      'psi-ms.obo',
    'unimod':                      'unimod.obo',
    'bto':                         'bto.obo',
    'clo':                         'clo.owl',
    'pride-cv':                    'pride-cv.obo',
    'mondo':                       'mondo.obo',
    'psimod':                      'psimod.obo',
    'experimentalfactor':          'experimentalfactor.obo',
    'drosophilaanatomy':           'drosophilaanatomy.obo',
    'plantontology':               'plantontology.obo',
    'zebrafishanatomydevelopment': 'zebrafishanatomydevelopment.obo',
    'flybase':                     'flybase.obo',
    'ratstrains':                  'ratstrains.obo',
    'chebi':                       'chebi.obo',
    'phenotypeandtrait':           'phenotypeandtrait.obo',
}


def build_indices(
    ontologies: list[str] | None = None,
    output_dir: str | None = None,
    slim: bool = False,
    use_gpu: bool = True,
) -> None:
    from .config import NormalizationConfig
    from .normalizer import TermNormalizer

    project_root = Path(__file__).parent.parent
    ontology_dir = project_root / "ontologies"
    cache_dir = Path(output_dir) if output_dir else project_root / "ontology_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Ontology directory : {ontology_dir}")
    logger.info(f"Cache directory    : {cache_dir}")

    selected = {k: v for k, v in ALL_ONTOLOGIES.items() if not ontologies or k in ontologies}
    if ontologies:
        missing = [o for o in ontologies if o not in ALL_ONTOLOGIES]
        if missing:
            logger.error(f"Unknown ontology IDs: {missing}")
            logger.error(f"Valid IDs: {sorted(ALL_ONTOLOGIES)}")
            sys.exit(1)
    logger.info(f"Building {len(selected)} ontologie(s): {', '.join(selected)}")

    config = NormalizationConfig(
        ontology_dir=str(ontology_dir),
        cache_dir=str(cache_dir),
        similarity_threshold=0.7,
        use_gpu=use_gpu,
    )
    config.ontology_files = selected

    normalizer = TermNormalizer(config)
    logger.info("Loading and indexing ontologies...")
    normalizer.load_all_ontologies()

    if slim:
        logger.info("Slimming indices: dropping raw embeddings from .pkl files...")
        for ont_id, index in normalizer.indices.items():
            cache_path = config.get_cache_path(ont_id)
            index.save(str(cache_path), slim=True)
            logger.info(f"  Slimmed: {ont_id}")

    logger.info("\n" + "=" * 60)
    logger.info("INDEXING COMPLETE")
    logger.info("=" * 60)
    for ont_id, index in normalizer.indices.items():
        n = len(index.term_ids) if hasattr(index, 'term_ids') else '?'
        logger.info(f"  {ont_id}: {n} terms")
    logger.info(f"\nCache saved to: {cache_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pre-build SapBERT ontology indices",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        '--ontologies', nargs='+', metavar='ID',
        help='Ontology IDs to build (default: all). '
             f'Valid: {", ".join(sorted(ALL_ONTOLOGIES))}',
    )
    parser.add_argument(
        '--output-dir', metavar='DIR',
        help='Where to write index files (default: ontology_cache/)',
    )
    parser.add_argument(
        '--slim', action='store_true',
        help='Strip raw embeddings from .pkl — saves ~50%% disk; '
             'FAISS binary is sufficient for search',
    )
    parser.add_argument(
        '--no-gpu', action='store_true',
        help='Force CPU even if a GPU is available',
    )
    args = parser.parse_args()

    print("=" * 60)
    print("ONTOLOGY INDEX BUILDER")
    print("=" * 60)

    build_indices(
        ontologies=args.ontologies,
        output_dir=args.output_dir,
        slim=args.slim,
        use_gpu=not args.no_gpu,
    )


if __name__ == "__main__":
    main()
