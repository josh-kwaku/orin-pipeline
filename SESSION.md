# Current Session: Orin Chat App Setup

Last Updated: 2026-01-14

## Active Work
- Created scaffolding for Orin Chat - the music messaging app
- Two new repos created locally (need manual git remote setup)

## New Repos Created

### /home/user/orin-chat-api
Node.js/Express/TypeScript backend:
- `POST /api/v1/snippets/recommend` - AI recommendations from encrypted context
- `POST /api/v1/snippets/search` - Manual search
- `GET /health` - Health check
- AES-256-GCM encryption for privacy
- Qdrant integration for vector search
- Together.ai for embeddings

### /home/user/orin-chat-web
React/Vite/TypeScript frontend (mobile-first):
- Phone auth via Supabase
- Real-time messaging via Supabase Realtime
- AI snippet picker with recommendations
- Manual search by lyrics/mood/feeling
- Waveform audio visualization
- Dark theme with purple accent

## Files Created

### orin-chat-api/
- `src/index.ts` - Express app entry
- `src/config/env.ts` - Environment config with Zod validation
- `src/routes/snippets.ts` - Recommendation and search endpoints
- `src/services/qdrant.ts` - Vector search
- `src/services/embedder.ts` - Embedding generation
- `src/services/crypto.ts` - AES-256-GCM decryption
- `SUPABASE_SETUP.md` - Full Supabase setup guide

### orin-chat-web/
- `src/App.tsx` - Routes and auth protection
- `src/pages/Auth.tsx` - Phone number login
- `src/pages/Conversations.tsx` - Chat list
- `src/pages/Chat.tsx` - Chat view with snippet picker
- `src/components/SnippetPicker.tsx` - AI recommendations + search
- `src/components/SnippetCard.tsx` - Snippet preview with audio
- `src/components/ChatBubble.tsx` - Message rendering
- `src/components/Waveform.tsx` - Audio visualization
- `src/stores/auth.ts` - Zustand auth store
- `src/stores/chat.ts` - Zustand chat store
- `src/lib/crypto.ts` - Client-side encryption

## Next Steps
1. User needs to create GitHub repos and push code
2. Create Supabase project (follow SUPABASE_SETUP.md)
3. Generate encryption key for both .env files
4. Install dependencies: `npm install` in both repos
5. Test locally: `npm run dev` in both repos

## Architecture Decisions
- Separate repos for frontend and backend (user requested)
- Privacy: LLM context description encrypted before sending
- Supabase for auth + realtime (phone auth)
- Together.ai for BGE-M3 embeddings (matches pipeline)
- Mobile-first design with Tailwind CSS
