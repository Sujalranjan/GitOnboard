from typing import List
from ..model.query import RepositoryQuery, ActionType, TargetType, QueryClause, ClauseType

class DSLParser:
    """
    Parses a simple DSL into a RepositoryQuery AST.
    e.g. "FIND FEATURE Authentication"
    e.g. "FROM FEATURE Authentication FOLLOW DEPENDS_ON"
    """
    def parse(self, query_str: str) -> RepositoryQuery:
        tokens = query_str.strip().split()
        if not tokens:
            raise ValueError("Empty query")
            
        action_token = tokens[0].upper()
        if action_token not in [ActionType.FIND.value, ActionType.FROM.value]:
            raise ValueError(f"Unknown action: {action_token}")
            
        action = ActionType(action_token)
        
        target_type_token = tokens[1].upper()
        if target_type_token not in [t.value for t in TargetType]:
            raise ValueError(f"Unknown target type: {target_type_token}")
            
        target_type = TargetType(target_type_token)
        target_name = tokens[2]
        
        query = RepositoryQuery(
            action=action,
            target_type=target_type,
            target_name=target_name
        )
        
        # Parse optional clauses
        idx = 3
        while idx < len(tokens):
            clause_type_token = tokens[idx].upper()
            if clause_type_token in [c.value for c in ClauseType]:
                clause_type = ClauseType(clause_type_token)
                idx += 1
                if idx < len(tokens):
                    target = tokens[idx]
                    idx += 1
                    
                    depth = None
                    if idx < len(tokens) and tokens[idx].upper() == "DEPTH":
                        idx += 1
                        if idx < len(tokens):
                            depth = int(tokens[idx])
                            idx += 1
                            
                    query.clauses.append(QueryClause(
                        type=clause_type,
                        target=target,
                        depth=depth
                    ))
            else:
                idx += 1
                
        return query
