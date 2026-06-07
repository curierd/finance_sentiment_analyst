#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Comment service — business logic layer"""

from backend.repositories.comment_repository import CommentRepository


class CommentService:
    def __init__(self):
        self.repo = CommentRepository()

    def list_comments(self, filters=None):
        return self.repo.find_all(filters)

    def get_comment(self, comment_id):
        return self.repo.find_by_id(comment_id)

    def lock_sentiment(self, comment_id, sentiment_fix):
        if sentiment_fix not in ("正面", "负面", "中性", None):
            raise ValueError("Invalid sentiment_fix value")
        return self.repo.update_sentiment_fix(comment_id, sentiment_fix)

    def get_stats(self):
        return self.repo.stats()

    def get_up_masters(self):
        return self.repo.find_up_masters()

    def get_videos(self):
        return self.repo.find_videos()