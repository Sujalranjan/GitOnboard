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
