from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON, Boolean
from sqlalchemy.orm import relationship, backref
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime, timezone
from backend.database import Base

JSONType = JSON().with_variant(JSONB, "postgresql")

class FactFile(Base):
    __tablename__ = "files"

    id = Column(String, primary_key=True, index=True)
    analysis_id = Column(Integer, ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False, index=True)
    path = Column(String, nullable=False, index=True)
    language = Column(String, nullable=True)
    size = Column(Integer, nullable=True, default=0)
    content_hash = Column(String, nullable=True)
    is_binary = Column(Boolean, nullable=False, default=False)
    is_generated = Column(Boolean, nullable=False, default=False)
    is_test = Column(Boolean, nullable=False, default=False)
    is_documentation = Column(Boolean, nullable=False, default=False)
    is_agent_instruction = Column(Boolean, nullable=False, default=False)
    last_modified = Column(DateTime(timezone=True), nullable=True)
    blob_name = Column(String, nullable=True, index=True)
    snapshot_id = Column(String, nullable=True, index=True)
    content_type = Column(String, nullable=True)

    analysis = relationship("Analysis", backref=backref("files", cascade="all, delete-orphan", passive_deletes=True))
    symbols = relationship("FactSymbol", back_populates="file", cascade="all, delete-orphan")

class FactSymbol(Base):
    __tablename__ = "symbols"

    id = Column(String, primary_key=True, index=True)
    analysis_id = Column(Integer, ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False, index=True)
    file_id = Column(String, ForeignKey("files.id", ondelete="CASCADE"), nullable=True, index=True)
    name = Column(String, nullable=False, index=True)
    qualified_name = Column(String, nullable=True, index=True)
    symbol_type = Column(String, nullable=False, index=True)  # function, class, method, variable, route, table, etc.
    line_start = Column(Integer, nullable=True)
    line_end = Column(Integer, nullable=True)
    signature_hash = Column(String, nullable=True)
    metadata_json = Column("metadata", JSONType, nullable=True)

    analysis = relationship("Analysis", backref=backref("symbols", cascade="all, delete-orphan", passive_deletes=True))
    file = relationship("FactFile", back_populates="symbols")

class FactRelationship(Base):
    __tablename__ = "relationships"

    id = Column(String, primary_key=True, index=True)
    analysis_id = Column(Integer, ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False, index=True)
    from_symbol_id = Column(String, nullable=False, index=True)
    to_symbol_id = Column(String, nullable=False, index=True)
    rel_type = Column(String, nullable=False, index=True)  # CONTAINS, CALLS, IMPORTS, INHERITS, READS, WRITES, USES, EXPOSES, DECLARES, HANDLED_BY, QUERIES, DEPENDS_ON, etc.
    evidence_line = Column(Integer, nullable=True)
    evidence_snippet = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="CONFIRMED")  # CONFIRMED, INFERRED, UNRESOLVED
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    analysis = relationship("Analysis", backref=backref("relationships", cascade="all, delete-orphan", passive_deletes=True))

class FactRoute(Base):
    __tablename__ = "routes"

    id = Column(String, primary_key=True, index=True)
    analysis_id = Column(Integer, ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False, index=True)
    symbol_id = Column(String, nullable=True, index=True)
    method = Column(String, nullable=False)  # GET, POST, PUT, DELETE, etc.
    path = Column(String, nullable=False, index=True)
    handler_symbol_id = Column(String, nullable=True, index=True)

    analysis = relationship("Analysis", backref=backref("routes", cascade="all, delete-orphan", passive_deletes=True))

class FactDatabaseObject(Base):
    __tablename__ = "database_objects"

    id = Column(String, primary_key=True, index=True)
    analysis_id = Column(Integer, ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False, index=True)
    symbol_id = Column(String, nullable=True, index=True)
    object_type = Column(String, nullable=False, index=True)  # table, model, query, column
    name = Column(String, nullable=False, index=True)

    analysis = relationship("Analysis", backref=backref("database_objects", cascade="all, delete-orphan", passive_deletes=True))

class FactCapability(Base):
    __tablename__ = "capabilities"

    id = Column(String, primary_key=True, index=True)
    analysis_id = Column(Integer, ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False, index=True)  # Authentication, CRUD, Background Tasks, File Upload, etc.
    capability_type = Column(String, nullable=True)
    status = Column(String, nullable=False, default="CONFIRMED")  # CONFIRMED, INFERRED
    evidence_summary = Column(Text, nullable=True)

    analysis = relationship("Analysis", backref=backref("capabilities", cascade="all, delete-orphan", passive_deletes=True))
    members = relationship("FactCapabilityMember", back_populates="capability", cascade="all, delete-orphan")

class FactEvidence(Base):
    __tablename__ = "evidence"

    id = Column(String, primary_key=True, index=True)
    analysis_id = Column(Integer, ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False, index=True)
    fact_type = Column(String, nullable=False, index=True)
    symbol_id = Column(String, nullable=True, index=True)
    details = Column(JSONType, nullable=True)
    location = Column(String, nullable=True)

    analysis = relationship("Analysis", backref=backref("evidence", cascade="all, delete-orphan", passive_deletes=True))

class FactCapabilityMember(Base):
    __tablename__ = "capability_members"

    id = Column(String, primary_key=True, index=True)
    capability_id = Column(String, ForeignKey("capabilities.id", ondelete="CASCADE"), nullable=False, index=True)
    symbol_id = Column(String, nullable=False, index=True)
    role = Column(String, nullable=True)  # entry_point, service, repository, table, handler, etc.
    evidence_id = Column(String, ForeignKey("evidence.id", ondelete="SET NULL"), nullable=True, index=True)

    capability = relationship("FactCapability", back_populates="members")
    evidence = relationship("FactEvidence", foreign_keys=[evidence_id])
