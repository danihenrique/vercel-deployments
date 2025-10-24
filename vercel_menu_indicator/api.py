from __future__ import annotations

import datetime as _dt
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import requests


_LOGGER = logging.getLogger(__name__)


@dataclass
class Deployment:
    id: str
    name: str
    url: str
    status: str  # one of: ready, building, error, queued, canceled, unknown
    created_at: _dt.datetime
    # Extra metadata to improve menu rendering
    branch: str = ""
    commit_sha: str = ""
    commit_message: str = ""
    author: str = ""
    target: str = ""  # e.g. production/preview


class VercelClient:
    """Minimal Vercel API client used by the indicator.

    Notes for future maintainers:
    - The Vercel API has evolved across versions (v6, v13). We handle both
      `state` and `readyState` fields to be resilient.
    - Team-scoped tokens often require passing `teamId` (which can be a slug)
      as a query param. We pass through the value provided by the user.
    """

    def __init__(self, token: str, team_id: Optional[str] = None, timeout_s: int = 10) -> None:
        self.token = token.strip()
        self.team_id = (team_id or "").strip() or None
        self.session = requests.Session()
        self.timeout_s = timeout_s
        self.base_url_candidates = [
            "https://api.vercel.com/v13",  # new
            "https://api.vercel.com/v6",  # legacy
        ]

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def list_deployments(self, limit: int = 10) -> List[Deployment]:
        params: Dict[str, Any] = {"limit": max(1, min(limit, 50))}
        if self.team_id:
            params["teamId"] = self.team_id

        last_error: Optional[Exception] = None
        for base in self.base_url_candidates:
            url = f"{base}/deployments"
            try:
                res = self.session.get(url, headers=self._headers(), params=params, timeout=self.timeout_s)
                if res.status_code == 401:
                    raise PermissionError("Unauthorized. Check Vercel API token and team scope.")
                res.raise_for_status()
                data = res.json() or {}
                deployments_raw = data.get("deployments") or data  # v6 may return list directly
                parsed = [self._parse_deployment(item) for item in deployments_raw]
                parsed.sort(key=lambda d: d.created_at, reverse=True)
                return parsed[: limit]
            except Exception as exc:  # meaningful handling: try next base or bubble up
                last_error = exc
                _LOGGER.debug("list_deployments failed via %s: %s", base, exc)
                continue
        if last_error:
            raise last_error
        return []

    def _parse_deployment(self, raw: Dict[str, Any]) -> Deployment:
        dep_id = str(raw.get("id") or raw.get("uid") or "")
        name = str(raw.get("name") or raw.get("project", {}).get("name") or "")
        url = str(raw.get("url") or raw.get("inspectorUrl") or "")
        created = raw.get("createdAt") or raw.get("created_at") or 0
        created_at = _dt.datetime.fromtimestamp(int(created) / 1000, tz=_dt.timezone.utc) if created else _dt.datetime.now(tz=_dt.timezone.utc)

        ready_state = (raw.get("readyState") or raw.get("state") or "").lower()
        # Map the many possible ready states to simplified buckets for the tray icon
        status_map = {
            "ready": "ready",
            "building": "building",
            "queued": "building",
            "initializing": "building",
            "error": "error",
            "failed": "error",
            "canceled": "error",
            "cancelled": "error",
        }
        status = status_map.get(ready_state, "unknown")

        # Extract git metadata in a provider-agnostic way (GitHub/GitLab/Bitbucket)
        branch, sha, message, author = self._extract_git_meta(raw)
        target = str(raw.get("target") or raw.get("environment") or "")

        return Deployment(
            id=dep_id,
            name=name or "(unknown)",
            url=url,
            status=status,
            created_at=created_at,
            branch=branch,
            commit_sha=sha,
            commit_message=message,
            author=author,
            target=target,
        )

    def _extract_git_meta(self, raw: Dict[str, Any]) -> Tuple[str, str, str, str]:
        """Best-effort extraction of branch/sha/message/author across providers.

        Reason for this logic: the Vercel payload uses different meta keys for
        GitHub/GitLab/Bitbucket. We normalize to improve menu readability.
        """
        meta = raw.get("meta") or {}

        # Branch
        branch = (
            meta.get("githubCommitRef")
            or meta.get("gitlabCommitRef")
            or meta.get("bitbucketCommitRef")
            or meta.get("branch")
            or meta.get("commitRef")
            or ""
        )

        # Commit SHA
        sha = (
            meta.get("githubCommitSha")
            or meta.get("gitlabCommitSha")
            or meta.get("bitbucketCommitSha")
            or meta.get("commitSha")
            or meta.get("sha")
            or ""
        )

        # Commit message
        message = (
            meta.get("githubCommitMessage")
            or meta.get("gitlabCommitMessage")
            or meta.get("bitbucketCommitMessage")
            or meta.get("commitMessage")
            or ""
        )

        # Author (prefer commit author; fallback to creator info)
        author = (
            meta.get("githubCommitAuthorName")
            or meta.get("gitlabCommitAuthorName")
            or meta.get("bitbucketCommitAuthorName")
            or meta.get("commitAuthorName")
            or ""
        )
        creator = raw.get("creator") or {}
        if not author:
            author = creator.get("name") or creator.get("username") or creator.get("email") or ""
        return str(branch), str(sha), str(message), str(author)


