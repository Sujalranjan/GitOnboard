# QueryLayer Bidirectional Query API

## Overview

The QueryLayer provides a unified bidirectional interface for accessing the RepositoryModel using both forward and reverse relationship queries.

## Initialization

```python
from backend.intelligence.query_layer import QueryLayer
from backend.intelligence.rim.repository import RepositoryModel

# Create a QueryLayer from a RepositoryModel
query = QueryLayer(repository_model)
```

## Forward Query Methods

Forward queries return the targets of relationships from a given entity.

### CALLS Relationships

```python
# What functions does this function call?
callees = query.get_calls(function_id)
```

### IMPORTS Relationships

```python
# What does this entity import?
imports = query.get_imports(entity_id)
```

### DEPENDS_ON Relationships

```python
# What does this file depend on?
dependencies = query.get_dependencies(file_id)
```

### USES Relationships

```python
# What does this entity use?
uses = query.get_uses(entity_id)
```

### INHERITS Relationships

```python
# What does this class inherit from?
parents = query.get_inherits(class_id)
```

### IMPLEMENTS Relationships

```python
# What interfaces/contracts does this class implement?
interfaces = query.get_implements(class_id)
```

## Reverse Query Methods

Reverse queries return the sources of relationships to a given entity (bidirectional queries).

### Reverse CALLS

```python
# What functions call this function?
callers = query.get_called_by(function_id)
# Alias: query.get_callers(function_id)
```

### Reverse IMPORTS

```python
# What entities import this entity?
importers = query.get_imported_by(entity_id)
# Alias: query.get_importers(entity_id)
```

### Reverse DEPENDS_ON

```python
# What files depend on this file?
dependents = query.get_depended_by(file_id)
# Alias: query.get_dependent_files(file_id)
```

### Reverse USES

```python
# What entities use this entity?
users = query.get_used_by(entity_id)
# Alias: query.get_users(entity_id)
```

### Reverse INHERITS

```python
# What classes extend this class?
subclasses = query.get_extended_by(class_id)
# Alias: query.get_subclasses(class_id)
```

### Reverse IMPLEMENTS

```python
# What classes implement this interface?
implementations = query.get_implementers(interface_id)
# Alias: query.get_implementations(interface_id)
```

## Relationship Query Methods

Get all relationships (forward or reverse) with metadata preservation.

### Forward Relationships

```python
# Get all forward relationships from an entity
all_forward = query.get_forward_relationships(entity_id)

# Get forward relationships of a specific type
calls_only = query.get_forward_relationships(entity_id, rel_type="CALLS")

# Result format:
# [
#     {
#         "type": "CALLS",
#         "target_id": "func_target",
#         "metadata": {"line": 42, "snippet": "..."}
#     },
#     ...
# ]
```

### Reverse Relationships

```python
# Get all reverse relationships to an entity
all_reverse = query.get_reverse_relationships(entity_id)

# Get reverse relationships of a specific type
callers = query.get_reverse_relationships(entity_id, rel_type="CALLS")

# Result format:
# [
#     {
#         "type": "CALLS",
#         "source_id": "func_caller",
#         "metadata": {"line": 42, "snippet": "..."}
#     },
#     ...
# ]
```

## Structural Query Methods

Query entities by their structural relationships.

```python
# Get classes defined in a file
classes = query.get_classes_in_file(file_id)

# Get functions defined in a module
functions = query.get_functions_in_module(module_id)

# Get all directories
directories = query.get_directories()

# Get all files
files = query.get_files()
```

## Entity Search Methods

```python
# Find functions by name
functions = query.find_function(name)

# Find classes by name
classes = query.get_class(name)

# Get a specific file
file = query.get_file(file_id)

# Search entities by substring
results = query.search_entities(query_string)
```

## Supported Relationship Types

The QueryLayer supports queries on the following relationship types:

- **CALLS**: Function/method invocation
- **IMPORTS**: Module/symbol imports
- **DEPENDS_ON**: File/module dependencies
- **USES**: Entity usage
- **INHERITS**: Class inheritance
- **IMPLEMENTS**: Interface implementation

## Return Values

All query methods return:
- Lists of entity IDs (for direct queries like `get_calls()`)
- Lists of dictionaries with metadata (for relationship queries like `get_forward_relationships()`)
- Empty lists `[]` when no results are found
- `None` or empty results for nonexistent entities

## Bidirectional Consistency

The QueryLayer maintains consistency between forward and reverse queries. For any relationship A → B:
- `get_calls("A")` returns B
- `get_called_by("B")` returns A

This allows for complete graph traversal in both directions.

## Usage Examples

### Finding All Callers of a Function

```python
# Get direct callers
callers = query.get_called_by("func_login")

# Get the actual function entities
caller_entities = [query.get_file(cid) for cid in callers]
```

### Tracing Dependencies

```python
# What does app.py depend on?
direct_deps = query.get_dependencies("file_app_py")

# What files depend on utils.py?
dependents = query.get_depended_by("file_utils_py")
```

### Class Hierarchy

```python
# What's the parent of DerivedClass?
parents = query.get_inherits("class_derived")

# What classes extend BaseClass?
children = query.get_extended_by("class_base")

# What implements an interface?
implementations = query.get_implementers("interface_serializable")
```

### Mixed Relationship Types

```python
# Get all relationships (any type) from an entity
all_rels = query.get_forward_relationships("entity_id")

# Get only CALLS relationships
calls = query.get_forward_relationships("entity_id", rel_type="CALLS")

# Preserve metadata for evidence
for rel in all_rels:
    print(f"{rel['type']}: {rel['source_id']} -> {rel['target_id']}")
    print(f"  Evidence: {rel['metadata']}")
```

## Performance Considerations

- QueryLayer builds indexes during initialization for fast lookups
- All queries are O(n) where n is the number of relationships
- For large repositories, consider filtering by relationship type when possible

## Backwards Compatibility

The QueryLayer maintains full backwards compatibility with existing code. All original methods are preserved:
- `find_function()`
- `get_class()`
- `get_file()`
- `get_classes_in_file()`
- `get_functions_in_module()`
- `get_directories()`
- `get_files()`
- `search_entities()`

The new reverse query methods are additions that don't modify existing behavior.
