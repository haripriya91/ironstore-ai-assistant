import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
  type RefObject,
} from 'react'
import {
  ArrowRight,
  ArrowUpRight,
  BarChart3,
  ChevronRight,
  Clock3,
  CreditCard,
  ExternalLink,
  FileText,
  Headphones,
  Laptop,
  Layers3,
  MessageSquare,
  Plus,
  Search,
  ShieldCheck,
  Tag,
  Truck,
  Users,
  X,
} from 'lucide-react'
import ReactMarkdown, { defaultUrlTransform } from 'react-markdown'
import type { Link, Root, RootContent } from 'mdast'
import {
  askIronStore,
  fetchDocuments,
  resolveDocumentUrl,
  type DocumentRecord,
  type HistoryMessage,
  type SourceReference,
} from './api'
import './App.css'

type Screen = 'ask' | 'library' | 'conversations'
type Department = string
type SourceItem = SourceReference | DocumentRecord

type ChatMessage = {
  id: string
  role: 'user' | 'assistant'
  text: string
  timestamp: string
  sources?: SourceReference[]
  limitations?: string[]
}

type Conversation = {
  id: string
  title: string
  updatedAt: string
  messages: ChatMessage[]
}

type SavedState = {
  conversations: Conversation[]
  error: string | null
  canPersist: boolean
}

const STORAGE_KEY = 'ironstore-conversations-v1'
const CITATION_PATTERN = /\[S\d+\]/g

const suggestions = [
  'How do I request annual leave?',
  'Find TV-NDV-NQ55U7: price and warehouse.',
  'What should support verify before a refund?',
]

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isSavedSource(value: unknown): value is SourceReference {
  return (
    isRecord(value) &&
    typeof value.source_id === 'string' &&
    typeof value.chunk_id === 'string' &&
    typeof value.document_id === 'string' &&
    typeof value.title === 'string' &&
    typeof value.page === 'number' &&
    typeof value.excerpt === 'string' &&
    typeof value.url === 'string'
  )
}

function isSavedMessage(value: unknown): value is ChatMessage {
  return (
    isRecord(value) &&
    typeof value.id === 'string' &&
    (value.role === 'user' || value.role === 'assistant') &&
    typeof value.text === 'string' &&
    typeof value.timestamp === 'string' &&
    (value.sources === undefined ||
      (Array.isArray(value.sources) && value.sources.every(isSavedSource))) &&
    (value.limitations === undefined ||
      (Array.isArray(value.limitations) &&
        value.limitations.every(
          (limitation) => typeof limitation === 'string',
        )))
  )
}

function isSavedConversation(value: unknown): value is Conversation {
  return (
    isRecord(value) &&
    typeof value.id === 'string' &&
    typeof value.title === 'string' &&
    typeof value.updatedAt === 'string' &&
    Array.isArray(value.messages) &&
    value.messages.every(isSavedMessage)
  )
}

function readSavedConversations(): SavedState {
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY)
    if (!saved) return { conversations: [], error: null, canPersist: true }

    const parsed: unknown = JSON.parse(saved)
    if (!Array.isArray(parsed) || !parsed.every(isSavedConversation)) {
      return {
        conversations: [],
        error:
          'Saved conversations could not be read because their data is invalid.',
        canPersist: false,
      }
    }

    return { conversations: parsed, error: null, canPersist: true }
  } catch (error) {
    return {
      conversations: [],
      error:
        error instanceof Error
          ? `Saved conversations could not be loaded: ${error.message}`
          : 'Saved conversations could not be loaded.',
      canPersist: false,
    }
  }
}

function formatTime(value: string): string {
  const timestamp = new Date(value).getTime()
  if (!Number.isFinite(timestamp)) return ''

  const elapsed = Math.max(0, Date.now() - timestamp)
  if (elapsed < 60_000) return 'Just now'
  if (elapsed < 3_600_000) return `${Math.floor(elapsed / 60_000)}m ago`
  if (elapsed < 86_400_000) return `${Math.floor(elapsed / 3_600_000)}h ago`
  if (elapsed < 604_800_000) return `${Math.floor(elapsed / 86_400_000)}d ago`
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
  }).format(timestamp)
}

function departmentIcon(department: string): typeof Tag {
  const normalized = department.toLowerCase()
  if (normalized.includes('product')) return Tag
  if (normalized.includes('people') || normalized.includes('hr')) return Users
  if (normalized.includes('support')) return Headphones
  if (normalized.includes('sales')) return BarChart3
  if (normalized.includes('finance')) return CreditCard
  if (normalized.includes('deliver')) return Truck
  if (normalized.includes('legal') || normalized.includes('compliance')) {
    return ShieldCheck
  }
  if (normalized.includes('it')) return Laptop
  return FileText
}

function remarkCitations(options: { sourceIds: string[] }) {
  const sourceIds = new Set(options.sourceIds)

  return (tree: Root) => {
    function transform(parent: Root | RootContent) {
      if (!('children' in parent)) return

      const children: RootContent[] = []
      for (const child of parent.children) {
        if (child.type === 'text') {
          const text = child
          let previousIndex = 0
          for (const match of text.value.matchAll(CITATION_PATTERN)) {
            const citation = match[0]
            const sourceId = citation.slice(1, -1)
            const matchIndex = match.index
            if (matchIndex === undefined || !sourceIds.has(sourceId)) continue
            if (matchIndex > previousIndex) {
              children.push({
                type: 'text',
                value: text.value.slice(previousIndex, matchIndex),
              })
            }
            const link: Link = {
              type: 'link',
              url: `ironstore-citation:${sourceId}`,
              title: null,
              children: [{ type: 'text', value: citation }],
            }
            children.push(link)
            previousIndex = matchIndex + citation.length
          }
          if (previousIndex > 0) {
            if (previousIndex < text.value.length) {
              children.push({
                type: 'text',
                value: text.value.slice(previousIndex),
              })
            }
          } else {
            children.push(child)
          }
        } else {
          children.push(child)
          if (child.type !== 'link' && child.type !== 'linkReference') {
            transform(child)
          }
        }
      }
      parent.children = children
    }

    transform(tree)
  }
}

function App() {
  const [screen, setScreen] = useState<Screen>('ask')
  const [savedState] = useState<SavedState>(() => readSavedConversations())
  const [conversations, setConversations] = useState<Conversation[]>(
    savedState.conversations,
  )
  const [canPersist] = useState(savedState.canPersist)
  const [storageError, setStorageError] = useState<string | null>(savedState.error)
  const [activeConversationId, setActiveConversationId] = useState<string | null>(
    null,
  )
  const [draft, setDraft] = useState('')
  const [search, setSearch] = useState('')
  const [departmentFilter, setDepartmentFilter] = useState<Department | 'All'>(
    'All',
  )
  const [documents, setDocuments] = useState<DocumentRecord[]>([])
  const [documentDepartments, setDocumentDepartments] = useState<string[]>([])
  const [documentTotal, setDocumentTotal] = useState(0)
  const [documentsLoading, setDocumentsLoading] = useState(true)
  const [documentsError, setDocumentsError] = useState<string | null>(null)
  const [documentsRefresh, setDocumentsRefresh] = useState(0)
  const [isSending, setIsSending] = useState(false)
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null)
  const [chatError, setChatError] = useState<string | null>(null)
  const [selectedSource, setSelectedSource] = useState<SourceItem | null>(null)
  const stayOnHomeAfterRequestRef = useRef(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const activeConversation =
    conversations.find(({ id }) => id === activeConversationId) ?? null
  const messages = activeConversation?.messages ?? []

  useEffect(() => {
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      setDocumentsLoading(true)
      setDocumentsError(null)
      void fetchDocuments(
        {
          department:
            departmentFilter === 'All' ? undefined : departmentFilter,
          search,
        },
        controller.signal,
      )
        .then((result) => {
          setDocuments(result.documents)
          setDocumentTotal(result.total)
          setDocumentDepartments(result.departments)
        })
        .catch((error: unknown) => {
          if (controller.signal.aborted) return
          setDocumentsError(
            error instanceof Error
              ? error.message
              : 'Documents could not be loaded.',
          )
        })
        .finally(() => {
          if (!controller.signal.aborted) setDocumentsLoading(false)
        })
    }, search ? 220 : 0)

    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [departmentFilter, documentsRefresh, search])

  useEffect(() => {
    if (screen === 'ask') {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages.length, activeConversationId, pendingQuestion, screen])

  function startNewConversation() {
    setActiveConversationId(null)
    setDraft('')
    setChatError(null)
    setPendingQuestion(null)
    setScreen('ask')
    setSelectedSource(null)
  }

  function goHome() {
    if (isSending) stayOnHomeAfterRequestRef.current = true
    setActiveConversationId(null)
    setDraft('')
    setChatError(null)
    setPendingQuestion(null)
    setScreen('ask')
    setSelectedSource(null)
  }

  function openConversation(id: string) {
    setActiveConversationId(id)
    setChatError(null)
    setScreen('ask')
    setSelectedSource(null)
  }

  async function sendMessage(text: string) {
    const question = text.trim()
    if (!question || isSending) return

    const currentConversation =
      conversations.find(({ id }) => id === activeConversationId) ?? null
    const timestamp = new Date().toISOString()
    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      text: question,
      timestamp,
    }
    const history: HistoryMessage[] = (currentConversation?.messages ?? [])
      .slice(-6)
      .map(({ role, text: content }) => ({ role, content }))

    stayOnHomeAfterRequestRef.current = false
    setIsSending(true)
    setPendingQuestion(question)
    setChatError(null)

    try {
      const result = await askIronStore(question, history)
      const answerMessage: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        text: result.answer,
        timestamp: new Date().toISOString(),
        sources: result.sources,
        limitations: result.limitations,
      }
      const id = currentConversation?.id ?? crypto.randomUUID()
      const updatedConversation: Conversation = {
        id,
        title: currentConversation?.title ?? question,
        updatedAt: answerMessage.timestamp,
        messages: [
          ...(currentConversation?.messages ?? []),
          userMessage,
          answerMessage,
        ],
      }
      const nextConversations = [
        updatedConversation,
        ...conversations.filter((conversation) => conversation.id !== id),
      ]

      setConversations(nextConversations)
      if (canPersist) {
        try {
          window.localStorage.setItem(
            STORAGE_KEY,
            JSON.stringify(nextConversations),
          )
        } catch (error) {
          setStorageError(
            error instanceof Error
              ? `Conversations could not be saved on this device: ${error.message}`
              : 'Conversations could not be saved on this device.',
          )
        }
      }
      if (!stayOnHomeAfterRequestRef.current) {
        setActiveConversationId(id)
        setDraft('')
        setScreen('ask')
      }
    } catch (error) {
      if (!stayOnHomeAfterRequestRef.current) {
        setDraft(question)
        setChatError(
          error instanceof Error
            ? error.message
            : 'The assistant could not complete this request.',
        )
      }
    } finally {
      setIsSending(false)
      setPendingQuestion(null)
      stayOnHomeAfterRequestRef.current = false
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void sendMessage(draft)
  }

  function chooseDepartment(department: Department) {
    setDepartmentFilter(department)
    setSearch('')
    setScreen('library')
  }

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Main navigation">
        <Brand onHome={goHome} />
        <nav className="primary-nav">
          <NavButton
            active={screen === 'ask'}
            icon={<MessageSquare />}
            label="Ask"
            onClick={() => setScreen('ask')}
          />
          <NavButton
            active={screen === 'library'}
            icon={<FileText />}
            label="Knowledge library"
            onClick={() => setScreen('library')}
          />
          <NavButton
            active={screen === 'conversations'}
            icon={<Clock3 />}
            label="Conversations"
            onClick={() => setScreen('conversations')}
          />
        </nav>
        <div className="sidebar-rule" />
        <button className="new-conversation-button" onClick={startNewConversation}>
          <Plus aria-hidden="true" />
          <span>New conversation</span>
        </button>
        <div className="recent-section">
          <p className="sidebar-caption">Recent conversations</p>
          {conversations.slice(0, 4).map((conversation) => (
            <button
              className={`recent-conversation ${
                activeConversationId === conversation.id ? 'selected' : ''
              }`}
              key={conversation.id}
              onClick={() => openConversation(conversation.id)}
            >
              <span>{conversation.title}</span>
              <small>{formatTime(conversation.updatedAt)}</small>
            </button>
          ))}
          {conversations.length === 0 && (
            <p className="sidebar-empty">No saved conversations yet.</p>
          )}
        </div>
        <p className="sidebar-note">Conversations saved on this device.</p>
      </aside>

      <main className="main-column">
        <header className="mobile-header">
          <Brand compact onHome={goHome} />
          <span className="preview-badge">INTERNAL</span>
        </header>

        {(chatError || storageError) && (
          <div className="app-alert error-alert" role="alert">
            <span>{chatError ?? storageError}</span>
            {chatError && draft.trim() && (
              <button
                className="retry-button"
                disabled={isSending}
                onClick={() => void sendMessage(draft)}
              >
                Try again
              </button>
            )}
          </div>
        )}
        {isSending && (
          <div className="app-alert loading-alert" role="status">
            <span className="loading-spinner" />
            Searching company documents…
          </div>
        )}

        <div className={`screen-content screen-${screen}`}>
          {screen === 'ask' &&
            (activeConversation ? (
              <ChatView
                conversation={activeConversation}
                draft={draft}
                isSending={isSending}
                messages={messages}
                messagesEndRef={messagesEndRef}
                pendingQuestion={pendingQuestion}
                onDraftChange={setDraft}
                onNewConversation={startNewConversation}
                onOpenSource={setSelectedSource}
                onSubmit={handleSubmit}
              />
            ) : (
              <WelcomeView
                departments={documentDepartments}
                documentsError={documentsError}
                draft={draft}
                isSending={isSending}
                isLoadingDepartments={documentsLoading}
                onDraftChange={setDraft}
                onDepartment={chooseDepartment}
                onRefreshDepartments={() =>
                  setDocumentsRefresh((count) => count + 1)
                }
                onOpenLibrary={() => {
                  setDepartmentFilter('All')
                  setScreen('library')
                }}
                onSubmit={handleSubmit}
                onSuggestion={(text) => void sendMessage(text)}
              />
            ))}

          {screen === 'library' && (
            <LibraryView
              departmentFilter={departmentFilter}
              departments={documentDepartments}
              documents={documents}
              documentsError={documentsError}
              documentsLoading={documentsLoading}
              documentTotal={documentTotal}
              onDepartmentFilter={setDepartmentFilter}
              onOpenSource={setSelectedSource}
              onRefresh={() => setDocumentsRefresh((count) => count + 1)}
              onSearch={setSearch}
              search={search}
            />
          )}

          {screen === 'conversations' && (
            <ConversationsView
              conversations={conversations}
              onNewConversation={startNewConversation}
              onOpenConversation={openConversation}
            />
          )}
        </div>

        <nav className="mobile-nav" aria-label="Mobile navigation">
          <MobileNavButton
            active={screen === 'ask'}
            icon={<MessageSquare />}
            label="Ask"
            onClick={() => setScreen('ask')}
          />
          <MobileNavButton
            active={screen === 'library'}
            icon={<FileText />}
            label="Library"
            onClick={() => setScreen('library')}
          />
          <MobileNavButton
            active={screen === 'conversations'}
            icon={<Clock3 />}
            label="History"
            onClick={() => setScreen('conversations')}
          />
        </nav>
      </main>

      {selectedSource && (
        <SourceDetails
          source={selectedSource}
          onClose={() => setSelectedSource(null)}
        />
      )}
    </div>
  )
}

function Brand({
  compact = false,
  onHome,
}: {
  compact?: boolean
  onHome: () => void
}) {
  return (
    <button
      className={`brand brand-control ${compact ? 'brand-compact' : ''}`}
      type="button"
      aria-label="IronStore home"
      title="Home"
      onClick={onHome}
    >
      <span className="brand-mark" aria-hidden="true">
        <Layers3 />
      </span>
      <span className="brand-name">IronStore</span>
      {!compact && <span className="preview-badge">INTERNAL</span>}
    </button>
  )
}

function NavButton({
  active,
  icon,
  label,
  onClick,
}: {
  active: boolean
  icon: ReactNode
  label: string
  onClick: () => void
}) {
  return (
    <button
      className={`nav-button ${active ? 'active' : ''}`}
      onClick={onClick}
      aria-current={active ? 'page' : undefined}
    >
      {icon}
      <span>{label}</span>
    </button>
  )
}

function MobileNavButton({
  active,
  icon,
  label,
  onClick,
}: {
  active: boolean
  icon: ReactNode
  label: string
  onClick: () => void
}) {
  return (
    <button
      className={`mobile-nav-button ${active ? 'active' : ''}`}
      onClick={onClick}
      aria-current={active ? 'page' : undefined}
    >
      {icon}
      <span>{label}</span>
    </button>
  )
}

function MessageComposer({
  draft,
  onDraftChange,
  onSubmit,
  disabled = false,
  compact = false,
}: {
  draft: string
  onDraftChange: (value: string) => void
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
  disabled?: boolean
  compact?: boolean
}) {
  return (
    <div className={`composer-wrap ${compact ? 'composer-compact' : ''}`}>
      <form className="message-composer" onSubmit={onSubmit}>
        <textarea
          aria-label="Ask IronStore a question"
          rows={compact ? 1 : 2}
          maxLength={4000}
          placeholder="Ask a question or enter a product SKU..."
          value={draft}
          disabled={disabled}
          onChange={(event) => onDraftChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              event.currentTarget.form?.requestSubmit()
            }
          }}
        />
        <button
          className="send-button"
          type="submit"
          aria-label="Send message"
          disabled={disabled || !draft.trim()}
        >
          <ArrowRight />
        </button>
      </form>
      <p className="composer-hint">Enter to send · Shift+Enter for a new line</p>
    </div>
  )
}

function WelcomeView({
  departments,
  documentsError,
  draft,
  isSending,
  isLoadingDepartments,
  onDraftChange,
  onDepartment,
  onOpenLibrary,
  onRefreshDepartments,
  onSubmit,
  onSuggestion,
}: {
  departments: string[]
  draft: string
  isSending: boolean
  isLoadingDepartments: boolean
  documentsError: string | null
  onDraftChange: (value: string) => void
  onDepartment: (department: Department) => void
  onRefreshDepartments: () => void
  onOpenLibrary: () => void
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
  onSuggestion: (text: string) => void
}) {
  return (
    <section className="welcome-view">
      <div className="welcome-content">
        <div className="welcome-emblem" aria-hidden="true">
          <Layers3 />
        </div>
        <h1>Ask IronStore</h1>
        <p className="welcome-subtitle">
          Find product details, policies and procedures—with sources.
        </p>

        <MessageComposer
          draft={draft}
          disabled={isSending}
          onDraftChange={onDraftChange}
          onSubmit={onSubmit}
        />

        <section className="welcome-section">
          <h2>Try asking</h2>
          <div className="suggestion-list">
            {suggestions.map((suggestion) => (
              <button
                className="suggestion-button"
                key={suggestion}
                disabled={isSending}
                onClick={() => onSuggestion(suggestion)}
              >
                <span>{suggestion}</span>
                <ArrowRight aria-hidden="true" />
              </button>
            ))}
          </div>
        </section>

        <section className="welcome-section department-section">
          <h2>Browse by department</h2>
          {departments.length ? (
            <div className="department-grid">
              {departments.map((name) => {
                const Icon = departmentIcon(name)
                return (
                  <button
                    className="department-button"
                    key={name}
                    onClick={() => onDepartment(name)}
                  >
                    <Icon aria-hidden="true" />
                    <span>{name}</span>
                  </button>
                )
              })}
            </div>
          ) : (
            <div className="department-status">
              <span>
                {isLoadingDepartments
                  ? 'Loading departments…'
                  : documentsError ?? 'No departments are currently available.'}
              </span>
              {documentsError && (
                <button className="retry-button" onClick={onRefreshDepartments}>
                  Try again
                </button>
              )}
            </div>
          )}
        </section>

        <button className="library-link" onClick={onOpenLibrary}>
          <FileText aria-hidden="true" />
          <span>Browse source documents in the library</span>
          <ArrowRight aria-hidden="true" />
        </button>
        <p className="welcome-footnote">
          Answers are grounded in company documents. Verify important details.
        </p>
      </div>
    </section>
  )
}

function ChatView({
  conversation,
  draft,
  isSending,
  messages,
  messagesEndRef,
  pendingQuestion,
  onDraftChange,
  onNewConversation,
  onOpenSource,
  onSubmit,
}: {
  conversation: Conversation
  draft: string
  isSending: boolean
  messages: ChatMessage[]
  messagesEndRef: RefObject<HTMLDivElement | null>
  pendingQuestion: string | null
  onDraftChange: (value: string) => void
  onNewConversation: () => void
  onOpenSource: (source: SourceItem) => void
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
}) {
  return (
    <section className="chat-view">
      <header className="chat-header">
        <div>
          <p className="eyebrow">IRONSTORE KNOWLEDGE ASSISTANT</p>
          <h1>{conversation.title}</h1>
        </div>
        <button className="outline-button" onClick={onNewConversation}>
          <Plus aria-hidden="true" />
          <span>New conversation</span>
        </button>
      </header>
      <div className="chat-messages">
        <div className="message-list">
          {messages.map((message) => (
            <article
              className={`message-row ${message.role}`}
              key={message.id}
            >
              {message.role === 'assistant' && (
                <span className="assistant-avatar" aria-hidden="true">
                  <Layers3 />
                </span>
              )}
              <div className="message-body">
                <div className="message-bubble">
                  {message.role === 'assistant' ? (
                    <ReactMarkdown
                      remarkPlugins={[
                        [remarkCitations, {
                          sourceIds: (message.sources ?? []).map(
                            ({ source_id }) => source_id,
                          ),
                        }],
                      ]}
                      urlTransform={(url) =>
                        url.startsWith('ironstore-citation:')
                          ? url
                          : defaultUrlTransform(url)
                      }
                      components={{
                        a: ({ href, children }) => {
                          const source = message.sources?.find(
                            ({ source_id }) =>
                              href === `ironstore-citation:${source_id}`,
                          )
                          return source ? (
                            <button
                              className="citation-link"
                              onClick={() => onOpenSource(source)}
                            >
                              {children}
                            </button>
                          ) : (
                            <a href={href}>{children}</a>
                          )
                        },
                      }}
                    >
                      {message.text}
                    </ReactMarkdown>
                  ) : (
                    <p>{message.text}</p>
                  )}
                  {message.sources?.map((source) => (
                    <button
                      className="source-chip"
                      key={source.source_id}
                      onClick={() => onOpenSource(source)}
                    >
                      <FileText aria-hidden="true" />
                      <span>
                        <strong>{source.source_id}</strong>
                        {source.title} · Page {source.page}
                      </span>
                      <ChevronRight aria-hidden="true" />
                    </button>
                  ))}
                  {message.limitations?.map((limitation) => (
                    <p className="answer-limitation" key={limitation}>
                      {limitation}
                    </p>
                  ))}
                </div>
                <time className="message-time">
                  {new Intl.DateTimeFormat(undefined, {
                    hour: 'numeric',
                    minute: '2-digit',
                  }).format(new Date(message.timestamp))}
                </time>
              </div>
            </article>
          ))}
          {isSending && pendingQuestion && (
            <>
              <article className="message-row user">
                <div className="message-body">
                  <div className="message-bubble">
                    <p>{pendingQuestion}</p>
                  </div>
                </div>
              </article>
              <article className="message-row assistant">
                <span className="assistant-avatar" aria-hidden="true">
                  <Layers3 />
                </span>
                <div className="message-body">
                  <div className="message-bubble typing-bubble" role="status">
                    <span className="loading-spinner" />
                    Searching company documents…
                  </div>
                </div>
              </article>
            </>
          )}
          <div ref={messagesEndRef} />
        </div>
      </div>
      <MessageComposer
        compact
        draft={draft}
        disabled={isSending}
        onDraftChange={onDraftChange}
        onSubmit={onSubmit}
      />
    </section>
  )
}

function LibraryView({
  departmentFilter,
  departments,
  documents,
  documentsError,
  documentsLoading,
  documentTotal,
  onDepartmentFilter,
  onOpenSource,
  onRefresh,
  onSearch,
  search,
}: {
  departmentFilter: Department | 'All'
  departments: string[]
  documents: DocumentRecord[]
  documentsError: string | null
  documentsLoading: boolean
  documentTotal: number
  onDepartmentFilter: (department: Department | 'All') => void
  onOpenSource: (source: SourceItem) => void
  onRefresh: () => void
  onSearch: (value: string) => void
  search: string
}) {
  return (
    <section className="standard-view">
      <div className="page-heading">
        <div>
          <p className="eyebrow">COMPANY KNOWLEDGE</p>
          <h1>Knowledge library</h1>
          <p>Browse the documents that power IronStore answers.</p>
        </div>
      </div>
      <label className="library-search">
        <Search aria-hidden="true" />
        <input
          value={search}
          maxLength={200}
          onChange={(event) => onSearch(event.target.value)}
          placeholder="Search documents"
          aria-label="Search documents"
        />
        {search && (
          <button
            type="button"
            className="clear-search"
            onClick={() => onSearch('')}
            aria-label="Clear search"
          >
            <X />
          </button>
        )}
      </label>
      <div className="filter-row" aria-label="Filter by department">
        {['All', ...departments].map((department) => (
          <button
            className={`filter-chip ${
              departmentFilter === department ? 'active' : ''
            }`}
            key={department}
            onClick={() => onDepartmentFilter(department)}
          >
            {department}
          </button>
        ))}
      </div>
      <div className="library-results-heading">
        <h2>Source documents</h2>
        <span>
          {documentsLoading ? 'Loading…' : `${documentTotal} documents`}
        </span>
      </div>
      {documentsError ? (
        <div className="inline-error" role="alert">
          <p>{documentsError}</p>
          <button className="retry-button" onClick={onRefresh}>
            Try again
          </button>
        </div>
      ) : documentsLoading && documents.length === 0 ? (
        <div className="empty-state" role="status">
          <span className="loading-spinner" />
          <p>Loading source documents…</p>
        </div>
      ) : documents.length ? (
        <div className="document-grid" aria-busy={documentsLoading}>
          {documents.map((document) => (
            <button
              className="document-card"
              key={document.document_id}
              onClick={() => onOpenSource(document)}
            >
              <span className="document-icon">
                <FileText aria-hidden="true" />
              </span>
              <span className="document-info">
                <strong>{document.title}</strong>
                <small>
                  {document.department} <span>·</span> {document.category}
                </small>
              </span>
              <ArrowUpRight className="document-open" aria-hidden="true" />
            </button>
          ))}
        </div>
      ) : documentsLoading ? (
        <div className="empty-state" role="status">
          <span className="loading-spinner" />
          <p>Loading source documents…</p>
        </div>
      ) : (
        <div className="empty-state">
          <Search aria-hidden="true" />
          <h2>No documents found</h2>
          <p>Try a different search or department.</p>
        </div>
      )}
    </section>
  )
}

function ConversationsView({
  conversations,
  onNewConversation,
  onOpenConversation,
}: {
  conversations: Conversation[]
  onNewConversation: () => void
  onOpenConversation: (id: string) => void
}) {
  return (
    <section className="standard-view">
      <div className="page-heading">
        <div>
          <p className="eyebrow">SAVED ON THIS DEVICE</p>
          <h1>Conversations</h1>
          <p>Pick up where you left off.</p>
        </div>
        <button
          className="new-conversation-button page-new-button"
          onClick={onNewConversation}
        >
          <Plus aria-hidden="true" />
          <span>New conversation</span>
        </button>
      </div>
      {conversations.length ? (
        <div className="conversation-list">
          {conversations.map((conversation) => (
            <button
              className="conversation-card"
              key={conversation.id}
              onClick={() => onOpenConversation(conversation.id)}
            >
              <span className="conversation-card-icon">
                <MessageSquare aria-hidden="true" />
              </span>
              <span className="conversation-card-copy">
                <strong>{conversation.title}</strong>
                <small>
                  {conversation.messages.length} messages
                  <span>·</span>
                  {formatTime(conversation.updatedAt)}
                </small>
              </span>
              <ChevronRight aria-hidden="true" />
            </button>
          ))}
        </div>
      ) : (
        <div className="empty-state conversation-empty">
          <MessageSquare aria-hidden="true" />
          <h2>No conversations yet</h2>
          <p>Ask a question to start a conversation.</p>
        </div>
      )}
    </section>
  )
}

function SourceDetails({
  source,
  onClose,
}: {
  source: SourceItem
  onClose: () => void
}) {
  const dialogRef = useRef<HTMLElement>(null)
  const closeButtonRef = useRef<HTMLButtonElement>(null)
  const isCitation = 'source_id' in source
  const page = isCitation ? source.page : undefined
  const excerpt = isCitation ? source.excerpt : undefined
  const category = isCitation ? undefined : source.category
  const department = isCitation ? undefined : source.department

  useLayoutEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return

    const opener =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null
    const scrollContainer =
      document.querySelector<HTMLElement>('.screen-content')
    const previousBodyOverflow = document.body.style.overflow
    const previousContainerOverflow = scrollContainer?.style.overflow

    document.body.style.overflow = 'hidden'
    if (scrollContainer) scrollContainer.style.overflow = 'hidden'
    closeButtonRef.current?.focus()

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
        return
      }

      if (event.key !== 'Tab' || !dialog) return
      const focusable = Array.from(
        dialog.querySelectorAll<HTMLElement>(
          'button:not(:disabled), a[href], [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((element) => element.getClientRects().length > 0)
      const first = focusable[0]
      const last = focusable.at(-1)

      if (!first || !last) {
        event.preventDefault()
        closeButtonRef.current?.focus()
      } else if (
        event.shiftKey &&
        (document.activeElement === first ||
          !dialog.contains(document.activeElement))
      ) {
        event.preventDefault()
        last.focus()
      } else if (
        !event.shiftKey &&
        (document.activeElement === last ||
          !dialog.contains(document.activeElement))
      ) {
        event.preventDefault()
        first.focus()
      }
    }

    function onFocusIn(event: FocusEvent) {
      if (
        event.target instanceof Node &&
        !dialog?.contains(event.target)
      ) {
        closeButtonRef.current?.focus()
      }
    }

    document.addEventListener('keydown', onKeyDown)
    document.addEventListener('focusin', onFocusIn)

    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.removeEventListener('focusin', onFocusIn)
      document.body.style.overflow = previousBodyOverflow
      if (scrollContainer && previousContainerOverflow !== undefined) {
        scrollContainer.style.overflow = previousContainerOverflow
      }
      if (opener?.isConnected) opener.focus()
    }
  }, [onClose])

  return (
    <div
      className="source-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <section
        ref={dialogRef}
        className="source-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="source-title"
      >
        <div className="source-handle" />
        <header className="source-panel-heading">
          <div className="source-heading-copy">
            <p className="eyebrow">
              {isCitation ? `SOURCE ${source.source_id}` : 'DOCUMENT DETAILS'}
            </p>
            <h2 id="source-title">{source.title}</h2>
            <div className="source-document">
              <span className="pdf-icon">PDF</span>
              <span>
                <small>
                  {page ? `Page ${page}` : 'Document'}
                  {department && ` · ${department}`}
                  {category && ` · ${category}`}
                </small>
              </span>
            </div>
          </div>
          <button
            ref={closeButtonRef}
            className="icon-button source-close-control"
            onClick={onClose}
            aria-label="Close source details"
          >
            <X />
          </button>
        </header>
        <div className="source-panel-body" tabIndex={0} aria-label="Source details">
          {excerpt ? (
            <div className="source-excerpt">
              <p>{excerpt}</p>
            </div>
          ) : (
            <p className="source-no-excerpt">
              Open the PDF to view this document.
            </p>
          )}
        </div>
        <footer className="source-panel-footer">
          <a
            className="source-close-button"
            href={resolveDocumentUrl(source.url)}
            target="_blank"
            rel="noreferrer"
          >
            <ExternalLink aria-hidden="true" />
            Open PDF{page ? ` · Page ${page}` : ''}
          </a>
        </footer>
      </section>
    </div>
  )
}

export default App
