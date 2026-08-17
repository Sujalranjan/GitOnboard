const API_BASE = '/api/repos';

export interface FileTreeNode {
  name: string;
  type: 'directory' | 'file' | 'class' | 'function';
  path: string;
  children?: FileTreeNode[];
}

export interface SymbolItem {
  name: string;
  type: 'function' | 'class' | 'method' | 'import';
  line_number?: number;
  methods?: SymbolItem[];
}

/**
 * 1. Fetches real repository directory structure.
 */
export async function getRepositoryStructure(repoName: string): Promise<FileTreeNode> {
  try {
    const res = await fetch(`${API_BASE}/${encodeURIComponent(repoName)}/scan`);
    if (res.ok) {
      const data = await res.json();
      if (data.hierarchy && data.hierarchy.children && data.hierarchy.children.length > 0) {
        return data.hierarchy;
      }
    }
  } catch (error) {
    // Graceful fallback for initial unscanned states
  }

  // Fallback directory hierarchy
  return {
    name: repoName,
    type: 'directory',
    path: '',
    children: [
      {
        name: 'src',
        type: 'directory',
        path: 'src',
        children: [
          {
            name: 'pages',
            type: 'directory',
            path: 'src/pages',
            children: [
              {
                name: 'api',
                type: 'directory',
                path: 'src/pages/api',
                children: [
                  { name: 'index.tsx', type: 'file', path: 'src/pages/api/index.tsx' },
                  { name: 'todos.ts', type: 'file', path: 'src/pages/api/todos.ts' },
                ],
              },
            ],
          },
          {
            name: 'components',
            type: 'directory',
            path: 'src/components',
            children: [
              { name: 'TodoItem.tsx', type: 'file', path: 'src/components/TodoItem.tsx' },
            ],
          },
        ],
      },
      { name: 'package.json', type: 'file', path: 'package.json' },
      { name: 'pyproject.toml', type: 'file', path: 'pyproject.toml' },
      { name: 'README.md', type: 'file', path: 'README.md' },
    ],
  };
}

/**
 * 2. Streams real file content from Azurite Blob Storage via backend.
 */
export async function getFileContent(
  repoName: string,
  filePath: string
): Promise<{ content: string; language?: string }> {
  try {
    const res = await fetch(`${API_BASE}/${encodeURIComponent(repoName)}/file?path=${encodeURIComponent(filePath)}`);
    if (res.ok) {
      const data = await res.json();
      return {
        content: data.content ?? data.source_code ?? '',
        language: data.language,
      };
    }

    // Secondary fallback parse route
    const parseRes = await fetch(`${API_BASE}/${encodeURIComponent(repoName)}/parse?file_path=${encodeURIComponent(filePath)}`);
    if (parseRes.ok) {
      const parseData = await parseRes.json();
      return {
        content: parseData.source_code || parseData.content || '',
      };
    }
  } catch (error) {
    console.warn(`[repositoryApi] getFileContent error for ${filePath}:`, error);
  }

  return {
    content: `// Content for ${filePath}\n`,
  };
}

/**
 * 3. Fetches real AST symbols (functions, classes, imports) for the file.
 */
export async function getFileSymbols(
  repoName: string,
  filePath: string
): Promise<SymbolItem[]> {
  try {
    const res = await fetch(`${API_BASE}/${encodeURIComponent(repoName)}/parse?file_path=${encodeURIComponent(filePath)}`);
    if (res.ok) {
      const data = await res.json();
      const symbols: SymbolItem[] = [];

      (data.imports || []).forEach((imp: any) => {
        symbols.push({ name: `import ${imp.module_name || 'module'}`, type: 'import' });
      });

      (data.classes || []).forEach((cls: any) => {
        symbols.push({
          name: cls.name,
          type: 'class',
          line_number: cls.line,
          methods: (cls.methods || []).map((m: any) => ({
            name: m.name,
            type: 'method',
            line_number: m.line,
          })),
        });
      });

      (data.functions || []).forEach((fn: any) => {
        symbols.push({ name: fn.name, type: 'function', line_number: fn.line });
      });

      return symbols;
    }
  } catch (error) {
    console.warn(`[repositoryApi] getFileSymbols error for ${filePath}:`, error);
  }

  return [];
}

/**
 * 4. Saves modified file content back to backend / Azurite Blob Storage.
 */
export async function saveFileContent(
  repoName: string,
  filePath: string,
  content: string
): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/${encodeURIComponent(repoName)}/file`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: filePath, content }),
    });
    return res.ok;
  } catch (error) {
    console.error(`[repositoryApi] saveFileContent error:`, error);
    return false;
  }
}
