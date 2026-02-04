-- Engagement Layer Tables for Aurelie English App
-- Run this in Supabase SQL Editor

-- 1. User Stats Table (daily streaks, total XP, level)
CREATE TABLE IF NOT EXISTS user_stats (
    id SERIAL PRIMARY KEY,
    user_id TEXT DEFAULT 'aurelie' UNIQUE,  -- Single user for now
    current_streak INTEGER DEFAULT 0,
    longest_streak INTEGER DEFAULT 0,
    total_xp INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1,
    last_practice_date DATE,
    streak_freeze_available BOOLEAN DEFAULT TRUE,
    streak_freeze_used_date DATE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 2. XP Log Table (track all XP earned)
CREATE TABLE IF NOT EXISTS xp_log (
    id SERIAL PRIMARY KEY,
    user_id TEXT DEFAULT 'aurelie',
    xp_amount INTEGER NOT NULL,
    xp_type TEXT NOT NULL,  -- 'correct_answer', 'streak_bonus', 'perfect_session', 'daily_goal'
    source_session_id INTEGER,
    earned_at TIMESTAMP DEFAULT NOW()
);

-- 3. Achievements Table (unlocked badges)
CREATE TABLE IF NOT EXISTS achievements (
    id SERIAL PRIMARY KEY,
    user_id TEXT DEFAULT 'aurelie',
    achievement_key TEXT NOT NULL,  -- e.g., 'first_session', '7_day_streak', 'perfect_10'
    unlocked_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, achievement_key)
);

-- 4. Topic Mastery Table (progress per grammar topic)
CREATE TABLE IF NOT EXISTS topic_mastery (
    id SERIAL PRIMARY KEY,
    user_id TEXT DEFAULT 'aurelie',
    topic_key TEXT NOT NULL,  -- e.g., 'simple_past_regular', 'present_perfect'
    total_attempts INTEGER DEFAULT 0,
    correct_attempts INTEGER DEFAULT 0,
    mastery_level TEXT DEFAULT 'LEARNING',  -- LEARNING, PRACTICING, MASTERED
    last_practiced DATE,
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, topic_key)
);

-- Initialize default user stats
INSERT INTO user_stats (user_id) VALUES ('aurelie')
ON CONFLICT (user_id) DO NOTHING;

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_xp_log_user_date ON xp_log(user_id, earned_at);
CREATE INDEX IF NOT EXISTS idx_topic_mastery_user ON topic_mastery(user_id);
CREATE INDEX IF NOT EXISTS idx_achievements_user ON achievements(user_id);
