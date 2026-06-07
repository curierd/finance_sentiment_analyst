-- Finance Sentiment Analyst: Unified Comments Database
-- Platform: SQLite
-- Date: 2026-06-07

-- Enable foreign keys and WAL mode for better concurrency
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ============================================================
-- Table: comments
-- Stores comments collected from Bilibili, Xiaohongshu, Xueqiu
-- ============================================================
CREATE TABLE IF NOT EXISTS comments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Platform identification
    platform        TEXT NOT NULL CHECK(platform IN ('bilibili', 'xiaohongshu', 'xueqiu')),

    -- Platform-specific IDs
    comment_id      TEXT,
    author_id       TEXT,
    author_name     TEXT,

    -- Content
    content TEXT NOT NULL,

    -- Engagement
    likes           INTEGER DEFAULT 0,
    replies         INTEGER DEFAULT 0,
    retweets        INTEGER DEFAULT 0,

    -- Source
    source_url      TEXT,
    local_image_path TEXT, -- Local path for downloaded images
    original_url    TEXT,           -- Backup of original image URL

    -- Bilibili-specific
    video_bvid      TEXT,
    video_title     TEXT,
    up_name         TEXT,
    up_uid          TEXT,

    -- Xueqiu-specific
    symbol TEXT,           -- Stock symbol e.g. SH600519

    -- Timestamps
    created_at      TEXT,           -- ISO8601 format from platform
    collected_at    TEXT DEFAULT (datetime('now')),

    -- Sentiment analysis results (filled later by textcnn_sentiment.py)
    sentiment TEXT CHECK(sentiment IN ('正面', '负面', '中性')),
    sentiment_score REAL,

    -- Manually fixed sentiment — once set, update_sentiment.py skips this row
    sentiment_fix TEXT CHECK(sentiment_fix IN ('正面', '负面', '中性')),

    -- Metadata
    raw_data TEXT            -- JSON blob of original platform data for audit
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_comments_platform ON comments(platform);
CREATE INDEX IF NOT EXISTS idx_comments_created_at ON comments(created_at);
CREATE INDEX IF NOT EXISTS idx_comments_likes ON comments(likes DESC);
CREATE INDEX IF NOT EXISTS idx_comments_sentiment ON comments(sentiment);
CREATE INDEX IF NOT EXISTS idx_comments_platform_date ON comments(platform, collected_at);

-- Partial index: high-engagement comments
CREATE INDEX IF NOT EXISTS idx_comments_high_likes ON comments(likes) WHERE likes > 10;

-- Composite index for like-weighted sentiment analysis
CREATE INDEX IF NOT EXISTS idx_comments_platform_sentiment ON comments(platform, sentiment);

-- ============================================================
-- Table: up_masters
-- Stores the source UP masters / bloggers info
-- ============================================================
CREATE TABLE IF NOT EXISTS up_masters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform        TEXT NOT NULL CHECK(platform IN ('bilibili', 'xiaohongshu', 'xueqiu')),
    uid TEXT NOT NULL, -- Platform-specific user ID
    name TEXT NOT NULL,
    fans_count INTEGER DEFAULT 0,
    video_count INTEGER DEFAULT 0,
    blacklisted INTEGER DEFAULT 0,      -- 1 = blocked
    source_file TEXT, -- Which preset file this came from
    created_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(platform, uid)
);

-- ============================================================
-- Table: videos
-- Stores video / note metadata for cross-reference
-- ============================================================
CREATE TABLE IF NOT EXISTS videos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    platform        TEXT NOT NULL CHECK(platform IN ('bilibili', 'xiaohongshu', 'xueqiu')),
    video_id TEXT NOT NULL,          -- bvid / note_id / post_id
    title TEXT,
    up_name         TEXT,
    up_uid TEXT,
    stats TEXT, -- JSON: views, likes, coins, favorites
    pubdate         TEXT,
    url TEXT,
    collected_at    TEXT DEFAULT (datetime('now')),
    UNIQUE(platform, video_id)
);

-- Index for video lookups
CREATE INDEX IF NOT EXISTS idx_videos_platform ON videos(platform);
CREATE INDEX IF NOT EXISTS idx_videos_up ON videos(up_uid);