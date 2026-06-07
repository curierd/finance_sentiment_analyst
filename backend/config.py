#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Backend configuration"""

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "db", "comments.db")