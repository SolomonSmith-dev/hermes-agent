"""A worktree card naming a branch that is already checked out elsewhere must not fail dispatch.

``git worktree add <target> <branch>`` refuses when the branch is checked out in any other worktree
(including the main checkout). ``_ensure_git_worktree`` used to surface that as a RuntimeError, which
the dispatcher turned into ``spawn_failed`` and, after two tries, ``gave_up``. It now cuts a fresh
``wt/<task-id>`` branch from the occupied branch's tip and returns the branch it actually used.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from hermes_cli import kanban_db as kb
from hermes_cli import kanban_db_connect as kbc
from hermes_cli import kanban_db_workspace as kbw


@pytest.fixture
def kanban_home(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    kb.init_db()
    return home


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), "-c", "user.name=Test User", "-c", "user.email=test@example.com",
         "-c", "commit.gpgsign=false", *args],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def _make_repo(tmp_path: Path, branch: str = "feat/x") -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", branch, str(repo)], check=True, capture_output=True, text=True)
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "init")
    return repo


def _new_task(**kw):
    with kbc.connect() as conn:
        tid = kb.create_task(conn, title="card", workspace_kind="worktree", **kw)
        return kb.get_task(conn, tid)


def test_branch_checked_out_in_main_repo_does_not_fail(kanban_home, tmp_path):
    repo = _make_repo(tmp_path, "feat/x")
    task = _new_task(workspace_path=str(repo), branch_name="feat/x")
    tip = _git(repo, "rev-parse", "feat/x")

    workspace, branch = kbw._resolve_worktree_workspace(task)

    assert workspace == (repo / ".worktrees" / task.id).resolve()
    assert branch == f"wt/{task.id}"
    assert _git(workspace, "rev-parse", "HEAD") == tip  # cut from the occupied branch's tip
    assert _git(workspace, "rev-parse", "--abbrev-ref", "HEAD") == branch
    assert _git(repo, "rev-parse", "--abbrev-ref", "HEAD") == "feat/x"  # main checkout untouched


def test_branch_checked_out_in_linked_worktree_does_not_fail(kanban_home, tmp_path):
    repo = _make_repo(tmp_path, "main")
    other = repo / ".worktrees" / "other"
    _git(repo, "worktree", "add", str(other), "-b", "fix/busy", "HEAD")
    target = repo / ".worktrees" / "card-path"
    task = _new_task(workspace_path=str(target), branch_name="fix/busy")

    workspace, branch = kbw._resolve_worktree_workspace(task)

    assert workspace == target
    assert branch == f"wt/{task.id}"
    assert _git(other, "rev-parse", "--abbrev-ref", "HEAD") == "fix/busy"


def test_free_existing_branch_is_still_reused(kanban_home, tmp_path):
    repo = _make_repo(tmp_path, "main")
    _git(repo, "branch", "fix/free")
    task = _new_task(workspace_path=str(repo), branch_name="fix/free")

    workspace, branch = kbw._resolve_worktree_workspace(task)

    assert branch == "fix/free"
    assert _git(workspace, "rev-parse", "--abbrev-ref", "HEAD") == "fix/free"


def test_ensure_git_worktree_returns_the_branch_used(kanban_home, tmp_path):
    repo = _make_repo(tmp_path, "feat/x")
    used = kbw._ensure_git_worktree(repo, repo / ".worktrees" / "t_abc", "feat/x")
    assert used == "wt/t_abc"
    assert kbw._ensure_git_worktree(repo, repo / ".worktrees" / "t_new", "brand/new") == "brand/new"
