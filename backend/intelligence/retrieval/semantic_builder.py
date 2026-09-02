"""
Build semantic (Chroma) embeddings for repository analysis.

Creates dense vector embeddings for code entities and stores them
in a Chroma persistent index.

This is run during analysis completion, not at retrieval time,
to ensure embeddings are fresh and available for RIM queries.
"""

import logging
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class SemanticIndexBuilder:
    """Builds Chroma embeddings for a repository analysis."""

    def __init__(self):
        self.embeddings_model = None

    def build_index(self, model_entities: Dict[str, Any]) -> Optional[bytes]:
        """
        Build Chroma index from repository model entities.

        Args:
            model_entities: Dict of entity_id -> Entity from RepositoryModel

        Returns:
            bytes: Compressed Chroma database ready for storage, or None if building fails
        """
        try:
            import chromadb
        except ImportError:
            logger.warning("chromadb not available - semantic indexing skipped")
            return None

        if not model_entities:
            logger.info("No entities to index for semantic search")
            return None

        try:
            # Create temporary directory for Chroma
            temp_dir = tempfile.mkdtemp(prefix="chroma_build_")
            try:
                # Initialize Chroma client
                client = chromadb.PersistentClient(path=temp_dir)

                # Delete existing collection if present
                try:
                    client.delete_collection(name="semantic_index")
                except Exception:
                    pass  # Collection doesn't exist yet

                # Create new collection
                collection = client.create_collection(
                    name="semantic_index",
                    metadata={"hnsw:space": "cosine"}
                )

                # Prepare documents for embedding
                documents = []
                ids = []
                metadatas = []

                for entity_id, entity in model_entities.items():
                    try:
                        # Extract text for embedding
                        doc_text = self._entity_to_text(entity)
                        if not doc_text:
                            continue

                        # Extract metadata
                        metadata = self._entity_to_metadata(entity)

                        documents.append(doc_text)
                        ids.append(entity_id)
                        metadatas.append(metadata)

                    except Exception as e:
                        logger.debug(f"Failed to index entity {entity_id}: {e}")
                        continue

                if not documents:
                    logger.info("No documents to embed for semantic index")
                    return None

                # Add documents to collection (Chroma handles embedding)
                logger.info(f"Embedding {len(documents)} entities for semantic search...")
                collection.add(
                    ids=ids,
                    documents=documents,
                    metadatas=metadatas
                )

                # Serialize Chroma database to bytes
                logger.info(f"Serializing Chroma index ({len(documents)} entities)...")
                import zipfile
                import io

                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                    for file_path in Path(temp_dir).rglob('*'):
                        if file_path.is_file():
                            arcname = file_path.relative_to(temp_dir)
                            zf.write(file_path, arcname=arcname)

                result = zip_buffer.getvalue()
                logger.info(f"Semantic index built: {len(result)} bytes compressed")
                return result

            finally:
                # Cleanup temp directory
                shutil.rmtree(temp_dir, ignore_errors=True)

        except Exception as e:
            logger.error(f"Failed to build semantic index: {e}", exc_info=True)
            return None

    def _entity_to_text(self, entity: Any) -> str:
        """Convert entity to searchable text."""
        parts = []

        # Add entity type and name
        if hasattr(entity, 'type') and hasattr(entity, 'name'):
            parts.append(f"{entity.type.value} {entity.name}")

        # Add qualified name if available
        if hasattr(entity, 'qualified_name'):
            parts.append(entity.qualified_name)

        # Add file path if available
        if hasattr(entity, 'location') and entity.location:
            if hasattr(entity.location, 'repository_path'):
                parts.append(entity.location.repository_path)

        # Add metadata docstring/signature if available
        if hasattr(entity, 'metadata') and entity.metadata:
            if 'docstring' in entity.metadata:
                parts.append(entity.metadata['docstring'])
            if 'signature' in entity.metadata:
                parts.append(entity.metadata['signature'])

        return " ".join(filter(None, parts))

    def _entity_to_metadata(self, entity: Any) -> Dict[str, str]:
        """Extract metadata for entity. All values must be strings for Chroma."""
        metadata = {}

        if hasattr(entity, 'type'):
            metadata['type'] = str(entity.type.value) if hasattr(entity.type, 'value') else str(entity.type)
        if hasattr(entity, 'name'):
            metadata['name'] = str(entity.name)
        if hasattr(entity, 'qualified_name'):
            metadata['qualified_name'] = str(entity.qualified_name)
        if hasattr(entity, 'location') and entity.location:
            if hasattr(entity.location, 'repository_path'):
                metadata['file_path'] = str(entity.location.repository_path)

        # Ensure all values are strings (Chroma requirement)
        return {k: str(v) if v is not None else "" for k, v in metadata.items()}
