# 📝 MEMORY CHECKPOINT REMINDER

**IMPORTANT**: Your global CLAUDE.md may not have memory checkpoint rules.
This local reminder ensures you maintain memory discipline in this project.

## Memory Checkpoint Rules

**Every 5 interactions or after completing a task**, pause and check:
- Did I discover new decisions, fixes, or patterns?
- Did the user express any preferences?
- Did I solve tricky problems or learn about architecture?

If yes → Log memory IMMEDIATELY:
```javascript
mcp__chroma__chroma_add_documents {
  "collection_name": "${PROJECT_COLLECTION}",
  "documents": ["<discovery under 300 chars>"],
  "metadatas": [{"type":"decision|fix|tip|preference","tags":"relevant,tags","source":"file"}],
  "ids": ["<unique-id>"]
}
```

**During long sessions (>10 interactions)**:
- Stop and review: Have I logged recent learnings?
- Check for unrecorded decisions or fixes
- Remember: Each memory helps future sessions

## At Session Start

Always query existing memories first:
```javascript
mcp__chroma__chroma_query_documents {
  "collection_name": "${PROJECT_COLLECTION}",
  "query_texts": ["project decisions preferences fixes patterns"],
  "n_results": 5  // raise to 10 only if <3 strong hits
}
```

---
*This file was created because memory checkpoint rules were not detected in global CLAUDE.md*
*To add them globally (optional): Add the rules to ~/.claude/CLAUDE.md manually*