import os
import tree_sitter
import tree_sitter_python
import tree_sitter_javascript
import tree_sitter_typescript
import tree_sitter_java

class LanguageParser:
    def __init__(self):
        self.languages = {
            ".py": tree_sitter.Language(tree_sitter_python.language()),
            ".js": tree_sitter.Language(tree_sitter_javascript.language()),
            ".jsx": tree_sitter.Language(tree_sitter_javascript.language()),
            ".ts": tree_sitter.Language(tree_sitter_typescript.language_typescript()),
            ".tsx": tree_sitter.Language(tree_sitter_typescript.language_tsx()),
            ".java": tree_sitter.Language(tree_sitter_java.language()),
        }

    def supports_extension(self, ext: str) -> bool:
        return ext.lower() in self.languages

    def parse_source(self, source: str, ext: str):
        lang = self.languages.get(ext.lower())
        if not lang:
            raise ValueError(f"Unsupported extension: {ext}")
        
        try:
            parser = tree_sitter.Parser(lang)
        except TypeError:
            # Fallback for older tree-sitter versions
            parser = tree_sitter.Parser()
            parser.set_language(lang)
            
        tree = parser.parse(source.encode('utf-8'))
        return tree, lang

    def extract_entities(self, tree, source: str, file_id: str, module_id: str):
        entities = {
            "imports": [],
            "functions": [],
            "classes": [],
            "methods": [],
            "variables": []
        }
        
        source_bytes = source.encode('utf-8')

        def get_text(node):
            if not node:
                return ""
            return source_bytes[node.start_byte:node.end_byte].decode('utf-8')

        def traverse(node, current_class_id=None):
            # Imports
            if node.type in ['import_statement', 'import_from_statement', 'import_declaration']:
                text = get_text(node)
                module_name = ""
                source_node = node.child_by_field_name('source')
                if source_node:
                    module_name = get_text(source_node).strip("'\"")
                else:
                    import re
                    match = re.search(r'''from\s+['"]([^'"]+)['"]|import\s+['"]([^'"]+)['"]|from\s+([a-zA-Z0-9_\.]+)|import\s+([a-zA-Z0-9_\.]+)''', text)
                    if match:
                        module_name = match.group(1) or match.group(2) or match.group(3) or match.group(4) or ""
                    else:
                        module_name = text.split()[1] if len(text.split()) > 1 else text
                
                if module_name:
                    entities["imports"].append({
                        "module_name": module_name.strip("'\""),
                        "alias": ""
                    })


            # Classes
            elif node.type in ['class_definition', 'class_declaration']:
                name_node = node.child_by_field_name('name')
                class_name = get_text(name_node) if name_node else f"AnonymousClass_{node.start_point[0]}"
                cls_id = f"{module_id}::{class_name}" if module_id else f"{file_id}::{class_name}"
                
                entities["classes"].append({
                    "id": cls_id,
                    "name": class_name,
                    "line_number": node.start_point[0] + 1,
                    "docstring": "", # Simplified
                    "source_segment": get_text(node)
                })
                current_class_id = cls_id

            # Functions / Methods
            elif node.type in ['function_definition', 'function_declaration', 'method_definition', 'method_declaration']:
                name_node = node.child_by_field_name('name')
                func_name = get_text(name_node) if name_node else f"AnonymousFn_{node.start_point[0]}"
                
                if current_class_id:
                    method_id = f"{current_class_id}.{func_name}"
                    entities["methods"].append({
                        "id": method_id,
                        "name": func_name,
                        "class_id": current_class_id,
                        "line_number": node.start_point[0] + 1,
                        "docstring": "",
                        "parameters": [],
                        "is_async": "async" in get_text(node).split(),
                        "source_segment": get_text(node)
                    })
                else:
                    fn_id = f"{module_id}::{func_name}" if module_id else f"{file_id}::{func_name}"
                    entities["functions"].append({
                        "id": fn_id,
                        "name": func_name,
                        "line_number": node.start_point[0] + 1,
                        "docstring": "",
                        "parameters": [],
                        "is_async": "async" in get_text(node).split(),
                        "source_segment": get_text(node)
                    })

            # Variables and Arrow Functions
            elif node.type in ['assignment', 'variable_declarator', 'lexical_declaration', 'variable_declaration']:
                declarators = []
                if node.type in ['lexical_declaration', 'variable_declaration']:
                    declarators = [c for c in node.children if c.type == 'variable_declarator']
                else:
                    declarators = [node]
                    
                for decl in declarators:
                    name_node = decl.child_by_field_name('name') or decl.child_by_field_name('left')
                    val_node = decl.child_by_field_name('value') or decl.child_by_field_name('right')
                    
                    if name_node:
                        var_name = get_text(name_node)
                        # Check if value is a function
                        if val_node and val_node.type == 'arrow_function':
                            fn_id = f"{module_id}::{var_name}" if module_id else f"{file_id}::{var_name}"
                            entities["functions"].append({
                                "id": fn_id,
                                "name": var_name,
                                "line_number": decl.start_point[0] + 1,
                                "docstring": "",
                                "parameters": [],
                                "is_async": "async" in get_text(val_node).split(),
                                "source_segment": get_text(decl)
                            })
                        else:
                            var_id = f"{module_id}::{var_name}" if module_id else f"{file_id}::{var_name}"
                            entities["variables"].append({
                                "id": var_id,
                                "name": var_name,
                                "line_number": decl.start_point[0] + 1
                            })

            for child in node.children:
                traverse(child, current_class_id)

        traverse(tree.root_node)
        return entities

    def extract_calls(self, tree, source: str):
        calls = []
        source_bytes = source.encode('utf-8')

        def get_text(node):
            if not node:
                return ""
            return source_bytes[node.start_byte:node.end_byte].decode('utf-8')

        def traverse(node, current_caller=None):
            if node.type in ['function_definition', 'function_declaration', 'method_definition', 'method_declaration', 'arrow_function']:
                name_node = node.child_by_field_name('name')
                if name_node:
                    current_caller = get_text(name_node)

            if node.type in ['call', 'call_expression', 'method_invocation']:
                func_node = node.child_by_field_name('function') or node.child_by_field_name('name')
                if func_node:
                    callee_name = get_text(func_node)
                    if current_caller:
                        calls.append((current_caller, callee_name))

            for child in node.children:
                traverse(child, current_caller)

        traverse(tree.root_node)
        return calls
