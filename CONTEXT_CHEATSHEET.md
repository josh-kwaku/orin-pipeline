# Context Management Cheat Sheet

Quick reference for using the living documentation system.

## Starting a Session

```bash
# Just say this to Claude:
"Hey Claude, read CLAUDE_START.md and let's continue"
```

Claude will:
1. Read context files
2. Summarize current state
3. Ask what you want to work on

## During the Session

Claude automatically:
- Updates `SESSION.md` as work progresses
- Adds decisions to `DECISIONS.md`
- Logs issues to `ISSUES.md`

You don't need to do anything!

## Ending a Session

```bash
# Tell Claude:
"Let's wrap up for today"

# Claude will guide you through:
# 1. Archive SESSION.md
mv SESSION.md sessions/2026-01-XX.md

# 2. Update PROGRESS.md (move checkboxes)
# 3. Commit
git add *.md sessions/
git commit -m "Session: [what you did]"
git push
```

## File Overview

| File | What It Is | Size |
|------|------------|------|
| `CLAUDE_START.md` | Startup instructions for Claude | Read this first |
| `SESSION.md` | What you're working on RIGHT NOW | Resets each session |
| `PROGRESS.md` | Project status with checkboxes | Cumulative |
| `DECISIONS.md` | Technical choices & rationale | Cumulative |
| `ISSUES.md` | Bugs and gotchas | Updated as needed |
| `sessions/` | Archived session notes | Growing archive |

## Quick Commands

```bash
# View current progress
cat PROGRESS.md

# View recent decisions
head -100 DECISIONS.md

# Check known issues
cat ISSUES.md

# See last session
ls -t sessions/ | head -1 | xargs cat
```

## Tips

- **Start each session** with "read CLAUDE_START.md"
- **Let Claude manage files** - you just code
- **Trust the system** - context is preserved
- **Keep sessions focused** - one main task per session
- **End cleanly** - archive and commit

## Benefits

✓ No context loss between sessions
✓ No repeated explanations
✓ Fast startup (<30 seconds)
✓ Clear progress tracking
✓ Decision history preserved

## If Things Get Messy

```bash
# Start fresh SESSION.md
rm SESSION.md
touch SESSION.md

# Check what's in progress
cat PROGRESS.md

# Review recent decisions
head -50 DECISIONS.md
```

---

**That's it! Simple, maintainable, effective.**
