"""
Target Entity Resolver: Resolves raw query strings to canonical Fact Store entities
(FactFile, FactSymbol, FactRoute, FactDatabaseObject) strictly scoped to an analysis_id.
"""
from __future__ import annotations

import logging
from typing import Optional, Any, Union
from sqlalchemy.orm import Session
from sqlalchemy import or_

from backend.models.fact_store import FactFile, FactSymbol, FactRoute, FactDatabaseObject

logger = logging.getLogger(__name__)


class TargetEntityResolver:
    """
    Resolves raw identifier strings or file paths to canonical database entities.
    """

    def __init__(self, db: Session, analysis_id: int):
        self.db = db
        self.analysis_id = analysis_id

    def resolve(
        self,
        raw_name: str,
        hint: Optional[str] = None
    ) -> Optional[Union[FactFile, FactSymbol, FactRoute, FactDatabaseObject]]:
        """
        Resolves raw target name to a canonical Fact Store record.
        """
        if not raw_name or not self.analysis_id:
            return None

        clean_name = raw_name.replace("\\", "/").strip("./ ")
        if not clean_name:
            return None

        # 1. If hint is route or name looks like an HTTP path starting with '/'
        if hint == "route" or clean_name.startswith("/"):
            route = self.db.query(FactRoute).filter(
                FactRoute.analysis_id == self.analysis_id,
                or_(
                    FactRoute.path == clean_name,
                    FactRoute.path.ilike(f"{clean_name}"),
                    FactRoute.path.ilike(f"%{clean_name}"),
                )
            ).first()
            if route:
                return route

        # 2. If hint is function, class, method, or symbol -> Prioritize FactSymbol
        if hint in ("function", "class", "method", "symbol"):
            sym_query = self.db.query(FactSymbol).filter(FactSymbol.analysis_id == self.analysis_id)
            if hint == "function":
                sym_query = sym_query.filter(FactSymbol.symbol_type.in_(["FUNCTION", "METHOD"]))
            elif hint == "class":
                sym_query = sym_query.filter(FactSymbol.symbol_type == "CLASS")
            elif hint == "method":
                sym_query = sym_query.filter(FactSymbol.symbol_type == "METHOD")

            # Check exact qualified name or exact name
            symbol = sym_query.filter(
                or_(
                    FactSymbol.qualified_name == clean_name,
                    FactSymbol.name == clean_name,
                    FactSymbol.qualified_name.ilike(f"%.{clean_name}"),
                    FactSymbol.name.ilike(clean_name),
                )
            ).first()
            if symbol:
                return symbol

        # 3. If hint is database table/model
        if hint == "database":
            db_obj = self.db.query(FactDatabaseObject).filter(
                FactDatabaseObject.analysis_id == self.analysis_id,
                or_(
                    FactDatabaseObject.name == clean_name,
                    FactDatabaseObject.name.ilike(clean_name),
                )
            ).first()
            if db_obj:
                return db_obj

            # Model Class fallback
            model_sym = self.db.query(FactSymbol).filter(
                FactSymbol.analysis_id == self.analysis_id,
                FactSymbol.symbol_type == "CLASS",
                or_(
                    FactSymbol.name == clean_name,
                    FactSymbol.qualified_name == clean_name,
                    FactSymbol.name.ilike(clean_name),
                )
            ).first()
            if model_sym:
                return model_sym

        # 4. If hint is file/module or name has explicit file extension
        has_file_ext = any(clean_name.endswith(ext) for ext in [".py", ".ts", ".js", ".jsx", ".tsx", ".html", ".css", ".json", ".yml", ".yaml", ".md"])
        if hint in ("file", "module") or has_file_ext:
            # Exact path match
            fact_file = self.db.query(FactFile).filter(
                FactFile.analysis_id == self.analysis_id,
                FactFile.path == clean_name
            ).first()
            if not fact_file:
                # Suffix match (e.g. "please.py" matches "pls_cli/please.py")
                fact_file = self.db.query(FactFile).filter(
                    FactFile.analysis_id == self.analysis_id,
                    or_(
                        FactFile.path.ilike(f"%/{clean_name}"),
                        FactFile.path.ilike(f"{clean_name}"),
                    )
                ).first()
            if fact_file:
                return fact_file

        # 5. General Fallback with strict exact-match precedence
        # 5a. FactSymbol
        symbol = self.db.query(FactSymbol).filter(
            FactSymbol.analysis_id == self.analysis_id,
            or_(
                FactSymbol.qualified_name == clean_name,
                FactSymbol.name == clean_name,
                FactSymbol.name.ilike(clean_name),
            )
        ).first()
        if symbol:
            return symbol

        # 5b. FactFile
        fact_file = self.db.query(FactFile).filter(
            FactFile.analysis_id == self.analysis_id,
            or_(
                FactFile.path == clean_name,
                FactFile.path.ilike(f"%/{clean_name}"),
            )
        ).first()
        if fact_file:
            return fact_file

        # 5c. FactDatabaseObject
        db_obj = self.db.query(FactDatabaseObject).filter(
            FactDatabaseObject.analysis_id == self.analysis_id,
            FactDatabaseObject.name.ilike(clean_name)
        ).first()
        if db_obj:
            return db_obj

        # 5d. FactRoute
        route = self.db.query(FactRoute).filter(
            FactRoute.analysis_id == self.analysis_id,
            FactRoute.path.ilike(f"%{clean_name}%")
        ).first()
        if route:
            return route

        return None
