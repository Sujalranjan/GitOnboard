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

  // Empty tree — no real scan data available yet
  return {
    name: repoName,
    type: 'directory',
    path: '',
    children: [],
  };
}

/**
 * 2. Streams real file content from Azurite Blob Storage via backend.
 * Explicitly surfaces 401, 404, 403, 500 without fabricating placeholder content.
 */
export async function getFileContent(
  repoName: string,
  filePath: string
): Promise<{ content: string; language?: string }> {
  if (!filePath || !filePath.trim()) {
    throw new Error('No file selected');
  }

  const res = await fetch(
    `${API_BASE}/${encodeURIComponent(repoName)}/file?path=${encodeURIComponent(filePath)}`
  );

  if (!res.ok) {
    if (res.status === 401) {
      throw new Error('Authentication Required (401). Please log in to view repository files.');
    }
    if (res.status === 404) {
      throw new Error(`File Not Found (404): '${filePath}' is not present in storage.`);
    }
    if (res.status === 403) {
      throw new Error(`Access Denied (403): You do not have permission to view '${filePath}'.`);
    }
    if (res.status === 408 || res.status === 504) {
      throw new Error(`Storage Timeout: Request to stream '${filePath}' timed out.`);
    }
    if (res.status >= 500) {
      throw new Error(`Storage Service Error (${res.status}): Azurite blob read failed for '${filePath}'.`);
    }
    throw new Error(`Failed to load file (${res.status}): ${filePath}`);
  }

  const data = await res.json();
  return {
    content: data.content ?? data.source_code ?? '',
    language: data.language,
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
