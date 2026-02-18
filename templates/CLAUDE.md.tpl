# CLAUDE.md — Project Contract

**Purpose**: Follow this in every session for this repo. Keep memory sharp. Keep outputs concrete. Cut rework.

## 🧠 Project Memory (Chroma)
Use server `chroma`. Collection `${PROJECT_COLLECTION}`.

Log after any confirmed fix, decision, gotcha, or preference.

**Schema:**
- **documents**: 1–2 sentences. Under 300 chars.
- **metadatas**: `{ "type":"decision|fix|tip|preference", "tags":"comma,separated", "source":"file|PR|spec|issue" }`
- **ids**: stable string if updating the same fact.

### Chroma Calls
```javascript
// Create once:
mcp__chroma__chroma_create_collection { "collection_name": "${PROJECT_COLLECTION}" }

// Add:
mcp__chroma__chroma_add_documents {
  "collection_name": "${PROJECT_COLLECTION}",
  "documents": ["<text>"],
  "metadatas": [{"type":"<type>","tags":"a,b,c","source":"<src>"}],
  "ids": ["<stable-id>"]
}

// Query (start with 5; escalate only if <3 strong hits):
mcp__chroma__chroma_query_documents {
  "collection_name": "${PROJECT_COLLECTION}",
  "query_texts": ["<query>"],
  "n_results": 5
}
```

## 🔍 Retrieval Checklist Before Coding
1. Query Chroma for related memories.
2. Check repo files that match the task.
3. List open PRs or issues that touch the same area.
4. Only then propose changes.

## ⚡ Activation
Read this file at session start.
Then read `.chroma/context/*.md` (titles + first bullets) and list which ones you used.
Run `bin/chroma-stats.py` and announce: **Contract loaded. Using Chroma ${PROJECT_COLLECTION}. Found [N] memories (by type ...).**

## 🧹 Session Hygiene
Prune to last 20 turns if context gets heavy. Save long outputs in `./backups/` and echo paths.

## 📁 Output Policy
For code, return unified diff or patchable files. For scripts, include exact commands and paths.

## 🛡️ Safety
No secrets in `.chroma` or transcripts. Respect rate limits. Propose batching if needed.