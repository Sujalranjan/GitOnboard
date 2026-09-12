/**
 * Repository hash lookup - Convert user-friendly names to efficient UUIDs
 */

const hashCache: Record<string, string> = {};

export async function getRepoHash(repoName: string): Promise<string> {
  // Check cache first
  if (hashCache[repoName]) {
    return hashCache[repoName];
  }

  try {
    const response = await fetch(`/api/repos/lookup-hash?name=${encodeURIComponent(repoName)}`);
    if (response.ok) {
      const data = await response.json();
      const hash = data.repository_hash;
      // Cache for future use
      hashCache[repoName] = hash;
      return hash;
    }
  } catch (error) {
    console.error(`Failed to look up repository hash for ${repoName}:`, error);
  }

  // Fallback to repo name if lookup fails
  return repoName;
}

export function clearHashCache() {
  Object.keys(hashCache).forEach((key) => delete hashCache[key]);
}
