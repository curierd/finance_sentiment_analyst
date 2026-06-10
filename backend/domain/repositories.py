#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Domain repository interfaces (Protocol-based for adapter pattern).

These are the "ports" that business logic depends on.
Adapters (sqlite, postgres, etc.) implement these interfaces.
"""

from typing import Protocol, Optional, Any


class CommentRepo(Protocol):
    """Repository for comment CRUD and analytics queries."""

    def find_all(self, filters: Optional[dict] = None) -> dict: ...

    def find_by_id(self, comment_id: int) -> Optional[dict]: ...

    def insert(self, data: dict) -> dict: ...

    def update_image(self, comment_id: int,
                     local_image_path: Optional[str] = None,
                     original_url: Optional[str] = None) -> Optional[dict]: ...

    def update_sentiment_fix(self, comment_id: int,
                             sentiment_fix: Optional[str]) -> Optional[dict]: ...

    def delete(self, comment_id: int) -> bool: ...

    def stats(self, filters: Optional[dict] = None) -> dict: ...

    def stats_by_date(self, granularity: str = "day",
                      filters: Optional[dict] = None) -> dict: ...

    def find_up_masters(self) -> list: ...

    def find_videos(self) -> list: ...

    def find_unlocked_ids_by_filter(self, filters: Optional[dict] = None) -> list: ...

    def batch_update_sentiment(self, updates: list) -> None: ...


class UnitOfWork(Protocol):
    """Protocol for transactional unit-of-work.

    Adapters provide context-managed transactions.
    """

    comments: CommentRepo

    def __enter__(self) -> "UnitOfWork": ...

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
