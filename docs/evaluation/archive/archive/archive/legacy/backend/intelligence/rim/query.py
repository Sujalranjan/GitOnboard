from typing import Protocol, List, Optional
from .entity import Entity
from .enums import EntityType
from .relationship import Relationship
from .repository import RepositoryModel

class RepositoryQueryService(Protocol):
    def get_entity(self, id: str) -> Optional[Entity]: ...
    def get_relationships(self, id: str) -> List[Relationship]: ...
    def get_incoming(self, id: str) -> List[Relationship]: ...
    def get_outgoing(self, id: str) -> List[Relationship]: ...
    def find_by_type(self, type_: EntityType) -> List[Entity]: ...
    def find_by_name(self, name: str) -> List[Entity]: ...
    def neighbors(self, id: str) -> List[Entity]: ...

class GraphQueryService:
    def __init__(self, model: RepositoryModel):
        self.model = model
        
        # Pre-compute indexes for fast lookup
        self._incoming = {}
        self._outgoing = {}
        self._by_type = {}
        self._by_name = {}
        
        for e in self.model.entities.values():
            self._by_type.setdefault(e.type, []).append(e)
            self._by_name.setdefault(e.name, []).append(e)
            self._incoming[e.id] = []
            self._outgoing[e.id] = []
            
        for r in self.model.relationships.values():
            if r.source_id in self._outgoing:
                self._outgoing[r.source_id].append(r)
            if r.target_id in self._incoming:
                self._incoming[r.target_id].append(r)

    def get_entity(self, id: str) -> Optional[Entity]:
        return self.model.entities.get(id)

    def get_relationships(self, id: str) -> List[Relationship]:
        return self.get_incoming(id) + self.get_outgoing(id)

    def get_incoming(self, id: str) -> List[Relationship]:
        return self._incoming.get(id, [])

    def get_outgoing(self, id: str) -> List[Relationship]:
        return self._outgoing.get(id, [])

    def find_by_type(self, type_: EntityType) -> List[Entity]:
        return self._by_type.get(type_, [])

    def find_by_name(self, name: str) -> List[Entity]:
        return self._by_name.get(name, [])

    def neighbors(self, id: str) -> List[Entity]:
        neighbor_ids = set()
        for r in self.get_outgoing(id):
            neighbor_ids.add(r.target_id)
        for r in self.get_incoming(id):
            neighbor_ids.add(r.source_id)
            
        return [self.get_entity(nid) for nid in neighbor_ids if self.get_entity(nid)]
