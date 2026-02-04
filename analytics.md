# Aurelie English App - Analytics & Monitoring

> SQL Queries um Aurelies Nutzung zu verstehen
> Nutze diese im Supabase SQL Editor oder via Claude Code MCP

---

## Schnell-Check: Nutzt Aurelie die App?

```sql
-- Letzten 10 Sessions
SELECT
  session_date,
  total_exercises,
  correct,
  ROUND(correct::numeric / total_exercises * 100) as accuracy_pct,
  best_streak
FROM session_results
WHERE details->>'user_id' IS NULL OR details->>'user_id' = 'aurelie'
ORDER BY session_date DESC
LIMIT 10;
```

---

## Übungsfrequenz

```sql
-- Sessions pro Woche
SELECT
  DATE_TRUNC('week', session_date) as week,
  COUNT(*) as sessions,
  SUM(total_exercises) as total_exercises,
  ROUND(AVG(correct::numeric / total_exercises * 100), 0) as avg_accuracy
FROM session_results
WHERE details->>'user_id' IS NULL OR details->>'user_id' = 'aurelie'
GROUP BY 1
ORDER BY 1 DESC
LIMIT 8;
```

---

## Fehleranalyse: Welche Verben sind schwer?

```sql
-- Verben die im Spaced Repetition sind (= wurden falsch beantwortet)
SELECT
  item as verb,
  interval_days,
  next_review,
  status
FROM spaced_repetition
WHERE item NOT LIKE '%:%'  -- Nur echte Verben, keine Topics
ORDER BY next_review ASC;
```

---

## Topic-Schwierigkeiten

```sql
-- Welche Grammatik-Themen sind schwer?
SELECT
  item as topic,
  interval_days,
  next_review
FROM spaced_repetition
WHERE item LIKE 'topic:%'
ORDER BY interval_days ASC;  -- Kürzere Intervalle = schwieriger
```

---

## Detaillierte Fehleranalyse (letzte Session)

```sql
-- Zeige alle Antworten der letzten Session
SELECT
  session_date,
  ex->>'question' as question,
  ex->>'user_answer' as user_answer,
  ex->>'correct_answer' as correct_answer,
  ex->>'correct' as was_correct
FROM session_results,
  jsonb_array_elements(details->'exercises') as ex
WHERE details->>'user_id' IS NULL OR details->>'user_id' = 'aurelie'
ORDER BY session_date DESC
LIMIT 20;
```

---

## Streak & Engagement (wenn Tabellen existieren)

```sql
-- User Stats
SELECT * FROM user_stats WHERE user_id = 'aurelie';

-- Achievements
SELECT achievement_key, unlocked_at
FROM achievements
WHERE user_id = 'aurelie'
ORDER BY unlocked_at DESC;

-- Topic Mastery
SELECT topic_key, total_attempts, correct_attempts, mastery_level
FROM topic_mastery
WHERE user_id = 'aurelie'
ORDER BY mastery_level DESC, correct_attempts DESC;
```

---

## Zusammenfassung: Dashboard-Daten

```sql
-- Alles auf einen Blick
SELECT
  (SELECT COUNT(*) FROM session_results WHERE details->>'user_id' IS NULL OR details->>'user_id' = 'aurelie') as total_sessions,
  (SELECT SUM(total_exercises) FROM session_results WHERE details->>'user_id' IS NULL OR details->>'user_id' = 'aurelie') as total_exercises,
  (SELECT SUM(correct) FROM session_results WHERE details->>'user_id' IS NULL OR details->>'user_id' = 'aurelie') as total_correct,
  (SELECT COUNT(*) FROM spaced_repetition WHERE status = 'active' AND item NOT LIKE '%:%') as verbs_to_practice,
  (SELECT MAX(session_date) FROM session_results WHERE details->>'user_id' IS NULL OR details->>'user_id' = 'aurelie') as last_session;
```

---

## Test-User Daten separat sehen

```sql
-- Papa-Test Sessions (für QA)
SELECT * FROM session_results
WHERE details->>'user_id' = 'papa_test'
ORDER BY session_date DESC;

-- Papa-Test SR Items
SELECT * FROM spaced_repetition
WHERE item LIKE 'papa_test:%';
```

---

*Letzte Aktualisierung: 2026-02-04*
