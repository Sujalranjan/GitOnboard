# Phase 2A Diagnosis: JavaScript Symbol Intelligence

## Current Implementation Path

```
JavaScript/TypeScript Source
  ↓
tree-sitter parse (TypeScriptProvider)
  ↓
TypeScriptTreeSitterVisitor.visit()
  ↓
extract symbols (functions, classes, methods)
  ↓
SymbolAnalyzer._process_synthetic_ast()
  ↓
Entity + Relationship creation
  ↓
RepositoryModel (in-memory)
  ↓
save_rim_to_fact_store()
  ↓
FactSymbol table
  ↓
get_symbol() lookup
  ↓
LLM receives results
```

## What's Currently Extracted

**File**: `backend/intelligence/engine/parser/providers/typescript.py`

The TypeScriptTreeSitterVisitor handles:
1. `function_declaration` → "function foo() {}"
2. `lexical_declaration` → "const foo = () => {}" or "const foo = function() {}"
3. `class_declaration` → "class Foo {}"
4. `method_definition` → methods within classes
5. `import_statement` → import statements

## What's NOT Extracted

**CommonJS Exports** (the problem):
```javascript
exports.login = async () => {}
```

```javascript
module.exports.login = function() {}
```

```javascript
module.exports = {
  login: async () => {}
}
```

**ES Module Named Exports** (may be incomplete):
```javascript
export const login = async () => {}
```

## Symbol Storage Model

**File**: `backend/models/fact_store.py::FactSymbol`

```python
class FactSymbol:
    id: str                    # Unique ID
    analysis_id: int           # Analysis reference
    file_id: str               # Foreign key to FactFile
    name: str                  # Symbol name (e.g., "login")
    qualified_name: str        # Fully qualified (e.g., "auth.login")
    symbol_type: str           # function, class, method, variable, etc.
    line_start: int            # Start line
    line_end: int              # End line
    signature_hash: str        # For dedup
    metadata_json: dict        # Extensible metadata
```

## Symbol Lookup

**File**: `backend/repository_tools/tools.py::get_symbol()`

```python
def get_symbol(self, name: str) -> List[Dict]:
    symbols = self.db.query(FactSymbol).filter(
        FactSymbol.analysis_id == self.analysis_id,
        FactSymbol.name.ilike(f"%{name}%"),  # Case-insensitive substring match
    ).limit(20).all()
```

**Behavior**:
- Case-insensitive substring match on `FactSymbol.name`
- Returns up to 20 results
- Returns full symbol info including file, type, line range

## Entity Type Enum

**File**: `backend/intelligence/rim/enums.py::EntityType`

Includes: FUNCTION, METHOD, CLASS, VARIABLE, CONSTANT, INTERFACE, ENUM, etc.

## Relationships

When a symbol is extracted, a `DECLARES` relationship is created:
- Source: File entity
- Target: Symbol entity
- Type: `DECLARES`

This allows queries like: "Which symbols does file X declare?"

## Current Test Coverage

**grep results**: No specific tests for CommonJS exports extraction found.

Existing tests:
- TypeScript/JavaScript imports extraction
- Function/class/method extraction
- Python symbol extraction (Python AST visitor)

## The Problem

CommonJS exports are **syntactically different** from function declarations:

```javascript
// HANDLED: Direct function
function login() {}

// HANDLED: Arrow function in const
const login = async () => {}

// NOT HANDLED: CommonJS export (assignment to exports object)
exports.login = async () => {}

// NOT HANDLED: CommonJS module.exports
module.exports.login = async () => {}
```

The tree-sitter parser WILL parse these statements, but the visitor doesn't extract them because:
1. `exports.login = ...` is an `assignment` or `assignment_expression` node
2. The value may be an `arrow_function` or `function_expression`
3. The current visitor only looks for specific node types (function_declaration, lexical_declaration)

## Solution Required

Extend `TypeScriptTreeSitterVisitor` to handle:

### 1. Expression Statements with Assignment to exports
```
expression_statement
  ├─ assignment_expression
      ├─ member_expression (exports.login or module.exports.login)
      └─ arrow_function / function_expression / other value
```

### 2. Module.exports Object Literal
```
assignment_expression
  ├─ member_expression (module.exports)
  └─ object_literal
      └─ object_assignments (key: function / arrow_function)
```

### 3. Symbol Identity

When extracting CommonJS exports, the symbol name should be:
- **name**: "login" (the exported property name, not "exports")
- **qualified_name**: "auth.login" (module path + property name)
- **metadata**: Include export info: `{"export_type": "commonjs", "export_kind": "named_export"}`

This ensures `get_symbol("login")` finds it regardless of syntax.

## Files to Modify

1. **backend/intelligence/engine/parser/providers/typescript.py**
   - Extend TypeScriptTreeSitterVisitor with CommonJS handling
   - Add _handle_assignment_expression() method
   - Add _handle_module_exports_object() method

2. **Tests** (to add):
   - test_extract_commonjs_exports()
   - test_extract_module_exports_object()
   - test_extract_es_exports() (if incomplete)
   - test_symbol_lookup_commonjs() (integration)

## No Changes Needed (for now)

- FactSymbol model (works as-is)
- get_symbol() lookup (works as-is)
- Entity/Relationship persistence (works as-is)
- SymbolAnalyzer (works as-is)
- Other language providers

The issue is purely in the extraction/parsing layer, not the storage or lookup layer.
