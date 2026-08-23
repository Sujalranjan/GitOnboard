export class ApiError extends Error {
  constructor(message, status = 500, data = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

export async function fetchAPI(endpoint, options = {}) {
  const defaultHeaders = {
    'Content-Type': 'application/json',
  };

  const config = {
    ...options,
    headers: {
      ...defaultHeaders,
      ...options.headers,
    },
  };

  try {
    const res = await fetch(`/api${endpoint}`, config);
    const contentType = res.headers.get('content-type') || '';

    let data = null;
    let text = '';

    if (contentType.includes('application/json')) {
      try {
        data = await res.json();
      } catch {
        data = null;
      }
    } else {
      try {
        text = await res.text();
      } catch {
        text = '';
      }
    }

    if (!res.ok) {
      const errorMsg =
        (data && (data.detail || data.message || data.error)) ||
        text ||
        `API Error: ${res.status} ${res.statusText || ''}`.trim();
      throw new ApiError(errorMsg, res.status, data);
    }

    return data !== null ? data : text;
  } catch (error) {
    console.error(`[API Error] ${endpoint}:`, error);
    throw error;
  }
}
