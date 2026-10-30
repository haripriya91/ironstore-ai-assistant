export type HistoryMessage = {
  role: 'user' | 'assistant'
  content: string
}

export type SourceReference = {
  source_id: string
  chunk_id: string
  document_id: string
  title: string
  page: number
  excerpt: string
  url: string
}

export type ChatResponse = {
  answer: string
  sources: SourceReference[]
  limitations: string[]
}

export type DocumentRecord = {
  document_id: string
  title: string
  department: string
  category: string
  url: string
}

export type DocumentListResponse = {
  documents: DocumentRecord[]
  total: number
  departments: string[]
}

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim()

export function resolveApiUrl(path: string): string {
  if (!apiBaseUrl) return path
  return new URL(path, `${apiBaseUrl.replace(/\/+$/, '')}/`).toString()
}

export function resolveDocumentUrl(path: string): string {
  const baseUrl = apiBaseUrl || window.location.origin
  return new URL(path, `${baseUrl.replace(/\/+$/, '')}/`).toString()
}

async function requestJson(path: string, init?: RequestInit): Promise<unknown> {
  let response: Response

  try {
    response = await fetch(resolveApiUrl(path), init)
  } catch (error) {
    if (error instanceof Error) {
      throw new Error(`Could not reach the IronStore API: ${error.message}`, {
        cause: error,
      })
    }
    throw new Error('Could not reach the IronStore API.', { cause: error })
  }

  const responseText = await response.text()
  let payload: unknown = null

  if (responseText) {
    try {
      payload = JSON.parse(responseText) as unknown
    } catch {
      if (response.ok) {
        throw new Error('The IronStore API returned invalid JSON.')
      }
      payload = responseText
    }
  }

  if (!response.ok) {
    const detail =
      typeof payload === 'object' &&
      payload !== null &&
      'detail' in payload &&
      typeof payload.detail === 'string'
        ? payload.detail
        : typeof payload === 'string'
          ? payload
          : response.statusText
    throw new Error(
      detail
        ? `IronStore API error (${response.status}): ${detail}`
        : `IronStore API error (${response.status}).`,
    )
  }

  if (payload === null) {
    throw new Error('The IronStore API returned an empty response.')
  }

  return payload
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function readSource(value: unknown): SourceReference {
  if (
    !isRecord(value) ||
    typeof value.source_id !== 'string' ||
    typeof value.chunk_id !== 'string' ||
    typeof value.document_id !== 'string' ||
    typeof value.title !== 'string' ||
    typeof value.page !== 'number' ||
    typeof value.excerpt !== 'string' ||
    typeof value.url !== 'string'
  ) {
    throw new Error('The IronStore API returned an invalid source.')
  }
  return {
    source_id: value.source_id,
    chunk_id: value.chunk_id,
    document_id: value.document_id,
    title: value.title,
    page: value.page,
    excerpt: value.excerpt,
    url: value.url,
  }
}

function readDocument(value: unknown): DocumentRecord {
  if (
    !isRecord(value) ||
    typeof value.document_id !== 'string' ||
    typeof value.title !== 'string' ||
    typeof value.department !== 'string' ||
    typeof value.category !== 'string' ||
    typeof value.url !== 'string'
  ) {
    throw new Error('The IronStore API returned an invalid document.')
  }
  return {
    document_id: value.document_id,
    title: value.title,
    department: value.department,
    category: value.category,
    url: value.url,
  }
}

export async function fetchDocuments(
  options: { department?: string; search?: string },
  signal?: AbortSignal,
): Promise<DocumentListResponse> {
  const params = new URLSearchParams()
  if (options.department) params.set('department', options.department)
  if (options.search?.trim()) params.set('search', options.search.trim())
  const query = params.size ? `?${params.toString()}` : ''
  const payload = await requestJson(`/api/documents${query}`, { signal })

  if (
    !isRecord(payload) ||
    !Array.isArray(payload.documents) ||
    typeof payload.total !== 'number' ||
    !Array.isArray(payload.departments) ||
    !payload.departments.every(
      (department): department is string => typeof department === 'string',
    )
  ) {
    throw new Error('The IronStore API returned an invalid document list.')
  }

  return {
    documents: payload.documents.map(readDocument),
    total: payload.total,
    departments: payload.departments,
  }
}

export async function askIronStore(
  question: string,
  history: HistoryMessage[],
): Promise<ChatResponse> {
  const payload = await requestJson('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, history }),
  })

  if (
    !isRecord(payload) ||
    typeof payload.answer !== 'string' ||
    !Array.isArray(payload.sources) ||
    !Array.isArray(payload.limitations) ||
    !payload.limitations.every(
      (limitation): limitation is string => typeof limitation === 'string',
    )
  ) {
    throw new Error('The IronStore API returned an invalid chat response.')
  }

  return {
    answer: payload.answer,
    sources: payload.sources.map(readSource),
    limitations: payload.limitations,
  }
}
