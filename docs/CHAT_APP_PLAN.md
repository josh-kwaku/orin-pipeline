# Orin Chat App - Architecture Plan

Last Updated: 2026-01-14

## Overview

A messaging app where music snippets are a first-class communication medium. Users can send song snippets as responses in conversations, with AI recommending the perfect snippet based on conversational context.

**Core insight**: "People already have musical feelings, they just don't have a frictionless way to express them in conversation."

---

## Repositories

```
~/personal/
├── orin-pipeline/      # Existing - processes songs into snippets
├── orin-chat-web/      # NEW - React frontend (mobile-first)
└── orin-chat-api/      # NEW - Node.js/Express/TypeScript backend
```

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| Frontend | React + TypeScript + Vite | Mobile-first web app |
| Styling | Tailwind CSS | Utility-first, rapid iteration |
| Backend | Node.js + Express + TypeScript | Snippet recommendation API |
| Auth | Supabase Auth | Phone number verification |
| Database | Supabase (PostgreSQL) | Users, conversations, messages |
| Realtime | Supabase Realtime | Live message delivery |
| Vector DB | Qdrant (existing) | Snippet similarity search |
| Storage | Cloudflare R2 (existing) | Audio snippet files |
| In-browser LLM | WebLLM or Transformers.js | Context → description (TBD) |

---

## Privacy Architecture

**Principle**: Raw conversation content never leaves the user's device/browser.

```
┌─────────────────────────────────────────────────────────────┐
│  BROWSER (User's Device)                                    │
│                                                             │
│  1. Read last k messages from local state                   │
│  2. Run small LLM locally: messages → natural language      │
│     description of emotional context                        │
│  3. Encrypt description (AES-256-GCM with ephemeral key)    │
│  4. Send only encrypted description to server               │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  SERVER                                                     │
│                                                             │
│  1. Decrypt description (never stored, processed in memory) │
│  2. Generate embedding (BGE-M3)                             │
│  3. Query Qdrant for similar snippets                       │
│  4. Return snippet metadata + R2 URLs                       │
│  5. Discard description immediately                         │
└─────────────────────────────────────────────────────────────┘
```

**V1 Simplification**: For initial testing, we may use HTTPS transport encryption only (no E2E encryption of descriptions). Add proper encryption before any public release.

---

## Database Schema (Supabase)

### users
```sql
CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  phone TEXT UNIQUE NOT NULL,
  display_name TEXT,
  avatar_url TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### conversations
```sql
CREATE TABLE conversations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### conversation_participants
```sql
CREATE TABLE conversation_participants (
  conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  joined_at TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (conversation_id, user_id)
);
```

### messages
```sql
CREATE TABLE messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
  sender_id UUID REFERENCES users(id) ON DELETE SET NULL,

  -- Message content (one of these will be set)
  text_content TEXT,                    -- Plain text message
  snippet_id TEXT,                      -- Reference to snippet in Qdrant
  snippet_r2_url TEXT,                  -- R2 audio URL
  snippet_lyrics TEXT,                  -- Lyrics excerpt for display
  snippet_artist TEXT,
  snippet_title TEXT,
  caption TEXT,                         -- Optional caption with snippet

  created_at TIMESTAMPTZ DEFAULT NOW(),

  -- Indexes
  INDEX idx_messages_conversation (conversation_id, created_at DESC)
);
```

### contacts (for sharing externally)
```sql
CREATE TABLE contacts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  phone TEXT NOT NULL,
  name TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id, phone)
);
```

---

## API Endpoints (orin-chat-api)

### Health
```
GET /api/health
```

### Snippets (Core functionality)
```
POST /api/snippets/recommend
Body: { encrypted_description: string, genre_filter?: string[] }
Response: { snippets: Snippet[] }  // 3-5 recommendations

POST /api/snippets/search
Body: { query: string, type: 'text' | 'voice' }
Response: { snippets: Snippet[] }

GET /api/snippets/:id
Response: { snippet: Snippet }
```

### Snippet Type
```typescript
interface Snippet {
  id: string;
  artist: string;
  title: string;
  lyrics: string;           // The lyric segment
  genre: string;
  r2_url: string;           // Audio URL
  duration_ms: number;
  score: number;            // Similarity score
}
```

---

## Frontend Structure (orin-chat-web)

```
src/
├── main.tsx
├── App.tsx
├── index.css                    # Tailwind imports
│
├── components/
│   ├── ui/                      # Reusable primitives
│   │   ├── Button.tsx
│   │   ├── Input.tsx
│   │   └── Waveform.tsx         # Audio visualization
│   │
│   ├── chat/
│   │   ├── ChatList.tsx         # Conversation list
│   │   ├── ChatView.tsx         # Single conversation
│   │   ├── MessageBubble.tsx    # Text or snippet message
│   │   ├── SnippetBubble.tsx    # Snippet-specific rendering
│   │   ├── MessageInput.tsx     # Text input + snippet button
│   │   └── SnippetPicker.tsx    # The magic 🎵 experience
│   │
│   └── auth/
│       └── PhoneAuth.tsx
│
├── pages/
│   ├── Login.tsx
│   ├── Chats.tsx                # Chat list view
│   ├── Conversation.tsx         # Single chat view
│   └── NewChat.tsx              # Start new conversation
│
├── hooks/
│   ├── useAuth.ts
│   ├── useConversation.ts
│   ├── useMessages.ts
│   ├── useSnippetRecommendation.ts
│   └── useAudioPlayer.ts
│
├── lib/
│   ├── supabase.ts              # Supabase client
│   ├── api.ts                   # orin-chat-api client
│   ├── contextAnalyzer.ts       # Browser LLM integration
│   └── encryption.ts            # Description encryption
│
├── stores/
│   └── chatStore.ts             # Zustand for local state
│
└── types/
    └── index.ts
```

---

## User Flows

### Flow 1: Send a Snippet
```
1. User is in conversation, taps 🎵 button
2. SnippetPicker slides up (keyboard slides down on mobile)
3. Browser analyzes last k messages with local LLM
4. Generates description: "User seems nostalgic, talking about old memories with friend"
5. Description encrypted, sent to API
6. API embeds, queries Qdrant, returns 3-5 snippets
7. Top recommendation shown prominently, others below
8. Audio auto-previews as user focuses each snippet
9. User taps to select, optionally adds caption
10. Message sent via Supabase Realtime
11. Snippet floats into chat with satisfying animation
```

### Flow 2: Receive a Snippet
```
1. Realtime subscription receives new message
2. SnippetBubble renders with waveform visualization
3. Lyrics displayed prominently
4. Tap to play audio (or auto-play once, softly)
5. Lyrics animate in sync with playback
```

### Flow 3: Manual Search
```
1. User taps search icon in SnippetPicker
2. Text input or voice recording button
3. Query sent to /api/snippets/search
4. Results displayed same as AI recommendations
5. User selects and sends
```

---

## Implementation Phases

### Phase 1: Foundation (Current)
- [ ] Create orin-chat-web repo with Vite + React + TypeScript + Tailwind
- [ ] Create orin-chat-api repo with Express + TypeScript
- [ ] Set up Supabase project (auth + database)
- [ ] Basic Express API structure with health endpoint
- [ ] Basic React app with routing

### Phase 2: Auth & Chat Core
- [ ] Phone number auth flow (Supabase)
- [ ] Chat list page (fetch user's conversations)
- [ ] Conversation page (message list + input)
- [ ] Real-time messaging (text only)
- [ ] Message persistence to Supabase

### Phase 3: Snippet Sending (The Magic)
- [ ] SnippetPicker component and animation
- [ ] Browser LLM integration (context → description)
- [ ] API: /snippets/recommend endpoint
- [ ] Connect API to existing Qdrant instance
- [ ] Display 3-5 recommendations with audio preview
- [ ] Send snippet message (with optional caption)

### Phase 4: Receiving & Polish
- [ ] SnippetBubble with waveform visualization
- [ ] Audio playback with lyrics sync
- [ ] Manual search (text + voice)
- [ ] Share snippets externally
- [ ] Empty state / new conversation UX
- [ ] Animations and micro-interactions

### Phase 5: Pre-launch Polish
- [ ] Description encryption (E2E)
- [ ] Error handling and edge cases
- [ ] Loading states and skeletons
- [ ] Responsive design testing
- [ ] Performance optimization

---

## Mobile-First Design Principles

1. **Touch targets**: Minimum 44x44px for all interactive elements
2. **Thumb zone**: Primary actions in bottom half of screen
3. **Gestures**: Swipe to navigate, long-press for options
4. **Viewport**: Design for 375px width (iPhone SE), scale up
5. **Safe areas**: Account for notches and home indicators
6. **Keyboard handling**: Smooth input focus transitions

---

## Open Questions

1. **In-browser LLM**: Which library? WebLLM (WebGPU) vs Transformers.js?
   - Need to test performance on mid-range devices
   - Fallback if WebGPU not available?

2. **Audio format**: MP3 vs AAC vs Opus for R2 snippets?
   - Need good browser compatibility + small file size

3. **Waveform visualization**: Pre-generate on pipeline or compute client-side?
   - Pre-generate is faster, but adds to R2 storage

4. **Message sync**: How many messages to fetch on conversation open?
   - Pagination strategy for long conversations

---

## Related Files

- `orin-pipeline/` - Source of snippet data (Qdrant + R2)
- `docs/API_PLAN.md` - Pipeline API (separate from chat API)
- `DECISIONS.md` - Technical decisions log
