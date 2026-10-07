# How branches are used

## The three kinds of branch

| Branch | What it holds |
|---|---|
| `main` | The project base only: idea, architecture, roadmap. No build work. |
| `develop` | The full project so far. Every finished phase is merged here. |
| `phase-N-name` | The work for one phase. Created from `develop`, merged back into `develop` when the phase is done. |

```
main ──●  (base, stays as it is)
        \
develop  ●──────────●──────────●
          \        / \        /
phase-1    ●──●──●    \      /
phase-2                ●──●─●
```

## Rules

1. Never build directly on `main` or `develop`.
2. Start each phase from the latest `develop`.
3. A phase is merged only when its "done when" check in [ROADMAP.md](ROADMAP.md) passes and its tests pass.
4. Every phase adds a notes file at `docs/phases/phase-N.md` saying what was built, how to run it, what was checked and what is still open.
5. `main` is updated only when you decide to release a finished state.

## Commands

Start a phase:

```bash
git checkout develop
git checkout -b phase-2-benchmark-engine
```

Finish a phase:

```bash
git checkout develop
git merge --no-ff phase-2-benchmark-engine
```

## Commit messages

Start with the phase, then say what changed:

```
Phase 1: add scoring rubric with seven measures
Phase 1: add mania persona and two scenarios
```

## The first nine phases

Phases 1 to 9 were each built on their own branch (`phase-1-rubric-personas` to
`phase-9-deploy`) and merged into `develop` one after another. Those branches were then
removed. Their commits are still in the history of `develop`:

```bash
git log --oneline --graph develop
```
