"""
TypeScript/JavaScript provider using tree-sitter for real AST parsing.
"""
import tree_sitter
import tree_sitter_typescript
import tree_sitter_javascript
from typing import List, Dict, Any, Optional
from .base import LanguageProvider, ParsedFile


class TypeScriptTreeSitterVisitor:
    """Walk tree-sitter AST to extract symbols and imports from TS/TSX code."""

    def __init__(self, source: str, file_path: str):
        self.source = source
        self.source_bytes = source.encode('utf-8')
        self.file_path = file_path
        self.symbols: List[Dict[str, Any]] = []
        self.imports: List[Dict[str, Any]] = []

    def _get_text(self, node) -> str:
        """Extract text for a node."""
        if not node:
            return ""
        return self.source_bytes[node.start_byte:node.end_byte].decode('utf-8', errors='replace')

    def _get_name(self, node) -> Optional[str]:
        """Extract identifier name from a node."""
        if node.type == 'identifier' or node.type == 'type_identifier':
            return self._get_text(node)
        # For names in declarators, find the child identifier
        for child in node.children:
            if child.type in ('identifier', 'type_identifier'):
                return self._get_text(child)
        return None

    def visit(self, node):
        """Traverse the AST and extract symbols and imports."""
        if node.type == 'function_declaration':
            self._handle_function_declaration(node)
        elif node.type == 'lexical_declaration':
            self._handle_lexical_declaration(node)
        elif node.type == 'class_declaration':
            self._handle_class_declaration(node)
        elif node.type == 'import_statement':
            self._handle_import_statement(node)
        elif node.type == 'expression_statement':
            self._handle_expression_statement(node)

        # Recurse
        for child in node.children:
            self.visit(child)

    def _handle_function_declaration(self, node):
        """Extract function declaration: function foo() {}"""
        name_node = node.child_by_field_name('name')
        if name_node:
            name = self._get_text(name_node)
            self.symbols.append({
                "name": name,
                "type": "function",
                "line": node.start_point[0] + 1,
                "file": self.file_path,
                "start_line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1
            })

    def _handle_lexical_declaration(self, node):
        """Extract arrow/function expressions: const foo = () => {} or const foo = function() {}"""
        for child in node.children:
            if child.type == 'variable_declarator':
                name_node = child.child_by_field_name('name')
                if not name_node:
                    continue
                name = self._get_text(name_node)

                # Check if the value is an arrow_function or function_expression
                value_node = child.child_by_field_name('value')
                if value_node and value_node.type in ('arrow_function', 'function'):
                    self.symbols.append({
                        "name": name,
                        "type": "function",
                        "line": child.start_point[0] + 1,
                        "file": self.file_path,
                        "start_line": child.start_point[0] + 1,
                        "end_line": child.end_point[0] + 1
                    })

    def _handle_class_declaration(self, node):
        """Extract class and its methods."""
        name_node = node.child_by_field_name('name')
        if name_node:
            class_name = self._get_text(name_node)
            self.symbols.append({
                "name": class_name,
                "type": "class",
                "line": node.start_point[0] + 1,
                "file": self.file_path,
                "start_line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1
            })

            # Extract methods
            class_body = node.child_by_field_name('body')
            if class_body:
                for child in class_body.children:
                    if child.type == 'method_definition':
                        method_name_node = child.child_by_field_name('name')
                        if method_name_node:
                            method_name = self._get_text(method_name_node)
                            self.symbols.append({
                                "name": method_name,
                                "type": "method",
                                "line": child.start_point[0] + 1,
                                "file": self.file_path,
                                "start_line": child.start_point[0] + 1,
                                "end_line": child.end_point[0] + 1,
                                "parent_class": class_name
                            })

    def _handle_import_statement(self, node):
        """Extract import statements."""
        # Get the module/path being imported from
        module_node = None
        for child in node.children:
            if child.type == 'string':
                module_node = child
                break

        if not module_node:
            return

        # Extract the module string (skip quotes)
        module_text = self._get_text(module_node)
        # Remove quotes
        module = module_text.strip('"\'')

        self.imports.append({
            "module": module,
            "line": node.start_point[0] + 1,
            "type": "import"
        })

    def _handle_expression_statement(self, node):
        """Handle expression statements, particularly CommonJS exports."""
        # expression_statement → assignment_expression → exports.X = func
        # or: expression_statement → call_expression
        if not node.children:
            return

        # Get the first child (usually the actual expression)
        expr = node.children[0] if node.children else None
        if not expr:
            return

        if expr.type == 'assignment_expression':
            self._handle_commonjs_assignment(expr)

    def _handle_commonjs_assignment(self, node):
        """
        Extract CommonJS exports from assignment expressions.
        Handles:
          - exports.login = async () => {}
          - module.exports = { login: () => {}, ... }
          - exports.login = function() {}
        """
        # assignment_expression has: left, right
        left = node.child_by_field_name('left')
        value = node.child_by_field_name('right')

        if not left or not value:
            return

        # Check if left side is exports.* or module.exports*
        # Pattern 1: exports.propertyName
        if left.type == 'member_expression':
            obj_part = left.children[0] if left.children else None
            prop_part = left.child_by_field_name('property')

            if not obj_part or not prop_part:
                return

            obj_text = self._get_text(obj_part).strip()

            # Case 1: exports.login = ...
            if obj_text == 'exports':
                prop_name = self._get_text(prop_part).strip()
                self._extract_commonjs_exported_symbol(
                    prop_name, value, node,
                    export_type='named_export'
                )

            # Case 2: module.exports.login = ... (less common)
            elif obj_text == 'module.exports':
                prop_name = self._get_text(prop_part).strip()
                self._extract_commonjs_exported_symbol(
                    prop_name, value, node,
                    export_type='named_export'
                )

        # Pattern 2: module.exports = { ... } (object literal)
        elif left.type == 'identifier' and self._get_text(left).strip() == 'exports':
            if value.type == 'object':
                self._extract_commonjs_object_exports(value, node)

        # Pattern 3: module.exports = {...}
        elif left.type == 'member_expression':
            # Check for module.exports
            left_text = self._get_text(left).strip()
            if left_text == 'module.exports' and value.type == 'object':
                self._extract_commonjs_object_exports(value, node)

    def _extract_commonjs_exported_symbol(self, name: str, value_node, location_node, export_type: str = 'named_export'):
        """
        Extract a CommonJS exported symbol from an assignment.

        Args:
            name: The exported name (e.g., 'login')
            value_node: The node containing the value (function, arrow_function, etc.)
            location_node: The node to use for line number
            export_type: 'named_export' or 'default_export'
        """
        if not name:
            return

        # Only extract if value is a function-like construct
        value_type = value_node.type if value_node else None
        if value_type not in ('arrow_function', 'function', 'function_expression', 'async_arrow_function'):
            return

        # Determine if async
        value_text = self._get_text(value_node)
        is_async = 'async' in value_text.split()

        self.symbols.append({
            "name": name,
            "type": "function",
            "line": location_node.start_point[0] + 1,
            "file": self.file_path,
            "start_line": location_node.start_point[0] + 1,
            "end_line": location_node.end_point[0] + 1,
            "export_type": export_type,
            "is_async": is_async
        })

    def _extract_commonjs_object_exports(self, object_node, location_node):
        """
        Extract symbols from a CommonJS object literal export.

        Handles: module.exports = { login: async () => {}, ... }
        """
        if object_node.type != 'object':
            return

        # Iterate through object properties
        for child in object_node.children:
            if child.type == 'pair':
                # pair has: key and value
                key_node = child.child_by_field_name('key')
                value_node = child.child_by_field_name('value')

                if not key_node or not value_node:
                    continue

                # Extract key name (could be identifier or string)
                if key_node.type == 'property_identifier':
                    key_name = self._get_text(key_node).strip()
                elif key_node.type == 'string':
                    key_text = self._get_text(key_node).strip()
                    # Remove quotes
                    key_name = key_text.strip('"\'')
                else:
                    key_name = self._get_text(key_node).strip()

                # Extract value if it's a function
                value_type = value_node.type
                if value_type in ('arrow_function', 'function', 'function_expression', 'async_arrow_function'):
                    value_text = self._get_text(value_node)
                    is_async = 'async' in value_text.split()

                    self.symbols.append({
                        "name": key_name,
                        "type": "function",
                        "line": child.start_point[0] + 1,
                        "file": self.file_path,
                        "start_line": child.start_point[0] + 1,
                        "end_line": child.end_point[0] + 1,
                        "export_type": "object_property",
                        "is_async": is_async
                    })


class TypeScriptProvider(LanguageProvider):
    language = "TypeScript"

    def __init__(self):
        self.ts_lang = tree_sitter.Language(tree_sitter_typescript.language_tsx())
        self.js_lang = tree_sitter.Language(tree_sitter_javascript.language())

    def parse(self, file_path: str, source: str) -> ParsedFile:
        language = "TypeScript" if file_path.endswith((".ts", ".tsx")) else "JavaScript"

        # Select the appropriate parser
        lang = self.ts_lang if language == "TypeScript" else self.js_lang
        parser = tree_sitter.Parser(lang)

        try:
            tree = parser.parse(source.encode('utf-8'))

            # Extract symbols and imports
            visitor = TypeScriptTreeSitterVisitor(source, file_path)
            visitor.visit(tree.root_node)

            return ParsedFile(
                file_path=file_path,
                language=language,
                ast=tree,  # Return the actual tree-sitter tree
                source=source,
                metadata={
                    "symbols": visitor.symbols,
                    "imports": visitor.imports
                }
            )
        except Exception as e:
            # Fallback to empty parse on error
            return ParsedFile(
                file_path=file_path,
                language=language,
                ast=None,
                source=source,
                metadata={"symbols": [], "imports": []},
                diagnostics=[{
                    "message": f"Parse error: {str(e)}",
                    "line": 1,
                    "column": 1,
                    "severity": "ERROR"
                }]
            )


class JavaScriptProvider(TypeScriptProvider):
    language = "JavaScript"
