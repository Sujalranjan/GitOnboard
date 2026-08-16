import { fetchAPI } from './api';

export const repositoryService = {
  getAll: () => fetchAPI('/repos'),
  
  delete: (repoName) => fetchAPI(`/repos/${repoName}`, { method: 'DELETE' }),
  
  scan: (repoName) => fetchAPI(`/repos/${repoName}/scan`),
  
  parseFile: (repoName, filePath) => fetchAPI(`/repos/${repoName}/parse?file_path=${encodeURIComponent(filePath)}`),
  getFile: (repoName, filePath) => fetchAPI(`/repos/${repoName}/file?path=${encodeURIComponent(filePath)}`),
  
  import: (url) => fetchAPI('/import', { method: 'POST', body: JSON.stringify({ url }) }),
  
  reanalyze: (repoName) => fetchAPI(`/repos/${repoName}/reanalyze`, { method: 'POST' }),
  
  cancel: (repoName) => fetchAPI(`/repos/${repoName}/cancel`, { method: 'POST' })
};
