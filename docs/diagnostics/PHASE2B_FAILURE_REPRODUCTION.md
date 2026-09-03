# Phase 2B: Failure Reproduction - CommonJS Symbol Extraction

## Test Fixtures

### Fixture 1: CommonJS Named Exports (exports.func = ...)

```javascript
// auth.js
exports.login = async (username, password) => {
    const user = await db.getUser(username);
    if (user && verify(password, user.hash)) {
        return createSession(user.id);
    }
    return null;
};

exports.verify = (password, hash) => {
    return hashPassword(password) === hash;
};

exports.createSession = (userId) => {
    const token = generateToken();
    store_session(userId, token);
    return token;
};
```

### Fixture 2: CommonJS Object Literal (module.exports = {...})

```javascript
// handlers.js
module.exports = {
    login: async (req, res) => {
        const { username, password } = req.body;
        const token = await login(username, password);
        if (token) {
            res.json({ status: 'ok', token });
        } else {
            res.status(401).json({ status: 'failed' });
        }
    },

    logout: (req, res) => {
        const session_id = req.query.session_id;
        destroy_session(session_id);
        res.json({ status: 'ok' });
    }
};
```

### Fixture 3: ES Module Exports (control group)

```javascript
// auth.js
export const login = async (username, password) => {
    const user = await db.getUser(username);
    return createSession(user.id);
};

export function verify(password, hash) {
    return hashPassword(password) === hash;
}

export async function createSession(userId) {
    const token = generateToken();
    storeSession(userId, token);
    return token;
}
```

### Fixture 4: Regular Functions (baseline)

```javascript
// auth.js
function login(username, password) {
    const user = db.getUser(username);
    return createSession(user.id);
}

const verify = (password, hash) => {
    return hashPassword(password) === hash;
};

const createSession = function(userId) {
    const token = generateToken();
    storeSession(userId, token);
    return token;
};
```

## Current Extraction Behavior (Code Analysis)

### TypeScriptTreeSitterVisitor.visit() Tree Node Handling

**File**: backend/intelligence/engine/parser/providers/typescript.py:37-50

Currently handles:
```python
if node.type == 'function_declaration':
    self._handle_function_declaration(node)
elif node.type == 'lexical_declaration':
    self._handle_lexical_declaration(node)
elif node.type == 'class_declaration':
    self._handle_class_declaration(node)
elif node.type == 'import_statement':
    self._handle_import_statement(node)
```

### Expected Extraction Results

#### Fixture 1: exports.login = async () => {}

**Tree node type**: `expression_statement`
**Child nodes**:
```
expression_statement
  └─ assignment_expression
      ├─ member_expression
      │   ├─ identifier: "exports"
      │   └─ property_identifier: "login"
      └─ arrow_function
          ├─ parameters
          └─ body
```

**Current visitor behavior**: 
- Sees `expression_statement` (not in handler list)
- **Skips the entire subtree** ❌
- **Result**: login() NOT extracted

**Expected result**: 
- Symbol name: "login"
- Symbol type: "function"
- File: "auth.js"
- Lines: X-Y

**Actual result**: ❌ MISSING

#### Fixture 2: module.exports = {...}

**Tree node type**: `assignment_expression`
**Child nodes**:
```
assignment_expression
  ├─ member_expression: "module.exports"
  └─ object
      ├─ pair
      │   ├─ key: "login"
      │   └─ arrow_function
      └─ pair
          ├─ key: "logout"
          └─ arrow_function
```

**Current visitor behavior**: 
- Sees assignment_expression (not in handler list)
- **Skips the entire subtree** ❌
- **Result**: login(), logout() NOT extracted

**Expected result**: 
- 2 symbols: "login", "logout"
- Both type: "function"

**Actual result**: ❌ BOTH MISSING

#### Fixture 3: export const/function (Control)

**Tree node types**: `export_statement` wrapping function_declaration/lexical_declaration

**Current visitor behavior**: 
- Sees `export_statement` (not in handler list)
- May or may not recurse into children
- **Uncertain behavior** ⚠️

**Note**: Need to verify if export statements are properly handled by recursion.

#### Fixture 4: function/const (Baseline)

**Current visitor behavior**:
- `function login()` → function_declaration → **HANDLED** ✓
- `const verify = () => {}` → lexical_declaration → **HANDLED** ✓
- `const createSession = function() {}` → lexical_declaration → **HANDLED** ✓

**Expected result**: All 3 functions extracted ✓

**Actual result**: ✓ WORKS

## Test Execution (Theoretical)

If the extraction were to run on Fixture 1:

```
Input:  exports.login = async () => { ... }
        exports.verify = () => { ... }
        exports.createSession = () => { ... }

Parser output (tree-sitter):
  - expression_statement (line 2)
  - expression_statement (line 9)
  - expression_statement (line 13)

Visitor traversal:
  Node type: expression_statement
  → Check: is this 'function_declaration'? NO
  → Check: is this 'lexical_declaration'? NO
  → Check: is this 'class_declaration'? NO
  → Check: is this 'import_statement'? NO
  → Continue to children (no special handler)
  
  Child: assignment_expression
  → Check: is this 'function_declaration'? NO
  → Skip (no handler)

Result: 0 symbols extracted

Expected: 3 symbols (login, verify, createSession)
Actual: 0 symbols
Status: ❌ FAILURE
```

## Root Cause

The `TypeScriptTreeSitterVisitor.visit()` method only handles specific node types:
- function_declaration
- lexical_declaration (handles const/let with arrow/function expressions)
- class_declaration
- import_statement

CommonJS export patterns use:
- **assignment_expression** (not handled)
- **expression_statement** (not handled, but visitor recurses)
- member_expression targeting exports/module.exports (not recognized)

The visitor's recursion will traverse into these nodes but won't extract the symbols because:
1. assignment_expression is not in the handler list
2. The handler would need to recognize it's assigning to exports.*
3. The handler would need to extract the right-hand side expression

## Proof of Failure

When running:
```
get_symbol("login")
```

On a repository with `exports.login = async () => {}`:

**Current result**: 
```
[
  # Empty list
]
```

**Expected result**:
```
[
  {
    "symbol_id": "...",
    "name": "login",
    "qualified_name": "auth.login",
    "symbol_type": "function",
    "file": "auth.js",
    "line_start": 2,
    "line_end": 8
  }
]
```

## Complexity of the Fix

The fix requires:

1. **Extend the visitor** to recognize:
   - `assignment_expression` nodes
   - `expression_statement` nodes containing assignments
   - member_expression patterns: `exports.X`, `module.exports.X`
   - object literal patterns: `module.exports = { ... }`

2. **Extract symbol info**:
   - Property name as symbol name
   - Value type (arrow_function, function_expression, etc.) to determine symbol type
   - Line numbers from the assignment/value node

3. **Handle edge cases**:
   - Nested object literals
   - Re-assignment of exports
   - Mixed CommonJS and ES modules in same file

4. **Add tests** to prevent regression

**Estimated scope**: ~100-150 lines in typescript.py, ~300+ lines of tests

## Files to Modify (confirmed)

1. `backend/intelligence/engine/parser/providers/typescript.py`
   - Add _handle_assignment_expression() method
   - Add logic to detect exports patterns
   - Extend visit() to handle assignment_expression and expression_statement

2. New test file (or extend existing):
   - Test CommonJS named exports
   - Test module.exports object literal
   - Test ES export statements
   - Test mixed patterns
   - Integration test with get_symbol()
