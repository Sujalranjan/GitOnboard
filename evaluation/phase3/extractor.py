from typing import List, Dict, Any

from .schemas import AtomicClaim, ClaimType, SupportStatus


class AtomicClaimExtractor:
    @staticmethod
    def extract_claims(raw_writer_output: Dict[str, Any], repository: str) -> List[AtomicClaim]:
        """Extract a flat list of :class:`AtomicClaim` from the writer output.

        The implementation covers the structures exercised by the current test suite:
        * ``technologies`` – each entry yields a ``TECHNOLOGY`` claim.
        * ``deployable_units`` – each entry yields a ``PATH`` claim.
        """
        claims: List[AtomicClaim] = []
        # Technology claims
        for tech in raw_writer_output.get("technologies", []):
            name = tech.get("name", "")
            category = tech.get("category", "technology").lower()
            claim_type = ClaimType.TECHNOLOGY if category == "technology" else ClaimType[category.upper()]
            claim = AtomicClaim(
                claim_id=f"tech_{name}",
                repository=repository,
                text=f"The project uses {name} ({category.capitalize()}).",
                claim_type=claim_type,
                citations=tech.get("evidence_ids", []),
                support_status=SupportStatus.UNRESOLVED,
            )
            claims.append(claim)
        # Deployable unit (path) claims
        for du in raw_writer_output.get("deployable_units", []):
            name = du.get("name", "")
            root_path = du.get("root_path", "")
            claim = AtomicClaim(
                claim_id=f"unit_{name}",
                repository=repository,
                text=f"Deployable unit '{name}' exists at root path '{root_path}'.",
                claim_type=ClaimType.PATH,
                citations=du.get("evidence_ids", []),
                support_status=SupportStatus.UNRESOLVED,
            )
            claims.append(claim)
        return claims

# Compatibility function expected by tests
def extract_claims(raw_writer_output, repository):
    """Alias to the static method for backward compatibility."""
    return AtomicClaimExtractor.extract_claims(raw_writer_output, repository)
