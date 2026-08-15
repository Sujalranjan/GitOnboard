from typing import List
import re
from ...rim.repository import RepositoryModel
from ...rim.entity import Entity
from ...rim.enums import EntityType

def infer_keywords_from_entity(entity: Entity, model: RepositoryModel) -> List[str]:
    keywords = set()
    
    # 1. Identifier Evidence
    # Split by camelCase or snake_case
    parts = re.sub(r'([A-Z])', r' \1', entity.name).split()
    parts = [p.lower() for part in parts for p in part.split('_')]
    
    for p in parts:
        if p and p not in ["get", "set", "is", "has"]:
            keywords.add(p)
            
    # 2. Route Evidence
    if entity.type == EntityType.ROUTE:
        route_parts = entity.name.split('/')
        for p in route_parts:
            p = p.strip().lower()
            if p and p not in ["get", "post", "put", "delete", "api", "v1"]:
                # strip path params like {id}
                p = re.sub(r'[{}]', '', p)
                keywords.add(p)
                
    # 3. Structural Context
    if entity.location:
        path = entity.location.repository_path.lower()
        folders = path.split('/')
        for f in folders[:-1]: # exclude filename
            if f and f not in ["src", "app", "lib", "main"]:
                keywords.add(f)
                
    return list(keywords)
