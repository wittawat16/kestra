---
name: givename
description: Suggests names for anything — variables, functions, classes, files/folders, git branches, commit messages, projects, features, or new skills — by first detecting the actual naming convention already in use nearby (casing, verb/noun shape, prefixes, domain vocabulary) instead of guessing from generic best practice. Use this skill whenever the user asks "what should I name/call this", "help me name X", "suggest a name for...", "is there a naming convention for...", wants a branch/commit name, is unsure what to call a new variable/function/file/class, or is naming a new project/feature/skill — even if they don't use the word "name" explicitly (e.g. "what should this function be called", "gotta call this something").
---

# givename

Most naming advice is generic ("use descriptive names!"). That's not the hard part — the hard part
is that every codebase, team, and repo already has its own accent: `getUserById` vs `get_user_by_id`
vs `fetchUser`, `feature/`-prefixed branches vs plain ones, `fix:`/`feat:` commit prefixes vs free
text. A name that's "good" in the abstract but breaks the local accent sticks out and gets renamed
in review. So the job here isn't to invent a name from first principles — it's to **read the
context first, then propose names that sound like they were already there.**

## Process

1. **Figure out what's being named.** One of roughly: a code identifier (variable, function,
   method, class, constant), a file or folder, a git branch, a commit message, or a
   project/feature/skill/package name. If it's ambiguous from the request, ask — the convention
   research differs a lot by category (a variable's convention lives in the file next to it; a
   branch's convention lives in `git branch -a` / `git log`).

2. **Gather real evidence of the existing convention — don't rely on memory or generic defaults.**
   What to look at depends on the category:

   | Naming what | Look at |
   |---|---|
   | Variable / function / class in a file | Other identifiers in the same file, then the same module/package. Casing (`camelCase`, `snake_case`, `PascalCase`, `SCREAMING_SNAKE_CASE`), verb-noun shape (`getX` vs `fetchX` vs `x()`), boolean prefixes (`is`/`has`/`should`), and whether abbreviations are common or spelled out. |
   | New file or folder | Sibling files in the same directory — casing, whether names are singular/plural, whether there's a suffix pattern (`*.service.ts`, `*_test.py`, `*.spec.js`). |
   | Git branch | `git branch -a` and recent `git log --oneline -20` for merge commits — is there a `type/description` prefix convention (`feature/`, `fix/`, `chore/`), a ticket-id prefix, hyphens vs slashes. |
   | Commit message | `git log --oneline -30` — Conventional Commits (`feat:`, `fix:`, `refactor:`)? Imperative mood? Ticket references? |
   | Project / feature / skill / package | Sibling projects/skills/packages in the same parent folder or org — casing, whether names are verb-first (action-oriented) or noun-first, length norms, whether a prefix/namespace is customary (this repo's own `workflow/kestra-build`, `workflow/kestra-run` pattern is a good example: noun-first, kebab-case, grouped by folder). |

   Use real tool calls (`grep`, `ls`, `git log`, `git branch`) to gather this — don't guess what the
   convention "probably" is. If the surrounding context is too sparse to infer a convention (a brand
   new empty repo, a lone file with one identifier), say so plainly and fall back to whatever
   ecosystem-standard convention applies (e.g. PEP 8 for Python, standard JS style) rather than
   inventing a house style that isn't actually there.

3. **Understand what the thing being named actually does or represents.** A convention tells you
   the *shape* of a good name, not the *content*. If the user hasn't said what the variable holds or
   what the branch/feature is for, ask for a one-line description before proposing names — a
   perfectly-cased name for the wrong concept is still wrong.

4. **Always propose exactly 5 candidates, ordered shortest to longest** (by character count of the
   final name — for a `type/description` branch or a `prefix:` commit, count the whole string, not
   just the description part), each following the detected convention, plus a one-line reason per
   candidate tying it back to the *specific* evidence found (not a generic justification). Five is
   the target even when the convention is narrow or the evidence is thin — vary the angle across
   candidates (e.g. different valid abbreviation choices, singular vs plural, different but
   equally-valid verb choices, more/less scope specificity) rather than padding with near-duplicates
   just to hit the count — the length spread should come naturally from that variety, not from
   artificially truncating or padding a single idea. If a name would violate the established
   convention on purpose (e.g. the user's ask doesn't fit any existing pattern), say so explicitly
   rather than silently picking something off-pattern.

5. **Flag convention conflicts, don't silently pick a side.** If the evidence is mixed (half the
   file uses `camelCase`, half uses `snake_case` — common in codebases mid-migration, or ones mixing
   a library's external API with internal code), point out the split and ask which one to follow, or
   default to whichever pattern is more prevalent nearby and say why.

## Output format

Keep it short — this is a naming lookup, not a report. **Always render the 5 candidates as a
numbered list, one per line — never as prose, a comma-separated run-on, or an inline mention.** The
numbering isn't decorative here: it *is* the shortest→longest ordering, so a reader should be able
to glance at the list and immediately see the length progression. Roughly:

```
Convention found: <one-line summary, e.g. "kebab-case, noun-first, grouped by folder (see workflow/kestra-build, workflow/kestra-run)">
Evidence: <what you actually looked at — file/command, e.g. "ls productivity/, workflow/">

Suggestions (shortest → longest):
1. `short` — <why, tied to the evidence>
2. `a-bit-longer` — <why>
3. `medium-length-one` — <why>
4. `a-longer-candidate-name` — <why>
5. `the-longest-most-explicit-candidate` — <why>
```

If there's a convention conflict or missing context, lead with that instead of guessing:

```
Found two conventions in play: <A> (used in <where>) vs <B> (used in <where>). Which should this follow?
```

## Notes

- Don't over-explain generic naming theory (avoid abbreviations, be descriptive, etc.) unless the
  user seems to want that — the value this skill adds is the *local* convention match, not a
  naming-101 refresher.
- For code identifiers, a quick grep for near-duplicate existing names is worth doing even when not
  asked — proposing a name that collides with (or is confusingly similar to) something already in
  scope is worse than a slightly generic one that's unambiguous.
