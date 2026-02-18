# ChromaDB Initialization

## Automatic Setup
When you start Claude in this project:
1. Claude reads CLAUDE.md
2. Checks if ChromaDB collection exists
3. Creates collection if needed
4. Starts logging memories

## Starting Claude
```bash
# From project directory:
claude

# Or use the launcher:
./start-claude-chroma.sh
```

## Manual Commands (if needed)

### Create Collection
```javascript
mcp__chroma__chroma_create_collection { "collection_name": "${PROJECT_COLLECTION}" }
```

### Test Collection
```javascript
mcp__chroma__chroma_query_documents {
  "collection_name": "${PROJECT_COLLECTION}",
  "query_texts": ["test"],
  "n_results": 5
}
```

### Add Memory
```javascript
mcp__chroma__chroma_add_documents {
  "collection_name": "${PROJECT_COLLECTION}",
  "documents": ["Your memory text here"],
  "metadatas": [{
    "type": "tip",
    "tags": "relevant,tags",
    "source": "manual",
    "confidence": 0.8
  }],
  "ids": ["unique-id-001"]
}
```

## Troubleshooting

### MCP server not found
- Ensure .mcp.json exists in project root
- Start Claude from the project directory
- Check: `cat .mcp.json | jq .`

### Collection errors
- Verify ChromaDB directory exists: `ls -la .chroma/`
- Try recreating collection with command above

### Memory not persisting
- Check collection name matches: "${PROJECT_COLLECTION}"
- Verify metadata format is correct
- Ensure unique IDs for each memory