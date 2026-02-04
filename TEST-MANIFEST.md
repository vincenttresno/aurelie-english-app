# Aurelie English App - Test Manifest

> Systematische Prüfung aller Features gegen erwartetes Verhalten
> Created: 2026-02-04

---

## 1. Core Learning Flow

### 1.1 Exercise Generation
| Test | Expected | Status |
|------|----------|--------|
| Topic selection filters exercises correctly | Only exercises from selected topic appear | ❓ TO TEST |
| "Gemischt" shows all topics | Exercises from multiple topics in one session | ❓ TO TEST |
| No exercise repeats within session | Same question doesn't appear twice | ❓ TO TEST |
| Hints are helpful and age-appropriate | Explain HOW to solve, not just the answer | ✅ FIXED |

### 1.2 Answer Checking
| Test | Expected | Status |
|------|----------|--------|
| Exact match required | "will be" ≠ "willbe" ≠ "will Be" | ❓ TO TEST |
| Case insensitive | "Faster" = "faster" | ❓ TO TEST |
| Whitespace trimmed | " faster " = "faster" | ❓ TO TEST |

### 1.3 Feedback on Wrong Answers
| Test | Expected | Status |
|------|----------|--------|
| Will Future: explains "will + Grundform" | Not "Vergangenheit" | ✅ FIXED |
| Going-to Future: explains structure | "am/is/are + going to + Verb" | ✅ FIXED |
| Comparison: explains rule | "-er for short, more for long" | ✅ FIXED (hints) |
| Past vs Perfect: explains signal words | "yesterday = Past, ever = Perfect" | ❓ TO TEST |

---

## 2. Spaced Repetition System

### 2.1 What Gets Tracked
| Test | Expected | Status |
|------|----------|--------|
| Wrong verbs get added to SR | "eat" added when user fails | ✅ WORKS |
| Wrong topics get added to SR | "Will Future" added when user fails | ❌ NOT WORKING |
| SR items appear in future sessions | Due items shown on start screen | ❓ TO TEST |

### 2.2 Interval Logic (SM-2)
| Test | Expected | Status |
|------|----------|--------|
| First review: 1 day | `next_review = today + 1` | ✅ WORKS |
| Correct → increase interval | 1 → 3 → 7 → 14 → 30 → 60 | ❓ TO TEST |
| Wrong → reset to 1 day | Back to beginning | ❓ TO TEST |

---

## 3. Engagement System

### 3.1 Streaks
| Test | Expected | Status |
|------|----------|--------|
| First session today → streak = 1 | New streak starts | ❓ TO TEST |
| Session yesterday + today → streak += 1 | Streak continues | ❓ TO TEST |
| Missed day → streak resets | Unless freeze available | ❓ TO TEST |
| Streak freeze works | One free miss per week | ❓ TO TEST |
| Longest streak tracked | Shows "Rekord: X" | ✅ ADDED |

### 3.2 XP & Levels
| Test | Expected | Status |
|------|----------|--------|
| +10 XP per correct answer | Shown in session summary | ❓ TO TEST |
| Streak bonus (3+) | +5 XP per answer in streak | ❓ TO TEST |
| Perfect session bonus | +50 XP for 100% | ❓ TO TEST |
| Level = total_xp / 500 + 1 | Level up every 500 XP | ❓ TO TEST |

### 3.3 Achievements
| Test | Expected | Status |
|------|----------|--------|
| first_session unlocks | After completing any session | ❓ TO TEST |
| streak_3 unlocks at 3 days | Check trigger | ❓ TO TEST |
| perfect_5 unlocks | 5/5 correct in one session | ❓ TO TEST |

### 3.4 Topic Mastery
| Test | Expected | Status |
|------|----------|--------|
| Tracks attempts per topic | Total + correct counted | ❓ TO TEST |
| Mastery levels calculated | LEARNING → PRACTICING → MASTERED | ❓ TO TEST |
| Dashboard shows progress | Visual display of mastery | ❓ TO TEST |

---

## 4. Data Persistence

### 4.1 Session Results
| Test | Expected | Status |
|------|----------|--------|
| Session saved on completion | All exercises + answers stored | ✅ WORKS |
| Details include question + user answer | For debugging/review | ✅ WORKS |
| Session NOT saved if incomplete | No partial saves | ❓ TO TEST |

### 4.2 Feedback
| Test | Expected | Status |
|------|----------|--------|
| Feedback saved with context | Question, topic, correct, user answer, text | ✅ DESIGNED |
| Feedback actually reaches DB | Check after submission | ❓ TO TEST |

### 4.3 Database Resilience
| Test | Expected | Status |
|------|----------|--------|
| App works without DB | Graceful degradation | ✅ FIXED |
| No crashes on DB timeout | Returns None, continues | ✅ FIXED |
| Reconnects after disconnect | Cache cleared, retry | ✅ FIXED |

---

## 5. UI/UX

### 5.1 Dashboard
| Test | Expected | Status |
|------|----------|--------|
| Shows only 2 metrics | Streak + Level (simplified) | ✅ DONE |
| Tooltips explain metrics | Help text on hover | ✅ DONE |
| Rekord shown under streak | "Rekord: X" as delta | ✅ DONE |

### 5.2 Exercise Screen
| Test | Expected | Status |
|------|----------|--------|
| Progress bar accurate | Shows X of Y | ✅ WORKS |
| Streak counter visible | "🔥 X richtig hintereinander" | ✅ WORKS |
| Hint button works | Shows hint from exercise | ❓ TO TEST |
| Vocabulary help works | Explains unknown words | ✅ FIXED |

### 5.3 Results Screen
| Test | Expected | Status |
|------|----------|--------|
| Shows correct/wrong summary | With specific verbs | ✅ WORKS |
| Shows XP earned | Breakdown of sources | ❓ TO TEST |
| Shows new achievements | If any unlocked | ❓ TO TEST |
| "Morgen" section accurate | Lists verbs to review | ✅ WORKS |

---

## 6. Known Bugs to Fix

| Bug | Impact | Fix Status |
|-----|--------|------------|
| SR only tracks verbs, not topics | Will Future errors not repeated | 🔴 TO FIX |
| explain_why_wrong said "Vergangenheit" for Will Future | Confusing feedback | ✅ FIXED |
| Hints were not helpful (just "fast + er") | Not teaching HOW | ✅ FIXED |
| Vocabulary explanation failed ("Frag Papa") | Missing api_client | ✅ FIXED |
| No Rekord/longest streak shown | User asked for it | ✅ FIXED |
| 4 metrics were confusing | Simplified to 2 | ✅ FIXED |

---

## 7. Test Commands

```sql
-- Check recent sessions
SELECT * FROM session_results ORDER BY session_date DESC LIMIT 5;

-- Check spaced repetition items
SELECT * FROM spaced_repetition ORDER BY next_review ASC;

-- Check error patterns
SELECT * FROM error_patterns WHERE status = 'AKTIV';

-- Check user stats (streak, XP, level)
SELECT * FROM user_stats WHERE user_id = 'aurelie';

-- Check feedback
SELECT * FROM feedback ORDER BY created_at DESC LIMIT 5;

-- Check achievements
SELECT * FROM achievements WHERE user_id = 'aurelie';

-- Check topic mastery
SELECT * FROM topic_mastery WHERE user_id = 'aurelie';
```

---

## 8. Priority Fixes

### P0 - Critical (Blocks Learning)
1. ❌ **SR tracks topics, not just verbs** - Will Future/Comparison errors need repeat

### P1 - Important (UX Issues)
2. ✅ Hints are helpful and explain HOW
3. ✅ Wrong answer explanations are accurate for each grammar type
4. ✅ Vocabulary explanation works

### P2 - Nice to Have
5. ✅ Rekord/longest streak shown
6. ✅ Simplified dashboard (2 metrics)

---

*Last updated: 2026-02-04*
