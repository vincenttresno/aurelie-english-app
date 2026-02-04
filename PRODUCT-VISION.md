# Aurelie English App - Product Vision

> Eine Englisch-Lern-App für Aurelie (6. Klasse Gymnasium)
> Created: 2026-02-04

---

## Die Kern-Erkenntnis

**"Duolingo's secret isn't their algorithm - it's that users don't quit."**

Aus der Lernforschung wissen wir:

| Faktor | Einfluss auf Lernerfolg |
|--------|------------------------|
| Motivation & Gewohnheit | 40% |
| Verständlicher Input | 30% |
| Spaced Repetition (SRS) | 20% |
| Algorithmus-Optimierung | 10% |

**Konsequenz**: Wir bauen eine App, die Aurelie BENUTZEN WILL, nicht nur eine mit dem besten Algorithmus.

---

## Für Wen

**Aurelie** - 11 Jahre, 6. Klasse Gymnasium Schweiz

- Lernt Englisch mit Green Line 2 / Access
- Braucht Übung mit unregelmässigen Verben und Grammatik
- Spricht kein "Gamer-Deutsch" (XP, Level sind fremd)
- Muss Spass haben, sonst macht sie's nicht
- Vater (Vincent) kann bei Fragen helfen

---

## Was Die App Sein Soll

### 1. Ein tägliches Ritual (5-10 Minuten)
- Kurze Sessions, die in den Alltag passen
- Streak motiviert zum Dranbleiben
- Streak-Freeze verzeiht einen vergessenen Tag

### 2. Intelligent wiederholend
- Was falsch war, kommt morgen wieder (Spaced Repetition)
- Sowohl **Verben** (eat → ate → eaten) als auch **Grammatik-Themen** (Will Future, Comparison)
- Intervalle wachsen bei Erfolg: 1 → 3 → 7 → 14 → 30 → 60 Tage

### 3. Hilfreich bei Fehlern
- **Hints** erklären WIE man die Antwort findet, nicht nur WAS die Antwort ist
- **Feedback** erklärt WARUM die Antwort falsch war
- **Vokabelhilfe** erklärt unbekannte Wörter auf Deutsch

### 4. Altersgerecht
- Keine Gaming-Begriffe (XP, Achievements)
- Einfache Metriken: Streak + Level
- Tooltips erklären alles
- Deutsche UI-Texte

### 5. Curriculum-aligned
- Deckt alle Grammatik-Themen der 6. Klasse ab
- Folgt Green Line 2 / Access Lehrbuch
- Vokabeln nach Einheiten organisiert

---

## Was Die App NICHT Sein Soll

- **Kein Ersatz für Unterricht** - Ergänzung zum Schulstoff
- **Kein Spiel** - Lernen steht im Vordergrund
- **Kein Druck** - Fehler sind Teil des Lernens
- **Keine Ablenkung** - Fokus auf die Übung

---

## Kern-Features

### Jetzt Implementiert ✅

| Feature | Beschreibung |
|---------|--------------|
| Übungen generieren | 320 Übungen, 8 Grammatik-Themen |
| Antwort prüfen | Case-insensitive, Whitespace-tolerant |
| Hints | Erklären WIE man die Antwort findet |
| Falsches Feedback | Erklärt Grammatik-Regeln |
| Vokabelhilfe | KI erklärt unbekannte Wörter |
| Spaced Repetition | Verben UND Topics werden wiederholt |
| Streak-System | Tage hintereinander geübt |
| Rekord-Anzeige | Längster Streak sichtbar |
| Level-System | Fortschritt sichtbar |
| Dashboard | 2 klare Metriken mit Tooltips |
| Datenbank-Resilience | App läuft auch ohne DB |

### Geplant (Backlog)

| Feature | Priorität | Warum |
|---------|-----------|-------|
| Push-Notifications | P1 | "Aurelie, dein Streak wartet!" |
| Mehr Übungen (→500) | P1 | Keine Wiederholungen in Session |
| Achievement-Badges | P2 | Motivation durch Meilensteine |
| Topic-Mastery Anzeige | P2 | Visueller Fortschritt pro Thema |
| FSRS Algorithmus | P3 | 20-30% effizienter (braucht Daten) |

---

## Erfolgs-Metriken

| Metrik | Ziel |
|--------|------|
| Sessions pro Woche | 5+ |
| Durchschnittliche Session | 10 Minuten |
| 7-Tage Retention | 60% |
| Streak-Länge (Durchschnitt) | 7+ Tage |

---

## Technologie

- **Frontend**: Streamlit (Python)
- **Datenbank**: Supabase (PostgreSQL)
- **KI**: Claude Haiku (für Vokabel-Erklärungen)
- **Hosting**: Streamlit Cloud
- **Algorithmus**: SM-2 Spaced Repetition

---

## Guiding Principles

1. **Einfachheit über Features** - Weniger ist mehr für ein Kind
2. **Erklären, nicht nur korrigieren** - Hints müssen WIE erklären
3. **Fehler sind Chancen** - SR bringt Fehler zurück zum Üben
4. **Gewohnheit schlägt Perfektion** - Tägliches Üben > perfekter Algorithmus
5. **Testen mit echtem User** - Aurelie's Feedback ist Gold

---

*Dieses Dokument beschreibt die Vision. Für Test-Checkliste siehe TEST-MANIFEST.md*
