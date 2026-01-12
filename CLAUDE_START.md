# Claude Session Startup Guide

**User: Tell Claude to read this file at the start of each session**

---

## Instructions for Claude

You are continuing work on the Orin music pipeline project. Follow these steps to rebuild context:

### Step 1: Read Context Files (in order)

Read these files to understand the current state:

1. **PROGRESS.md** - What's completed, in progress, and next up
2. **DECISIONS.md** - Recent technical decisions (read last 5-10 entries)
3. **ISSUES.md** - Known bugs and gotchas
4. **SESSION.md** - What was worked on last (if exists, may be empty)
5. **README.md** - Quick project overview (optional, if you need setup info)

**Total reading time: <30 seconds**

### Step 2: Understand User's Request

The user will tell you what they want to work on. Ask clarifying questions if needed.

### Step 3: Update SESSION.md

Create or update `SESSION.md` with:

```markdown
# Current Session: [Brief title of what you're working on]

Last Updated: YYYY-MM-DD

## Active Work
- [What feature/fix you're implementing]
- [Current focus]

## Files Modified
- [List files as you change them]

## Recent Changes
- [Bullet points of changes made]

## Next Steps
- [Immediate next 1-3 tasks]

## Context Notes
- [Important decisions or discoveries this session]
```

### Step 4: Work on the Task

As you work:

- **Update SESSION.md** whenever you modify files or make decisions
- **Keep it current** - it's your working memory
- **Be concise** - bullet points, not essays

### Step 5: Maintain Other Files (During Session)

**DECISIONS.md**: Add entry when you make a significant technical choice
```markdown
## YYYY-MM-DD: [Decision Title]

**Context:** [Why this came up]
**Decision:** [What you decided]
**Files:** [Which files changed]

**Rationale:**
- [Why this approach]
- [What alternatives you considered]

**Implementation:**
- [Key details]
```

**ISSUES.md**: Add bugs or gotchas as discovered
```markdown
### Issue Title
**Severity:** Low/Medium/High
**Impact:** [What breaks]
**Files:** [Where the issue is]
**Workaround:** [Temporary fix]
```

**PROGRESS.md**: Don't update during session - only at the end

### Step 6: End of Session (User will prompt)

When user says to wrap up:

1. **Archive SESSION.md**:
   ```bash
   mv SESSION.md sessions/YYYY-MM-DD.md
   ```

2. **Update PROGRESS.md** - Move completed items from "In Progress" to "Completed"

3. **Commit to git**:
   ```bash
   git add *.md sessions/
   git commit -m "Session: [brief summary]"
   ```

---

## Key Principles

### Do:
- ✓ Update SESSION.md continuously
- ✓ Document significant decisions in DECISIONS.md
- ✓ Keep files under size limits (200-500 lines)
- ✓ Use bullet points, not paragraphs
- ✓ Be specific with file paths and line numbers

### Don't:
- ✗ Over-document trivial changes
- ✗ Duplicate info across files
- ✗ Write essays - be concise
- ✗ Update PROGRESS.md during session (only at end)
- ✗ Forget to update SESSION.md as you work

---

## File Purposes Quick Reference

| File | Purpose | Update When |
|------|---------|-------------|
| `SESSION.md` | Current work focus | Throughout session |
| `PROGRESS.md` | Project status | End of session |
| `DECISIONS.md` | Technical choices | When making significant decision |
| `ISSUES.md` | Bugs & gotchas | When discovered/resolved |
| `sessions/` | Archive | End of session |

---

## Example Session Flow

```
User: "Hey Claude, read CLAUDE_START.md and let's continue"

Claude:
1. Reads PROGRESS.md, DECISIONS.md, ISSUES.md, SESSION.md
2. Summarizes current state: "I see we've completed genre detection and
   are currently testing with diverse tracks. Last session worked on..."
3. Asks: "What would you like to work on today?"

User: "Let's process 100 songs and test recommendation quality"

Claude:
1. Updates SESSION.md with new focus
2. Works on task, updating SESSION.md as files change
3. Documents any decisions or issues discovered
4. Continues until user says to wrap up

User: "Let's wrap up for today"

Claude:
1. Archives SESSION.md to sessions/2026-01-XX.md
2. Updates PROGRESS.md checkboxes
3. Suggests git commit message
```

---

## Context Management Benefits

- **No repeated explanations** - Files preserve context
- **Quick startup** - ~1000 lines to read vs full conversation
- **Clear progress** - Always know where you are
- **Preserved decisions** - Rationale captured for future
- **Simple maintenance** - Just markdown files

---

**Ready to start? Tell me what you'd like to work on!**
