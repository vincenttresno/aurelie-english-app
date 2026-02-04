"""
Aurelie English Learning App
============================
Streamlit UI für das Aurelie-Lernsystem.
Nutzt Anthropic Claude API (zuverlässig, Vincent hat bereits einen Key).
"""

import streamlit as st
import anthropic
import os
import json
import re
import random
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

# Lade .env Datei (für API Key)
load_dotenv()

# Basis-Pfad zum Aurelie-System (für lokale Dateien die noch nicht migriert sind)
BASE_PATH = Path(__file__).parent.parent.parent / "areas" / "aurelie-english"

# Content-Pfad für JSON-Dateien (exercises, vocabulary, irregular_verbs)
CONTENT_PATH = Path(__file__).parent / "content"

# --- Content Loading Functions ---
@st.cache_data
def load_exercises_json():
    """Lädt alle Übungen aus exercises.json."""
    path = CONTENT_PATH / "exercises.json"
    if path.exists():
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get("exercises", {})
    return {}

@st.cache_data
def load_vocabulary_json():
    """Lädt alle Vokabeln aus vocabulary.json."""
    path = CONTENT_PATH / "vocabulary.json"
    if path.exists():
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get("vocabulary", {})  # JSON uses "vocabulary" not "units"
    return {}

@st.cache_data
def load_irregular_verbs_json():
    """Lädt alle unregelmäßigen Verben aus irregular_verbs.json."""
    path = CONTENT_PATH / "irregular_verbs.json"
    if path.exists():
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get("verbs", [])
    return []

def get_all_exercises_as_templates():
    """Konvertiert JSON-Übungen in das Template-Format für Kompatibilität.

    Returns:
        list: [(question, verb, answer, hint, topic), ...]
    """
    exercises_data = load_exercises_json()
    templates = []

    for topic_key, topic_data in exercises_data.items():
        # JSON uses "items" not "exercises" for the exercise list
        items = topic_data.get("items", [])
        for ex in items:
            # Format: (Satz mit Lücke, Verb-Infinitiv, richtige Antwort, Hint, Topic-Key)
            templates.append((
                ex.get("question", ""),
                ex.get("verb", ""),  # May be empty for regular verbs
                ex.get("answer", ""),
                ex.get("hint", ""),
                topic_key
            ))

    return templates

def get_vocabulary_dict():
    """Erstellt ein flaches Dictionary aus allen Vokabeln für die Wort-Erklärung.

    Returns:
        dict: {word: explanation, ...}
    """
    vocab_data = load_vocabulary_json()
    vocab_dict = {}

    for unit_key, unit_data in vocab_data.items():
        words = unit_data.get("words", [])
        for word in words:
            # JSON uses "en" and "de" not "english" and "german"
            english = word.get("en", "").lower()
            german = word.get("de", "")
            example = word.get("example", "")

            if english:
                if example:
                    vocab_dict[english] = f"{german}. '{example}'"
                else:
                    vocab_dict[english] = german

    # Füge auch Verb-Formen aus irregular_verbs hinzu
    verbs = load_irregular_verbs_json()
    for verb in verbs:
        infinitive = verb.get("infinitive", "").lower()
        past_simple = verb.get("past_simple", "").lower()
        past_participle = verb.get("past_participle", "").lower()
        german = verb.get("german", "")
        memory_trick = verb.get("memory_trick", "")

        forms_str = f"{infinitive} → {past_simple} → {past_participle}"

        if infinitive and infinitive not in vocab_dict:
            vocab_dict[infinitive] = f"{german}. {forms_str}"
        if past_simple and past_simple not in vocab_dict:
            vocab_dict[past_simple] = f"{german} (von '{infinitive}'). {forms_str}"
        if past_participle and past_participle not in vocab_dict and past_participle != past_simple:
            vocab_dict[past_participle] = f"{german} (von '{infinitive}'). {forms_str}"

    return vocab_dict

# --- Supabase Database Connection ---
# Flag um zu tracken ob DB verfügbar ist (session-state für thread safety)
def is_db_available():
    """Prüft ob Datenbank verfügbar ist."""
    return st.session_state.get('_db_available', False)

def set_db_available(value):
    """Setzt den DB-Status."""
    st.session_state['_db_available'] = value

@st.cache_resource
def get_db_connection():
    """Erstellt eine persistente Datenbankverbindung.

    GARANTIERT: Gibt niemals einen Fehler - entweder Connection oder None.
    App läuft IMMER, auch ohne DB (dann ohne persistente Daten).
    """
    # Credentials NUR aus Streamlit Secrets oder Environment Variables
    # NIEMALS hardcoded!
    try:
        db_config = st.secrets["database"]
        conn = psycopg2.connect(
            host=db_config["host"],
            port=db_config["port"],
            database=db_config["database"],
            user=db_config["user"],
            password=db_config["password"],
            sslmode='require',
            connect_timeout=5  # Timeout um hängende Connections zu vermeiden
        )
        return conn
    except Exception:
        pass  # Streamlit secrets nicht verfügbar

    # Fallback: Environment Variables für lokale Entwicklung
    try:
        host = os.environ.get("SUPABASE_HOST")
        password = os.environ.get("SUPABASE_PASSWORD")
        if host and password:
            conn = psycopg2.connect(
                host=host,
                port=5432,
                database='postgres',
                user='postgres',
                password=password,
                sslmode='require',
                connect_timeout=5
            )
            return conn
    except Exception:
        pass  # Env vars nicht verfügbar oder Connection fehlgeschlagen

    # Keine DB-Verbindung möglich - App läuft trotzdem (ohne persistente Daten)
    return None

def db_query(query, params=None, fetch=True):
    """Führt eine Datenbankabfrage aus mit automatischer Reconnection.

    GARANTIERT: Gibt niemals einen Fehler - entweder Ergebnis oder None.
    Alle Exceptions werden intern abgefangen.
    """
    conn = None
    try:
        conn = get_db_connection()
        if conn is None:
            set_db_available(False)
            return None  # DB nicht verfügbar

        # Prüfe ob Verbindung noch aktiv ist
        if conn.closed:
            st.cache_resource.clear()
            conn = get_db_connection()
            if conn is None:
                set_db_available(False)
                return None

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            if fetch:
                result = cur.fetchall()
                conn.commit()
                set_db_available(True)
                return result
            conn.commit()
            set_db_available(True)
            return None
    except psycopg2.OperationalError:
        # Verbindung verloren - Cache leeren
        try:
            st.cache_resource.clear()
        except Exception:
            pass
        set_db_available(False)
        return None
    except Exception:
        # Alle anderen Fehler
        try:
            if conn and not conn.closed:
                conn.rollback()
        except Exception:
            pass
        set_db_available(False)
        return None


def safe_db_operation(func):
    """Decorator der Datenbankfunktionen sicher macht.

    Fängt ALLE Exceptions ab und gibt einen Fallback-Wert zurück.
    """
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception:
            return None
    return wrapper

# --- Page Config ---
st.set_page_config(
    page_title="Aurelie's English Practice",
    page_icon="📚",
    layout="centered"
)

# --- Custom CSS ---
st.markdown("""
<style>
    .stApp {
        max-width: 800px;
        margin: 0 auto;
    }
    .correct {
        background-color: #d4edda;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #28a745;
    }
    .incorrect {
        background-color: #f8d7da;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #dc3545;
    }
    .exercise-box {
        background-color: #f8f9fa;
        padding: 1.5rem;
        border-radius: 0.5rem;
        margin: 1rem 0;
    }
    .streak {
        font-size: 1.5rem;
        color: #fd7e14;
    }
</style>
""", unsafe_allow_html=True)

# --- Helper Functions ---

def load_lernstand():
    """Lädt den aktuellen Lernstand."""
    path = BASE_PATH / "progress" / "lernstand.md"
    if path.exists():
        return path.read_text()
    return None

def load_error_patterns():
    """Lädt die Fehlermuster."""
    path = BASE_PATH / "progress" / "error-patterns.md"
    if path.exists():
        return path.read_text()
    return None

def get_exercise_from_claude(client, lernstand, error_patterns, exercise_num, total, active_error_patterns=None, selected_topic=None, due_items=None):
    """Generiert eine Übung mit Claude API.

    Implementiert Interleaving: Mischt verschiedene Themen statt nur ein Thema zu wiederholen.
    Priorisiert: 1. Due Items (Spaced Repetition), 2. Selected Topic, 3. Aktive Fehlermuster, 4. Zufällig
    """

    # Lade Übungen aus JSON-Dateien (320 Übungen in 8 Topics)
    sentence_templates = get_all_exercises_as_templates()

    # Fallback auf minimale hardcoded Templates falls JSON nicht geladen werden kann
    if not sentence_templates:
        sentence_templates = [
            ("Yesterday, I ___ (go) to school.", "go", "went", "go → went → gone", "simple_past_irregular"),
            ("I have ___ (go) to Paris twice.", "go", "gone", "Present Perfect: have/has + gone", "present_perfect"),
        ]

    # ===== TOPIC MAPPING für JSON-basierte Filterung =====
    # WICHTIG: Reihenfolge matters! Spezifischere Matches ZUERST prüfen
    # Verwende exact match statt substring, um Doppel-Matching zu vermeiden
    topic_to_json_keys_exact = {
        # Exact matches from dropdown (case-insensitive)
        "simple past regular": ["simple_past_regular"],
        "simple past irregular": ["simple_past_irregular"],
        "present perfect": ["present_perfect"],
        "past vs perfect": ["past_vs_perfect"],
        "going-to future": ["going_to_future"],
        "will future": ["will_future"],
        "comparison": ["comparison_adjectives"],
        "adverbs": ["adverbs"],
    }
    # Fallback substring matches (nur wenn kein exact match)
    topic_to_json_keys_fallback = {
        "past simple": ["simple_past_regular", "simple_past_irregular"],
        "simple past": ["simple_past_regular", "simple_past_irregular"],
        "going to future": ["going_to_future"],
        "adjectives": ["comparison_adjectives"],
        "irregular verbs": ["simple_past_irregular", "present_perfect"],
        "irregular": ["simple_past_irregular", "present_perfect"],
    }

    # ===== THEMA-FILTERUNG + PRIORITÄT LOGIK =====
    # 1. Due Items (Spaced Repetition - HÖCHSTE PRIORITÄT)
    # 2. Selected Topic (vom Dropdown)
    # 3. Aktive Fehlermuster
    # 4. Zufällig aus allen

    filtered_templates = sentence_templates  # Default: alle

    # due_items ist jetzt ein dict: {"verbs": [...], "topics": [...], "all": [...]}
    due_verbs = due_items.get("verbs", []) if isinstance(due_items, dict) else due_items or []
    due_topics = due_items.get("topics", []) if isinstance(due_items, dict) else []

    # HÖCHSTE PRIORITÄT: Spaced Repetition Due Items (jede 2. Übung wenn vorhanden)
    if (due_verbs or due_topics) and exercise_num % 2 == 0:
        due_templates = []

        # 1. Filtere auf fällige Verben
        if due_verbs:
            due_templates.extend([t for t in sentence_templates if t[1] in due_verbs])

        # 2. Filtere auf fällige Topics (topic_key ist Index 4)
        if due_topics:
            # Konvertiere Topic-Display-Namen zu JSON-Keys
            topic_display_to_key = {
                "Past Simple - Irregular Verbs": "simple_past_irregular",
                "Past Simple - Regular Verbs": "simple_past_regular",
                "Present Perfect": "present_perfect",
                "Past vs Perfect (Signal Words)": "past_vs_perfect",
                "Going-to Future": "going_to_future",
                "Will Future": "will_future",
                "Comparison of Adjectives": "comparison_adjectives",
                "Adverbs": "adverbs",
            }
            due_topic_keys = [topic_display_to_key.get(t, t.lower().replace(" ", "_")) for t in due_topics]
            due_templates.extend([t for t in sentence_templates if t[4] in due_topic_keys])

        if due_templates:
            filtered_templates = due_templates

    # ZWEITE PRIORITÄT: Selected Topic (vom User-Dropdown)
    elif selected_topic:
        topic_lower = selected_topic.lower()

        # Finde passende JSON topic keys - EXACT MATCH FIRST
        matching_keys = []

        # 1. Versuche exact match (um "simple past regular" nicht mit "simple past" zu matchen)
        if topic_lower in topic_to_json_keys_exact:
            matching_keys = topic_to_json_keys_exact[topic_lower]
        else:
            # 2. Fallback: substring match für generische Begriffe
            for search_term, json_keys in topic_to_json_keys_fallback.items():
                if search_term in topic_lower:
                    matching_keys.extend(json_keys)
                    break  # Nur ersten Match nehmen

        if matching_keys:
            # Filtere auf passende Topics (topic_key ist jetzt Index 4)
            # Dedupliziere matching_keys
            matching_keys = list(set(matching_keys))
            filtered_templates = [t for t in sentence_templates if t[4] in matching_keys]

        # Fallback: wenn keine Templates gefunden, alle nehmen
        if not filtered_templates:
            filtered_templates = sentence_templates

    # Priorisierung alle 3 Übungen: Fehlermuster einstreuen
    if exercise_num % 3 == 0 and not selected_topic:
        # Aktive Fehlermuster - MIT SPEZIFISCHEN PROBLEM-VERBEN
        if active_error_patterns and active_error_patterns.get("problem_verbs"):
            # Nutze nur die spezifischen Verben die Probleme verursacht haben
            pattern_verbs = active_error_patterns["problem_verbs"]
            if pattern_verbs:
                # Filtere Templates auf genau diese Problem-Verben
                filtered_templates = [t for t in sentence_templates if t[1] in pattern_verbs]
                # Fallback: wenn keine Templates gefunden, alle nehmen
                if not filtered_templates:
                    filtered_templates = sentence_templates

    # Wähle eine zufällige Vorlage aus der (evtl. gefilterten) Liste
    template = random.choice(filtered_templates)
    question, verb, correct_answer, hint, topic_key = template

    # Bestimme menschenlesbares Topic für die Anzeige
    topic_display_names = {
        "simple_past_regular": "Past Simple - Regular Verbs",
        "simple_past_irregular": "Past Simple - Irregular Verbs",
        "present_perfect": "Present Perfect",
        "past_vs_perfect": "Past vs Perfect (Signal Words)",
        "going_to_future": "Going-to Future",
        "will_future": "Will Future",
        "comparison_adjectives": "Comparison of Adjectives",
        "adverbs": "Adverbs",
    }
    topic = topic_display_names.get(topic_key, topic_key.replace("_", " ").title())

    prompt = f"""Du bist ein freundlicher Englisch-Lehrer für Aurelie, eine 12-jährige Schülerin (6. Klasse).

Ich gebe dir einen fertigen Übungssatz. Erstelle NUR das JSON mit einer hilfreichen Erklärung.

ÜBUNGSSATZ: {question}
VERB: {verb}
RICHTIGE ANTWORT: {correct_answer}
HINT: {hint}
TOPIC: {topic}

WICHTIG für die Erklärung - gib einen ECHTEN TRICK, nicht nur die Formen!:
- SCHLECHT: "swim → swam → swum" (das ist kein Trick, nur auswendig lernen)
- GUT: "swIm-swAm-swUm: Die Vokale gehen I-A-U, wie im Alphabet!" (DAS ist ein Trick!)
- GUT: "GO und WENT sehen total anders aus - wie Clark Kent und Superman!"
- GUT: "EAT-ATE: Stell dir vor, du isst (eat) einen Kuchen und sagst 'Acht!' (ate klingt wie 8)"
- Schreibe wie ein netter Lehrer, der mit einer 12-Jährigen spricht
- Max 2 kurze Sätze, ein echter Merktrick!

FORMAT (nur JSON, nichts anderes):
{{
    "topic": "{topic}",
    "difficulty": 3,
    "question": "{question}",
    "correct_answer": "{correct_answer}",
    "hint": "{hint}",
    "explanation": "[Deine kinderfreundliche Erklärung - max 2 Sätze]"
}}"""

    try:
        response = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
    except anthropic.APIConnectionError:
        # Netzwerkfehler - nutze Fallback
        return _get_fallback_exercise(question, correct_answer, hint, topic)
    except anthropic.RateLimitError:
        # Rate Limit - nutze Fallback
        return _get_fallback_exercise(question, correct_answer, hint, topic)
    except anthropic.APIStatusError as e:
        # API Fehler - nutze Fallback
        print(f"API Status Error: {e.status_code}")
        return _get_fallback_exercise(question, correct_answer, hint, topic)
    except Exception as e:
        # Unerwarteter Fehler
        print(f"Unerwarteter API-Fehler: {e}")
        return _get_fallback_exercise(question, correct_answer, hint, topic)

    try:
        # Claude gibt Text in content[0].text zurück
        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())
    except (json.JSONDecodeError, IndexError, AttributeError) as e:
        # JSON Parsing Fehler - nutze die vorgefertigte Übung
        print(f"JSON Parsing Fehler: {e}")
        return _get_fallback_exercise(question, correct_answer, hint, topic)


def _get_fallback_exercise(question, correct_answer, hint, topic):
    """Gibt die vorbereitete Übung zurück mit echten Merktricks."""
    # ECHTE Eselsbrücken - keine langweiligen Formen, sondern Bilder und Geschichten!
    verb_tricks = {
        # GO
        "went": "🦸 GO wird zu WENT - wie Clark Kent zu Superman! Gleiche Person, komplett anderes Aussehen. WENT hat nichts mit GO zu tun - einfach merken als 'Spezialfall'!",
        "gone": "🐉 GONE reimt sich auf 'dragon' (Drache). Stell dir vor: Der Drache ist weg-ge-GONE! Bei 'have/has' immer GONE, nie went!",

        # SWIM
        "swam": "🏊 swIm → swAm → swUm: Die Vokale gehen I-A-U! Wie wenn du tauchst und Luftblasen machst: 'I...A...U!' SWAM = gestern geschwommen.",
        "swum": "🏊 swIm → swAm → swUm: I-A-U! Bei 'have/has' immer SWUM: 'I have swum' = Ich bin geschwommen.",

        # EAT
        "ate": "🍪 ATE spricht man wie '8' (eight)! Merksatz: 'I ATE 8 cookies!' = Ich aß 8 Kekse! ATE = gestern gegessen.",
        "eaten": "🍽️ Bei 'have/has' kommt EATEN (mit -en am Ende). EATEN klingt wie 'Essen' auf Deutsch! 'I have eaten' = Ich habe gegessen.",

        # RUN
        "ran": "🏃 RUN → RAN: Wenn du rennst, geht dir die Puste aus: 'Raaaaan!' Das U wird zum A. RAN = gestern gerannt.",
        "run": "🏃 Überraschung! Bei 'have/has' bleibt RUN gleich: 'I have run' = Ich bin gerannt. Kein neues Wort nötig!",

        # TAKE
        "took": "👀 TAKE → TOOK: Die zwei OO sehen aus wie große Augen! Du NIMMST etwas und guckst mit großen Augen: 'Oooh!' TOOK = gestern genommen.",
        "taken": "✋ Bei 'have/has' kommt TAKEN: 'I have taken' = Ich habe genommen. Merke: -EN am Ende für Present Perfect!",

        # WRITE
        "wrote": "✍️ WRITE → WROTE: Das I wird zum O - wie ein Tintenklecks (Kreis) auf dem Papier! WROTE = gestern geschrieben.",
        "written": "📝 Bei 'have/has' kommt WRITTEN (mit Doppel-T!): 'I have written' = Ich habe geschrieben.",

        # SEE
        "saw": "🪚 SEE → SAW: SAW ist auch 'Säge'! Merksatz: 'Ich SAH eine Säge!' SAW = gestern gesehen.",
        "seen": "👁️ Bei 'have/has' bleibt das doppelte E: SEEN! 'I have seen' = Ich habe gesehen.",

        # COME
        "came": "🚪 COME → CAME: Nur O wird zu A! Super einfach. CAME = gestern gekommen.",
        "come": "🏠 Überraschung! Bei 'have/has' bleibt COME gleich: 'I have come' = Ich bin gekommen.",

        # DO
        "did": "✅ DO → DID: Kurz und einfach! DID für alles in der Vergangenheit. 'I did my homework' = Ich machte meine Hausaufgaben.",
        "done": "🎯 Bei 'have/has' kommt DONE: 'I have done' = Ich habe gemacht. DONE = fertig, erledigt!",

        # MAKE
        "made": "🎨 MAKE → MADE: Das K fällt weg, E kommt dazu. Klingt fast gleich! MADE = gestern gemacht.",

        # BUY
        "bought": "🛒 BUY → BOUGHT: Das sieht wild aus! Aber: 'brought' (bringen) und 'bought' (kaufen) reimen sich. BOUGHT = gestern gekauft.",

        # FIND
        "found": "🔍 FIND → FOUND: Das I wird zu OU. FOUND klingt wie 'Pfund' - du findest einen Schatz! FOUND = gestern gefunden.",

        # GET
        "got": "📦 GET → GOT: E wird zu O. Kurz und einfach! GOT = gestern bekommen.",

        # GIVE
        "given": "🎁 Bei 'have/has' kommt GIVEN: 'I have given' = Ich habe gegeben. GIVE + N = GIVEN!",
        "gave": "🎁 GIVE → GAVE: I wird zu A. 'I gave you a gift' = Ich gab dir ein Geschenk. GAVE = gestern gegeben.",

        # KNOW
        "knew": "🧠 KNOW → KNEW: Das stumme K bleibt! KNEW reimt sich auf 'new' (neu). KNEW = wusste gestern.",
        "known": "💡 Bei 'have/has' kommt KNOWN: 'I have known' = Ich habe gewusst. Das stumme K bleibt immer!",
    }

    # Suche nach passendem Trick
    explanation = verb_tricks.get(correct_answer.lower(), f"💡 Merke: {hint}")

    return {
        "topic": topic,
        "difficulty": 3,
        "question": question,
        "correct_answer": correct_answer,
        "hint": hint,
        "explanation": explanation
    }

def check_answer(user_answer, correct_answer):
    """Prüft die Antwort - exakt, keine Tippfehler-Toleranz bei Grammatikübungen."""
    if not user_answer or not correct_answer:
        return False

    user = user_answer.lower().strip()
    correct = correct_answer.lower().strip()

    if not user or not correct:
        return False

    return user == correct


def explain_vocabulary(word, api_client=None):
    """Erklärt ein englisches Wort kindgerecht auf Deutsch.

    api_client wird beim Aufruf übergeben (damit es nach Initialisierung verfügbar ist).
    """
    if not word or not word.strip():
        return None

    # Sicherheit: Wort auf max. 50 Zeichen begrenzen
    word = word.strip()[:50].lower()

    # LOKALES DICTIONARY aus JSON-Dateien (480 Vokabeln + 59 Verben)
    local_vocab = get_vocabulary_dict()

    # Zuerst im lokalen Dictionary suchen
    if word in local_vocab:
        return local_vocab[word]

    # Kein API client? Kann nicht weiter helfen
    if api_client is None:
        return None

    # Fallback: API-Call für unbekannte Wörter
    prompt = f"""Was bedeutet "{word}" auf Deutsch?

WICHTIG - Antworte GENAU so:
1. ZUERST die deutsche Übersetzung (ein Wort!)
2. DANN ein kurzes Beispiel

BEISPIELE wie du antworten sollst:
- "night" → "Nacht. 'Last night' = Letzte Nacht."
- "swim" → "Schwimmen. 'I swim' = Ich schwimme. (swim-swam-swum)"
- "dishes" → "Geschirr. 'Do the dishes' = Geschirr spülen."
- "went" → "Ging (von 'go'). 'I went home' = Ich ging nach Hause."
- "movie" → "Film. 'a great movie' = ein toller Film."

Antworte NUR mit: Übersetzung. Beispiel."""

    try:
        response = api_client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text.strip()
    except Exception as e:
        print(f"Vokabel-Erklärung Fehler: {e}")
        return None


def extract_from_school_material(image_bytes):
    """Extrahiert Vokabeln und Grammatik aus einem Foto von Schulmaterial."""
    import base64

    # Bild zu Base64 konvertieren
    image_base64 = base64.b64encode(image_bytes).decode("utf-8")

    prompt = """Analysiere dieses Foto von Englisch-Schulmaterial.

WICHTIG: Extrahiere ALLES was du siehst!

## 1. GRAMMATIK-PRINZIPIEN (am wichtigsten!)
Schreibe die Regeln AUS, die auf dem Blatt stehen:
- Wie bildet man die Zeit? (z.B. "have/has + Past Participle")
- Wann benutzt man was? (z.B. "Present Perfect für Erfahrungen")
- Signalwörter? (z.B. "ever, never, already, yet")
- Beispielsätze die erklärt werden

## 2. VOKABELN
Englisch: Deutsch
- Nur wenn Wortpaare auf dem Blatt stehen

## 3. VERBEN-FORMEN
Falls unregelmäßige Verben gezeigt werden:
go - went - gone
eat - ate - eaten
(alle die du siehst)

## 4. ÜBUNGSTYPEN
Was für Aufgaben sind das? (Lückentext, Übersetzen, etc.)

Schreibe ALLES auf was du lesen kannst - auch wenn es unvollständig ist!"""

    try:
        response = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=1000,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_base64
                        }
                    },
                    {
                        "type": "text",
                        "text": prompt
                    }
                ]
            }]
        )
        return response.content[0].text.strip()
    except Exception as e:
        print(f"Bild-Analyse Fehler: {e}")
        return None


def save_extracted_vocabulary(extraction_text):
    """Speichert extrahierte Vokabeln ins Curriculum."""
    curriculum_path = BASE_PATH / "curriculum" / "vocabulary"
    curriculum_path.mkdir(parents=True, exist_ok=True)

    filename = f"imported-{datetime.now().strftime('%Y-%m-%d-%H%M')}.md"

    content = f"""# Importierte Vokabeln ({datetime.now().strftime('%Y-%m-%d %H:%M')})

> Automatisch extrahiert aus Schulmaterial-Foto

---

{extraction_text}

---

**Importiert am**: {datetime.now().strftime('%Y-%m-%d %H:%M')}
"""

    try:
        (curriculum_path / filename).write_text(content)
        return filename
    except Exception as e:
        print(f"Fehler beim Speichern: {e}")
        return None


def save_session_result(results):
    """Speichert die Session-Ergebnisse in Supabase.

    SICHER: Gibt None zurück wenn DB nicht verfügbar - App läuft weiter.
    """
    try:
        correct = sum(1 for r in results if r.get("correct", False))
        total = len(results)
        best_streak = st.session_state.get("best_streak", 0)

        # Details als JSON speichern (mit User für Filterung)
        details = {
            "user_id": get_current_user(),
            "exercises": results,
            "timestamp": datetime.now().isoformat()
        }

        query = """
            INSERT INTO session_results (session_date, total_exercises, correct, best_streak, details)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """
        result = db_query(query, (datetime.now().date(), total, correct, best_streak, json.dumps(details)), fetch=True)

        if result:
            return f"session-{result[0]['id']}"
    except Exception:
        pass  # DB nicht verfügbar - kein Problem
    return None


def save_feedback(exercise, user_answer, feedback_text):
    """Speichert Feedback zu einer Übung in Supabase."""
    if not feedback_text or not feedback_text.strip():
        return False

    query = """
        INSERT INTO feedback (exercise_question, exercise_topic, correct_answer, user_answer, feedback_text)
        VALUES (%s, %s, %s, %s, %s)
    """
    db_query(
        query,
        (
            exercise.get("question", ""),
            exercise.get("topic", ""),
            exercise.get("correct_answer", ""),
            user_answer or "",
            feedback_text.strip()
        ),
        fetch=False
    )
    return True

def detect_error_pattern(user_answer, correct_answer, verb):
    """Erkennt das Fehlermuster basierend auf der falschen Antwort."""
    # Edge Case: None oder leere Werte
    user = (user_answer or "").lower().strip()
    correct = (correct_answer or "").lower().strip()
    verb = verb or "unknown"

    # Pattern: Reguläre -ed Endung bei irregulären Verben (goed, swimmed, eated)
    if user.endswith("ed") and not correct.endswith("ed"):
        return {
            "pattern": "irregular-past-regularization",
            "description": f"Reguläre -ed Endung bei '{verb}' benutzt",
            "example": f"{user} statt {correct}",
            "verb": verb
        }

    # Pattern: Present Perfect Verwechslung (has went statt has gone)
    if "went" in user and "gone" in correct:
        return {
            "pattern": "present-perfect-confusion",
            "description": "Past Simple Form im Present Perfect benutzt",
            "example": f"{user} statt {correct}",
            "verb": verb
        }

    # Pattern: Tense Mixing
    if correct.endswith("ed") and not user.endswith("ed") and user == verb:
        return {
            "pattern": "tense-mixing",
            "description": "Grundform statt Past Simple benutzt",
            "example": f"{user} statt {correct}",
            "verb": verb
        }

    # Allgemeiner Fehler
    return {
        "pattern": "general-error",
        "description": f"Falsches Verb für '{verb}'",
        "example": f"{user} statt {correct}",
        "verb": verb
    }


def explain_why_wrong(user_answer, correct_answer, question):
    """
    Erklärt WARUM die Antwort des Users falsch ist - nicht nur was richtig wäre.
    Analysiert den grammatikalischen Kontext der Frage.
    """
    user = (user_answer or "").lower().strip()
    correct = (correct_answer or "").lower().strip()
    q_lower = question.lower()

    # === PAST SIMPLE vs PRESENT PERFECT ===

    # User schrieb Present Perfect (has/have + participle), aber Past Simple war gefragt
    past_simple_markers = ["yesterday", "last week", "last month", "last year",
                          "ago", "last monday", "last tuesday", "last wednesday",
                          "last thursday", "last friday", "last saturday", "last sunday",
                          "in 2023", "in 2022", "when i was"]

    has_past_marker = any(marker in q_lower for marker in past_simple_markers)
    user_is_present_perfect = user.startswith("has ") or user.startswith("have ") or "has " in user or "have " in user

    if has_past_marker and user_is_present_perfect:
        # Finde welcher Zeit-Marker in der Frage steht
        found_marker = next((m for m in past_simple_markers if m in q_lower), "")
        return f"""**Warum "{user}" hier falsch ist:**

Du hast Present Perfect benutzt (has/have + Partizip).
Aber in der Frage steht "**{found_marker}**" - das ist ein bestimmter Zeitpunkt in der Vergangenheit!

📚 **Die Regel:**
- **Past Simple** (took, went, ate) = bestimmter Zeitpunkt: *yesterday*, *last week*, *two days ago*
- **Present Perfect** (has taken, has gone) = KEIN bestimmter Zeitpunkt: *I have seen this film* (wann? - egal!)

➡️ Bei "**{found_marker}**" brauchst du immer **Past Simple**!"""

    # User schrieb Past Simple, aber Present Perfect war gefragt
    present_perfect_markers = ["already", "just", "ever", "never", "yet", "so far",
                               "since", "for three", "for two", "recently", "lately"]

    has_pp_marker = any(marker in q_lower for marker in present_perfect_markers)
    user_is_past_simple = not user_is_present_perfect and correct.startswith("has ") or correct.startswith("have ")

    if has_pp_marker and user_is_past_simple:
        found_marker = next((m for m in present_perfect_markers if m in q_lower), "")
        return f"""**Warum "{user}" hier falsch ist:**

Du hast Past Simple benutzt.
Aber in der Frage steht "**{found_marker}**" - das ist ein Signalwort für Present Perfect!

📚 **Die Regel:**
- **Present Perfect** (has/have + Partizip) = bei *already*, *just*, *ever*, *never*, *yet*, *since*, *for*
- **Past Simple** = bei *yesterday*, *last week*, *ago*

➡️ Bei "**{found_marker}**" brauchst du **Present Perfect** (has/have + 3. Form)!"""

    # === IRREGULÄRE VERBEN ===

    # User hat -ed angehängt bei irregulären Verb
    if user.endswith("ed") and not correct.endswith("ed"):
        # Verb aus Klammern extrahieren
        verb_match = re.search(r'\((\w+)\)', question)
        verb = verb_match.group(1) if verb_match else "dieses Verb"
        return f"""**Warum "{user}" hier falsch ist:**

Du hast die regelmäßige -ed Endung benutzt.
Aber "**{verb}**" ist ein **unregelmäßiges Verb**!

📚 **Unregelmäßige Verben haben KEINE -ed Endung!**
Sie haben eigene Formen die du auswendig lernen musst.

✅ Richtig: **{correct}**
❌ Falsch: {user}

💡 **Tipp:** Lerne die drei Formen: {verb} → {correct} → ..."""

    # === GRUNDFORM STATT KONJUGIERTER FORM ===

    verb_match = re.search(r'\((\w+)\)', question)
    verb = verb_match.group(1).lower() if verb_match else ""

    if user == verb and correct != verb:
        # Erkenne welche Zeit gefragt war anhand der richtigen Antwort
        if correct.startswith("will "):
            return f"""**Warum "{user}" hier falsch ist:**

Du hast nur die **Grundform** geschrieben, aber hier brauchen wir **Will Future**!

📚 **Will Future** = **will + Grundform**
- Für spontane Entscheidungen, Versprechen, Vorhersagen

✅ Richtig: **{correct}**
❌ Nur Grundform: {user}

💡 Merke: Bei "I think", "I promise", "probably" → immer **will + Verb**!"""
        elif "going to" in correct:
            return f"""**Warum "{user}" hier falsch ist:**

Du hast nur die **Grundform** geschrieben, aber hier brauchen wir **Going-to Future**!

📚 **Going-to Future** = **am/is/are + going to + Grundform**
- Für Pläne und erkennbare Anzeichen

✅ Richtig: **{correct}**
❌ Nur Grundform: {user}"""
        else:
            return f"""**Warum "{user}" hier falsch ist:**

Du hast die **Grundform** geschrieben, aber die Frage braucht eine andere Zeitform!

Schau auf die Zeitangaben in der Frage - sie zeigen dir welche Zeit gebraucht wird.

✅ Richtig: **{correct}**
❌ Grundform: {user}"""

    # === FALLBACK: Allgemeine Erklärung ===
    return None  # Nutze dann die normale Erklärung


def update_error_patterns(results):
    """Aktualisiert die error_patterns Tabelle in Supabase."""
    # Falsche Antworten sammeln
    errors = []
    for r in results:
        if not r.get("correct", False):
            question = r.get("question", "")
            verb_match = re.search(r'\((\w+)\)', question)
            verb = verb_match.group(1) if verb_match else "unknown"

            pattern = detect_error_pattern(
                r.get("user_answer", ""),
                r.get("correct_answer", ""),
                verb
            )
            errors.append(pattern)

    if not errors:
        return

    today = datetime.now().date()

    for error in errors:
        # Prüfen ob Pattern schon existiert
        existing = db_query(
            "SELECT id, occurrences FROM error_patterns WHERE pattern = %s AND verb = %s",
            (error["pattern"], error["verb"])
        )

        if existing:
            # Vorkommen erhöhen
            new_count = existing[0]['occurrences'] + 1
            new_status = "AKTIV" if new_count >= 3 else "BEOBACHTEN"
            db_query(
                "UPDATE error_patterns SET occurrences = %s, status = %s, last_seen = %s WHERE id = %s",
                (new_count, new_status, today, existing[0]['id']),
                fetch=False
            )
        else:
            # Neues Pattern einfügen
            db_query(
                """INSERT INTO error_patterns (pattern, description, example, verb, occurrences, status, last_seen)
                   VALUES (%s, %s, %s, %s, 1, 'BEOBACHTEN', %s)""",
                (error["pattern"], error["description"], error["example"], error["verb"], today),
                fetch=False
            )

def update_spaced_repetition(results):
    """Aktualisiert die spaced_repetition Tabelle in Supabase.

    Trackt ZWEI Dinge:
    1. Verben (aus der Klammer) - für irreguläre Verben
    2. Topics (Will Future, Comparison, etc.) - für Grammatik-Themen
    """
    # SM-2 Intervalle: 1 → 3 → 7 → 14 → 30 → 60 Tage
    intervals = [1, 3, 7, 14, 30, 60]

    # === 1. VERBEN TRACKEN (wie bisher) ===
    practiced_verbs = {}
    for r in results:
        verb_match = re.search(r'\((\w+)\)', r["question"])
        if verb_match:
            verb = verb_match.group(1)
            if verb not in practiced_verbs:
                practiced_verbs[verb] = {"correct": 0, "wrong": 0}
            if r["correct"]:
                practiced_verbs[verb]["correct"] += 1
            else:
                practiced_verbs[verb]["wrong"] += 1

    for verb, stats in practiced_verbs.items():
        _update_sr_item(verb, "Irregular Verbs", stats, intervals)

    # === 2. TOPICS TRACKEN (NEU!) ===
    # Gruppiere Ergebnisse nach Topic
    practiced_topics = {}
    for r in results:
        topic = r.get("topic", "unknown")
        # Normalisiere Topic-Namen für konsistentes Tracking
        topic_key = f"topic:{topic}"  # Prefix um Verben/Topics zu unterscheiden

        if topic_key not in practiced_topics:
            practiced_topics[topic_key] = {"correct": 0, "wrong": 0, "display_name": topic}
        if r["correct"]:
            practiced_topics[topic_key]["correct"] += 1
        else:
            practiced_topics[topic_key]["wrong"] += 1

    # NUR Topics mit Fehlern ins SR aufnehmen (nicht alle)
    for topic_key, stats in practiced_topics.items():
        if stats["wrong"] > 0:  # Nur wenn Fehler gemacht wurden
            _update_sr_item(topic_key, stats["display_name"], stats, intervals)


def _update_sr_item(item, topic, stats, intervals):
    """Hilfsfunktion: Aktualisiert ein einzelnes SR-Item."""
    # User-Präfix für Isolation der Daten
    user_id = get_current_user()
    prefixed_item = f"{user_id}:{item}" if user_id != "aurelie" else item

    existing = db_query(
        "SELECT id, interval_days FROM spaced_repetition WHERE item = %s",
        (prefixed_item,)
    )

    if existing:
        current_interval = existing[0]['interval_days']

        # Bestimme nächstes Intervall
        if stats["correct"] > stats["wrong"]:
            try:
                current_index = intervals.index(current_interval)
                next_interval = intervals[min(current_index + 1, len(intervals) - 1)]
            except ValueError:
                next_interval = next((i for i in intervals if i > current_interval), 60)
            status = "mastered" if next_interval >= 60 else "active"
        else:
            next_interval = 1
            status = "active"

        next_date = datetime.now().date() + timedelta(days=next_interval)

        db_query(
            "UPDATE spaced_repetition SET interval_days = %s, next_review = %s, status = %s WHERE id = %s",
            (next_interval, next_date, status, existing[0]['id']),
            fetch=False
        )
    else:
        # Neues Item einfügen
        next_date = datetime.now().date() + timedelta(days=1)
        db_query(
            """INSERT INTO spaced_repetition (item, topic, interval_days, next_review, status)
               VALUES (%s, %s, 1, %s, 'active')""",
            (prefixed_item, topic, next_date),
            fetch=False
        )

def get_active_error_patterns():
    """Holt aktive Fehlermuster aus Supabase für gezielte Übungen.

    Returns:
        dict: {"pattern_names": [...], "problem_verbs": [...]}
    """
    try:
        result = db_query("SELECT pattern, verb FROM error_patterns WHERE status = 'AKTIV'")

        if not result:
            return {"pattern_names": [], "problem_verbs": []}

        pattern_names = list(set(r['pattern'] for r in result))
        problem_verbs = list(set(r['verb'] for r in result if r['verb']))

        return {"pattern_names": pattern_names, "problem_verbs": problem_verbs}
    except Exception:
        return {"pattern_names": [], "problem_verbs": []}

def get_due_items():
    """Holt heute fällige Spaced Repetition Items aus Supabase.

    Returns:
        dict: {
            "verbs": ["eat", "swim", ...],  # Für Verb-Filterung
            "topics": ["Will Future", ...],  # Für Topic-Filterung
            "all": ["eat", "topic:Will Future", ...]  # Für Anzeige
        }
    """
    try:
        today = datetime.now().date()
        user_id = get_current_user()

        # Filtere nach User-Präfix oder unpräfixierte Items (für Aurelie-Kompatibilität)
        if user_id == "aurelie":
            # Aurelie: alle Items ohne Präfix
            result = db_query(
                "SELECT item, topic FROM spaced_repetition WHERE status = 'active' AND next_review <= %s AND item NOT LIKE '%:%'",
                (today,)
            )
        else:
            # Andere User: nur Items mit ihrem Präfix
            prefix = f"{user_id}:%"
            result = db_query(
                "SELECT item, topic FROM spaced_repetition WHERE status = 'active' AND next_review <= %s AND item LIKE %s",
                (today, prefix)
            )

        if not result:
            return {"verbs": [], "topics": [], "all": []}

        verbs = []
        topics = []
        all_items = []

        for r in result:
            item = r['item']
            # Entferne User-Präfix für Anzeige
            display_item = item.split(":", 1)[-1] if ":" in item and not item.startswith("topic:") else item

            all_items.append(display_item)

            if item.startswith("topic:") or (user_id != "aurelie" and ":topic:" in item):
                # Topic-Item: extrahiere den Topic-Namen
                topic_name = item.replace("topic:", "").replace(f"{user_id}:topic:", "")
                topics.append(topic_name)
            else:
                # Verb-Item
                verbs.append(display_item)

        return {"verbs": verbs, "topics": topics, "all": all_items}
    except Exception:
        return {"verbs": [], "topics": [], "all": []}


# --- Engagement System Functions ---

def get_current_user():
    """Gibt den aktuell ausgewählten User zurück."""
    return st.session_state.get('current_user', 'aurelie')


def get_user_stats():
    """Holt die User-Statistiken (Streak, XP, Level)."""
    user_id = get_current_user()
    try:
        result = db_query("SELECT * FROM user_stats WHERE user_id = %s", (user_id,))
        if result:
            return result[0]
        # Fallback: Create default entry
        db_query(
            "INSERT INTO user_stats (user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING",
            (user_id,),
            fetch=False
        )
    except Exception as e:
        # Table doesn't exist yet - return defaults
        pass

    return {
        'current_streak': 0,
        'longest_streak': 0,
        'total_xp': 0,
        'level': 1,
        'last_practice_date': None,
        'streak_freeze_available': True
    }


def update_daily_streak():
    """Aktualisiert den täglichen Streak basierend auf dem Übungsdatum."""
    try:
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)

        stats = get_user_stats()
        last_practice = stats.get('last_practice_date')
        current_streak = stats.get('current_streak', 0)
        longest_streak = stats.get('longest_streak', 0)
    except Exception:
        return 0  # Table doesn't exist yet

    # Konvertiere last_practice zu date wenn nötig
    if last_practice:
        if isinstance(last_practice, str):
            last_practice = datetime.fromisoformat(last_practice.replace('Z', '+00:00')).date()
        elif hasattr(last_practice, 'date'):
            last_practice = last_practice.date() if callable(getattr(last_practice, 'date', None)) else last_practice

    if last_practice == today:
        # Schon heute geübt - nichts ändern
        return current_streak
    elif last_practice == yesterday:
        # Gestern geübt - Streak fortsetzen
        new_streak = current_streak + 1
    elif last_practice and last_practice < yesterday:
        # Mehr als 1 Tag Pause - Streak zurücksetzen (außer Freeze verfügbar)
        if stats.get('streak_freeze_available', False):
            # Streak Freeze verwenden
            db_query(
                """UPDATE user_stats SET
                   streak_freeze_available = FALSE,
                   streak_freeze_used_date = %s,
                   last_practice_date = %s,
                   updated_at = NOW()
                   WHERE user_id = %s""",
                (yesterday, today, get_current_user()),
                fetch=False
            )
            return current_streak  # Streak bleibt erhalten
        else:
            new_streak = 1  # Reset auf 1 (heute ist Tag 1)
    else:
        # Erster Tag oder keine Daten
        new_streak = 1

    # Longest Streak aktualisieren
    if new_streak > longest_streak:
        longest_streak = new_streak

    # Datenbank aktualisieren
    db_query(
        """UPDATE user_stats SET
           current_streak = %s,
           longest_streak = %s,
           last_practice_date = %s,
           updated_at = NOW()
           WHERE user_id = %s""",
        (new_streak, longest_streak, today, get_current_user()),
        fetch=False
    )

    return new_streak


def award_xp(amount, xp_type, session_id=None):
    """Vergibt XP und aktualisiert das Gesamtkonto."""
    user_id = get_current_user()
    try:
        # XP zum Log hinzufügen
        db_query(
            """INSERT INTO xp_log (user_id, xp_amount, xp_type, source_session_id)
               VALUES (%s, %s, %s, %s)""",
            (user_id, amount, xp_type, session_id),
            fetch=False
        )

        # Gesamt-XP und Level aktualisieren
        db_query(
            """UPDATE user_stats SET
               total_xp = total_xp + %s,
               level = GREATEST(1, (total_xp + %s) / 500 + 1),
               updated_at = NOW()
               WHERE user_id = %s""",
            (amount, amount, user_id),
            fetch=False
        )
    except Exception:
        pass  # Table doesn't exist yet


def calculate_session_xp(results, best_streak):
    """Berechnet XP für eine Session.

    XP System:
    - +10 XP pro richtige Antwort
    - +5 XP Streak-Bonus pro Antwort in Folge (ab 3)
    - +50 XP für perfekte Session (100%)
    - +25 XP für gute Session (≥80%)
    """
    total_xp = 0
    xp_breakdown = []

    correct_count = sum(1 for r in results if r.get('correct', False))
    total_count = len(results)
    accuracy = (correct_count / total_count * 100) if total_count > 0 else 0

    # Basis-XP für richtige Antworten
    base_xp = correct_count * 10
    total_xp += base_xp
    xp_breakdown.append(f"+{base_xp} XP ({correct_count} richtige Antworten)")

    # Streak-Bonus (ab 3er Streak)
    if best_streak >= 3:
        streak_bonus = (best_streak - 2) * 5  # +5 für jeden über 2
        total_xp += streak_bonus
        xp_breakdown.append(f"+{streak_bonus} XP (🔥 {best_streak}er Streak)")

    # Perfekte Session Bonus
    if accuracy == 100 and total_count >= 5:
        total_xp += 50
        xp_breakdown.append("+50 XP (🏆 Perfekte Session!)")
    # Gute Session Bonus
    elif accuracy >= 80:
        total_xp += 25
        xp_breakdown.append("+25 XP (⭐ Gute Session)")

    return total_xp, xp_breakdown


def check_and_unlock_achievements(stats, session_results=None):
    """Prüft und schaltet Achievements frei.

    Returns:
        list: Neu freigeschaltete Achievements
    """
    new_achievements = []

    try:
        # Achievement Definitionen
        achievement_checks = [
            ('first_session', "🎉 Erste Schritte", "Deine erste Übungssession!", lambda s, r: True),
            ('streak_3', "🔥 Auf Feuer!", "3 Tage in Folge geübt", lambda s, r: s.get('current_streak', 0) >= 3),
            ('streak_7', "🔥🔥 Wochenkrieger", "7 Tage in Folge geübt", lambda s, r: s.get('current_streak', 0) >= 7),
            ('streak_14', "🔥🔥🔥 Unaufhaltbar", "14 Tage in Folge geübt", lambda s, r: s.get('current_streak', 0) >= 14),
            ('streak_30', "🏆 Monatsmeister", "30 Tage in Folge geübt", lambda s, r: s.get('current_streak', 0) >= 30),
            ('xp_100', "⭐ Sammler", "100 XP verdient", lambda s, r: s.get('total_xp', 0) >= 100),
            ('xp_500', "⭐⭐ Fleißig", "500 XP verdient", lambda s, r: s.get('total_xp', 0) >= 500),
            ('xp_1000', "⭐⭐⭐ Superstar", "1000 XP verdient", lambda s, r: s.get('total_xp', 0) >= 1000),
            ('level_5', "📈 Aufsteiger", "Level 5 erreicht", lambda s, r: s.get('level', 1) >= 5),
            ('level_10', "📈📈 Profi", "Level 10 erreicht", lambda s, r: s.get('level', 1) >= 10),
        ]

        # Session-basierte Achievements
        if session_results:
            correct = sum(1 for r in session_results if r.get('correct', False))
            total = len(session_results)
            accuracy = (correct / total * 100) if total > 0 else 0

            achievement_checks.extend([
                ('perfect_5', "💯 Mini-Perfekt", "5 von 5 richtig", lambda s, r: total >= 5 and accuracy == 100),
                ('perfect_10', "💯💯 Perfektionist", "10 von 10 richtig", lambda s, r: total >= 10 and accuracy == 100),
            ])

        # Prüfe jedes Achievement
        user_id = get_current_user()
        for key, name, description, check_func in achievement_checks:
            # Prüfe ob schon freigeschaltet
            existing = db_query(
                "SELECT id FROM achievements WHERE user_id = %s AND achievement_key = %s",
                (user_id, key)
            )

            if not existing and check_func(stats, session_results):
                # Freischalten!
                db_query(
                    "INSERT INTO achievements (user_id, achievement_key) VALUES (%s, %s)",
                    (user_id, key),
                    fetch=False
                )
                new_achievements.append({'key': key, 'name': name, 'description': description})
    except Exception:
        pass  # Table doesn't exist yet

    return new_achievements


def get_unlocked_achievements():
    """Holt alle freigeschalteten Achievements."""
    try:
        result = db_query(
            "SELECT achievement_key, unlocked_at FROM achievements WHERE user_id = %s ORDER BY unlocked_at DESC",
            (get_current_user(),)
        )
    except Exception:
        return []  # Table doesn't exist yet

    # Achievement Metadaten
    achievement_meta = {
        'first_session': ("🎉 Erste Schritte", "Deine erste Übungssession!"),
        'streak_3': ("🔥 Auf Feuer!", "3 Tage in Folge geübt"),
        'streak_7': ("🔥🔥 Wochenkrieger", "7 Tage in Folge geübt"),
        'streak_14': ("🔥🔥🔥 Unaufhaltbar", "14 Tage in Folge geübt"),
        'streak_30': ("🏆 Monatsmeister", "30 Tage in Folge geübt"),
        'xp_100': ("⭐ Sammler", "100 XP verdient"),
        'xp_500': ("⭐⭐ Fleißig", "500 XP verdient"),
        'xp_1000': ("⭐⭐⭐ Superstar", "1000 XP verdient"),
        'level_5': ("📈 Aufsteiger", "Level 5 erreicht"),
        'level_10': ("📈📈 Profi", "Level 10 erreicht"),
        'perfect_5': ("💯 Mini-Perfekt", "5 von 5 richtig"),
        'perfect_10': ("💯💯 Perfektionist", "10 von 10 richtig"),
    }

    achievements = []
    if result:
        for r in result:
            key = r['achievement_key']
            meta = achievement_meta.get(key, (key, ""))
            achievements.append({
                'key': key,
                'name': meta[0],
                'description': meta[1],
                'unlocked_at': r['unlocked_at']
            })

    return achievements


def update_topic_mastery(results):
    """Aktualisiert die Meisterschaft pro Grammatik-Thema."""
    try:
        # Gruppiere Ergebnisse nach Topic
        topic_stats = {}
        for r in results:
            topic = r.get('topic', 'unknown')
            # Konvertiere Display-Name zu Key
            topic_key = topic.lower().replace(' ', '_').replace('-', '_').replace('(', '').replace(')', '')

            if topic_key not in topic_stats:
                topic_stats[topic_key] = {'correct': 0, 'total': 0}

            topic_stats[topic_key]['total'] += 1
            if r.get('correct', False):
                topic_stats[topic_key]['correct'] += 1

        today = datetime.now().date()

        user_id = get_current_user()
        for topic_key, stats in topic_stats.items():
            # Prüfe ob Topic existiert
            existing = db_query(
                "SELECT id, total_attempts, correct_attempts FROM topic_mastery WHERE user_id = %s AND topic_key = %s",
                (user_id, topic_key)
            )

            if existing:
                new_total = existing[0]['total_attempts'] + stats['total']
                new_correct = existing[0]['correct_attempts'] + stats['correct']
                accuracy = (new_correct / new_total * 100) if new_total > 0 else 0

                # Bestimme Mastery Level
                if accuracy >= 85 and new_total >= 20:
                    mastery = 'MASTERED'
                elif accuracy >= 70 and new_total >= 10:
                    mastery = 'PRACTICING'
                else:
                    mastery = 'LEARNING'

                db_query(
                    """UPDATE topic_mastery SET
                       total_attempts = %s, correct_attempts = %s,
                       mastery_level = %s, last_practiced = %s, updated_at = NOW()
                       WHERE id = %s""",
                    (new_total, new_correct, mastery, today, existing[0]['id']),
                    fetch=False
                )
            else:
                accuracy = (stats['correct'] / stats['total'] * 100) if stats['total'] > 0 else 0
                mastery = 'LEARNING'

                db_query(
                    """INSERT INTO topic_mastery (user_id, topic_key, total_attempts, correct_attempts, mastery_level, last_practiced)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (user_id, topic_key, stats['total'], stats['correct'], mastery, today),
                    fetch=False
                )
    except Exception:
        pass  # Table doesn't exist yet


def get_topic_mastery():
    """Holt den Fortschritt pro Thema."""
    try:
        result = db_query(
            """SELECT topic_key, total_attempts, correct_attempts, mastery_level
               FROM topic_mastery WHERE user_id = %s ORDER BY topic_key""",
            (get_current_user(),)
        )
    except Exception:
        return []  # Table doesn't exist yet

    # Topic Display Names
    display_names = {
        'past_simple___regular_verbs': 'Simple Past (Regular)',
        'past_simple___irregular_verbs': 'Simple Past (Irregular)',
        'present_perfect': 'Present Perfect',
        'past_vs_perfect_signal_words': 'Past vs Perfect',
        'going_to_future': 'Going-to Future',
        'will_future': 'Will Future',
        'comparison_of_adjectives': 'Comparison',
        'adverbs': 'Adverbs',
    }

    mastery_data = []
    if result:
        for r in result:
            key = r['topic_key']
            total = r['total_attempts']
            correct = r['correct_attempts']
            accuracy = (correct / total * 100) if total > 0 else 0

            mastery_data.append({
                'topic_key': key,
                'display_name': display_names.get(key, key.replace('_', ' ').title()),
                'total': total,
                'correct': correct,
                'accuracy': accuracy,
                'mastery_level': r['mastery_level']
            })

    return mastery_data


# --- Session State ---
if "current_user" not in st.session_state:
    st.session_state.current_user = "aurelie"  # Default: Aurelie's echte Daten
if "exercise_num" not in st.session_state:
    st.session_state.exercise_num = 0
if "total_exercises" not in st.session_state:
    st.session_state.total_exercises = 10
if "current_exercise" not in st.session_state:
    st.session_state.current_exercise = None
if "results" not in st.session_state:
    st.session_state.results = []
if "streak" not in st.session_state:
    st.session_state.streak = 0
if "show_feedback" not in st.session_state:
    st.session_state.show_feedback = False
if "last_correct" not in st.session_state:
    st.session_state.last_correct = None
if "session_started" not in st.session_state:
    st.session_state.session_started = False
if "best_streak" not in st.session_state:
    st.session_state.best_streak = 0

# --- Main App ---

st.title("📚 Aurelie's English Practice")

# API Key Check - Claude API (zuverlässig!)
api_key = os.environ.get("ANTHROPIC_API_KEY")
if not api_key:
    st.warning("⚠️ Bitte setze den ANTHROPIC_API_KEY als Umgebungsvariable.")
    st.info("💡 Tipp: `export ANTHROPIC_API_KEY='sk-ant-...'` im Terminal")
    api_key = st.text_input("Oder gib deinen API Key hier ein:", type="password")
    if not api_key:
        st.stop()

# Claude Client initialisieren
client = anthropic.Anthropic(api_key=api_key)

# --- Start Screen ---
if not st.session_state.session_started:
    # Test-Banner (nur im Test-Modus, aber gleiche UI wie Aurelie sieht)
    if get_current_user() == "test_user":
        st.info("🧪 **TEST ENVIRONMENT** - Daten werden separat gespeichert")

    # Normale Begrüßung (identisch für Test und Produktion)
    st.markdown("## 👋 Hey Aurelie!")
    st.markdown("Schön, dass du da bist! Lass uns zusammen Englisch üben. 🎯")

    st.markdown("---")

    # === ENGAGEMENT DASHBOARD ===
    try:
        user_stats = get_user_stats()
        current_streak = user_stats.get('current_streak', 0)
        longest_streak = user_stats.get('longest_streak', 0)
        total_xp = user_stats.get('total_xp', 0)
        level = user_stats.get('level', 1)
        streak_freeze = user_stats.get('streak_freeze_available', True)

        # Haupt-Stats in 2 Spalten (vereinfacht)
        st.markdown("### 📊 Dein Fortschritt")
        col1, col2 = st.columns(2)

        with col1:
            streak_emoji = "🔥" if current_streak > 0 else "❄️"
            # Zeige Rekord als Delta wenn er höher als aktuell ist
            delta_text = f"Rekord: {longest_streak}" if longest_streak > current_streak else None
            st.metric(f"{streak_emoji} Streak", f"{current_streak} Tage", delta=delta_text, delta_color="off", help="Tage in Folge geübt - jeden Tag üben hält den Streak!")

        with col2:
            st.metric("⭐ Level", level, help="Steigt mit jeder richtigen Antwort")

        # Streak-Warnung oder Motivation
        if current_streak == 0:
            st.info("💪 Starte heute deinen Streak! Jeden Tag üben = Streak aufbauen!")
        elif current_streak >= 7:
            st.success(f"🎉 Wow! {current_streak} Tage in Folge! Du bist unaufhaltbar!")
        elif current_streak >= 3:
            st.success(f"🔥 {current_streak} Tage Streak! Mach weiter so!")

        # Streak Freeze Status
        if not streak_freeze and current_streak > 0:
            st.caption("⚠️ Streak Freeze verbraucht - übe jeden Tag, um deinen Streak zu behalten!")

        # Level Progress Bar
        xp_for_next_level = (level) * 500  # Level 1→2 = 500, Level 2→3 = 1000, etc.
        xp_in_current_level = total_xp - ((level - 1) * 500)
        progress_to_next = min(1.0, xp_in_current_level / 500) if level > 0 else 0

        st.caption(f"Level {level} → {level + 1}: {xp_in_current_level}/500 XP")
        st.progress(progress_to_next)

        st.markdown("---")

        # Topic Mastery Overview
        mastery_data = get_topic_mastery()
        if mastery_data:
            st.markdown("### 📚 Themen-Fortschritt")

            # Gruppiere nach Mastery Level
            mastered = [t for t in mastery_data if t['mastery_level'] == 'MASTERED']
            practicing = [t for t in mastery_data if t['mastery_level'] == 'PRACTICING']
            learning = [t for t in mastery_data if t['mastery_level'] == 'LEARNING']

            col1, col2, col3 = st.columns(3)

            with col1:
                st.markdown("**✅ Gemeistert**")
                if mastered:
                    for t in mastered:
                        st.markdown(f"- {t['display_name']} ({t['accuracy']:.0f}%)")
                else:
                    st.caption("_Noch keins_")

            with col2:
                st.markdown("**📝 Am Üben**")
                if practicing:
                    for t in practicing:
                        st.markdown(f"- {t['display_name']} ({t['accuracy']:.0f}%)")
                else:
                    st.caption("_Noch keins_")

            with col3:
                st.markdown("**🌱 Am Lernen**")
                if learning:
                    for t in learning:
                        st.markdown(f"- {t['display_name']} ({t['accuracy']:.0f}%)")
                else:
                    st.caption("_Noch keins_")

            st.markdown("---")

        # Achievements (kompakt)
        achievements = get_unlocked_achievements()
        if achievements:
            with st.expander(f"🏅 Achievements ({len(achievements)} freigeschaltet)"):
                for a in achievements[:6]:  # Max 6 zeigen
                    st.markdown(f"**{a['name']}** - {a['description']}")
                if len(achievements) > 6:
                    st.caption(f"... und {len(achievements) - 6} weitere")

    except Exception as e:
        # Fallback wenn Tabellen noch nicht existieren
        st.info("📊 Engagement-System wird geladen... (Datenbank wird eingerichtet)")

        # Lade letzte Sessions für Kontext (alter Code als Fallback)
        sessions_path = BASE_PATH / "sessions"
        if sessions_path.exists():
            session_count = len(list(sessions_path.glob("*.md")))
            if session_count > 0:
                st.success(f"💪 Du hast schon **{session_count} Sessions** gemacht! Weiter so!")

    # Lernstand laden
    lernstand = load_lernstand()
    error_patterns_content = load_error_patterns()

    # Aktive Fehlermuster und fällige Items holen
    active_patterns = get_active_error_patterns()
    due_items = get_due_items()

    # Spaced Repetition: Fällige Items anzeigen
    if due_items.get("verbs") or due_items.get("topics"):
        st.markdown("---")
        due_display = []
        if due_items.get("verbs"):
            due_display.append(f"Verben: {', '.join(due_items['verbs'])}")
        if due_items.get("topics"):
            due_display.append(f"Themen: {', '.join(due_items['topics'])}")
        st.warning(f"📅 **Heute zur Wiederholung fällig**: {' | '.join(due_display)}")

    # Aktive Fehlermuster anzeigen
    if active_patterns and active_patterns.get("pattern_names"):
        st.markdown("---")
        st.error(f"🎯 **Dein Fokus heute**: Diese Verben haben dir Probleme gemacht - wir üben sie extra!")
        for pattern in active_patterns["pattern_names"]:
            st.markdown(f"- {pattern.replace('-', ' ').title()}")
        if active_patterns.get("problem_verbs"):
            st.caption(f"Besonders: {', '.join(active_patterns['problem_verbs'])}")

    # Beobachtete Muster als Tipp
    elif error_patterns_content and "BEOBACHTEN" in error_patterns_content:
        st.markdown("---")
        st.info("💡 **Tipp**: Achte heute besonders auf die Verben, die du letztens verwechselt hast!")

    st.markdown("---")

    # Thema auswählen
    st.markdown("### 🎯 Welches Thema möchtest du üben?")

    # Vordefinierte Themen (basierend auf JSON exercises.json - 8 Topics + Gemischt)
    topics = [
        "🎲 Gemischt (alle Themen)",
        "📝 Simple Past Regular (regelmäßige Verben)",
        "📝 Simple Past Irregular (unregelmäßige Verben)",
        "📝 Present Perfect (have/has + done)",
        "🔀 Past vs Perfect (Signalwörter)",
        "🚀 Going-to Future (Zukunft mit going to)",
        "🚀 Will Future (Zukunft mit will)",
        "📊 Comparison of Adjectives (Steigerung)",
        "✨ Adverbs (Adverbien)",
    ]

    selected_topic = st.selectbox(
        "Wähle ein Thema:",
        topics,
        index=0,
        key="topic_selector"
    )

    # Thema in session_state speichern
    if selected_topic.startswith("🎲"):
        st.session_state.selected_topic = None  # Gemischt
    else:
        # Extrahiere das Thema aus dem Dropdown-Text
        topic_mapping = {
            "Simple Past Regular": "Simple Past Regular",
            "Simple Past Irregular": "Simple Past Irregular",
            "Present Perfect": "Present Perfect",
            "Past vs Perfect": "Past vs Perfect",
            "Going-to Future": "Going-to Future",
            "Will Future": "Will Future",
            "Comparison of Adjectives": "Comparison",
            "Adverbs": "Adverbs",
        }
        for key, value in topic_mapping.items():
            if key in selected_topic:
                st.session_state.selected_topic = value
                break

    # Zeige was geübt wird
    if st.session_state.get("selected_topic"):
        st.info(f"📚 **Thema heute**: {st.session_state.selected_topic}")

    st.markdown("---")

    # Übungsanzahl wählen
    st.markdown("### Wie viele Übungen möchtest du machen?")
    num_exercises = st.slider("", 5, 15, 10, label_visibility="collapsed")
    st.session_state.total_exercises = num_exercises

    st.markdown("")  # Spacing

    if st.button("🚀 Los geht's!", type="primary", use_container_width=True):
        st.session_state.session_started = True
        st.session_state.exercise_num = 1
        st.session_state.best_streak = 0  # Track best streak
        st.rerun()

# --- Exercise Screen ---
elif st.session_state.exercise_num <= st.session_state.total_exercises:

    # Header mit Restart-Button
    col_title, col_restart = st.columns([4, 1])
    with col_title:
        pass  # Progress kommt darunter
    with col_restart:
        if st.button("🏠 Neu starten", key="restart_btn", help="Zurück zum Start"):
            # Session zurücksetzen
            st.session_state.session_started = False
            st.session_state.exercise_num = 1
            st.session_state.results = []
            st.session_state.streak = 0
            st.session_state.current_exercise = None
            st.session_state.show_feedback = False
            st.session_state.selected_topic = None
            st.rerun()

    # Progress
    progress = st.session_state.exercise_num / st.session_state.total_exercises
    st.progress(progress)
    st.caption(f"Übung {st.session_state.exercise_num} von {st.session_state.total_exercises}")

    # Streak anzeigen
    if st.session_state.streak > 0:
        st.markdown(f'<p class="streak">🔥 {st.session_state.streak} richtig hintereinander!</p>', unsafe_allow_html=True)

    # Übung laden oder generieren
    if st.session_state.current_exercise is None:
        with st.spinner("Übung wird geladen..."):
            lernstand = load_lernstand()
            error_patterns = load_error_patterns()
            # Aktive Fehlermuster für Interleaving holen
            active_patterns = get_active_error_patterns()
            # Fällige Spaced Repetition Items holen
            due_items = get_due_items()
            exercise = get_exercise_from_claude(
                client,
                lernstand,
                error_patterns,
                st.session_state.exercise_num,
                st.session_state.total_exercises,
                active_error_patterns=active_patterns,
                selected_topic=st.session_state.get("selected_topic"),
                due_items=due_items
            )
            st.session_state.current_exercise = exercise
            st.rerun()

    exercise = st.session_state.current_exercise

    # Übung anzeigen
    st.markdown(f"**Thema**: {exercise['topic']}")
    st.markdown("⭐" * exercise.get('difficulty', 3) + "☆" * (5 - exercise.get('difficulty', 3)))

    st.markdown('<div class="exercise-box">', unsafe_allow_html=True)
    st.markdown(f"### {exercise['question']}")
    st.markdown('</div>', unsafe_allow_html=True)

    # Vokabel-Hilfe: Wort erklären lassen
    with st.expander("❓ Ich kenne ein Wort nicht"):
        vocab_word = st.text_input(
            "Welches Wort verstehst du nicht?",
            key=f"vocab_help_{st.session_state.exercise_num}",
            placeholder="z.B. 'went' oder 'swimming'"
        )
        if st.button("Erklären", key=f"explain_btn_{st.session_state.exercise_num}"):
            if vocab_word and vocab_word.strip():
                with st.spinner("Moment..."):
                    explanation = explain_vocabulary(vocab_word.strip(), api_client=client)
                    if explanation:
                        st.info(f"**{vocab_word.strip()}**: {explanation}")
                    else:
                        st.warning("Das konnte ich leider nicht erklären. Frag Papa!")
            else:
                st.warning("Tippe erst ein Wort ein!")

    # Feedback anzeigen wenn vorhanden
    if st.session_state.show_feedback:
        if st.session_state.last_correct:
            st.markdown(f"""
<div class="correct">
<h4>✅ Richtig!</h4>
<p><strong>{exercise['correct_answer']}</strong> ist korrekt!</p>
<p>💡 {exercise.get('hint', '')}</p>
</div>
""", unsafe_allow_html=True)
        else:
            # Safety: letzte Antwort aus results holen (falls vorhanden)
            last_answer = st.session_state.results[-1]['user_answer'] if st.session_state.results else "?"

            # Kontextbezogene Erklärung WARUM die Antwort falsch ist
            why_wrong = explain_why_wrong(
                last_answer,
                exercise['correct_answer'],
                exercise['question']
            )

            st.markdown(f"""
<div class="incorrect">
<h4>🤔 Fast!</h4>
<p>Du hast geschrieben: <em>{last_answer}</em></p>
<p>Richtig wäre: <strong>{exercise['correct_answer']}</strong></p>
</div>
""", unsafe_allow_html=True)

            # Kontextbezogene Erklärung anzeigen (wenn vorhanden)
            if why_wrong:
                st.markdown(why_wrong)
            else:
                # Fallback: normale Erklärung
                st.markdown(f"💡 **Trick zum Merken:** {exercise.get('explanation', exercise.get('hint', ''))}")

            st.markdown("🌟 *Fehler sind super - so lernst du am besten!*")

        # Feedback-Option für die Übung
        with st.expander("📝 Feedback zu dieser Übung geben"):
            # Letzte Antwort für Kontext holen
            last_user_answer = st.session_state.results[-1]['user_answer'] if st.session_state.results else ""

            feedback_text = st.text_area(
                "Was war das Problem?",
                key=f"feedback_text_{st.session_state.exercise_num}",
                placeholder="z.B. 'Die Frage war nicht gut erklärt' oder 'Da war ein Fehler'"
            )
            if st.button("💬 Feedback senden", key=f"send_feedback_{st.session_state.exercise_num}"):
                if feedback_text and feedback_text.strip():
                    # Feedback in Supabase speichern
                    if save_feedback(exercise, last_user_answer, feedback_text):
                        st.success("✅ Danke!")
                    else:
                        st.error("Feedback konnte nicht gespeichert werden.")
                else:
                    st.warning("Schreib erst was rein!")

        if st.button("Weiter →", type="primary", use_container_width=True):
            st.session_state.exercise_num += 1
            st.session_state.current_exercise = None
            st.session_state.show_feedback = False
            st.rerun()

    else:
        # Antwort-Eingabe mit Enter-Key Support (st.form)
        with st.form(key=f"answer_form_{st.session_state.exercise_num}"):
            user_answer = st.text_input("Deine Antwort:", key=f"answer_{st.session_state.exercise_num}")

            col1, col2 = st.columns([3, 1])

            with col1:
                submitted = st.form_submit_button("Prüfen ↵", type="primary", use_container_width=True)

            with col2:
                show_hint = st.form_submit_button("💡 Tipp")

        # Form wurde submitted (Button ODER Enter-Taste)
        if submitted:
            if user_answer:
                is_correct = check_answer(user_answer, exercise['correct_answer'])

                # Ergebnis speichern
                st.session_state.results.append({
                    "topic": exercise['topic'],
                    "question": exercise['question'],
                    "user_answer": user_answer,
                    "correct_answer": exercise['correct_answer'],
                    "correct": is_correct
                })

                # Streak aktualisieren
                if is_correct:
                    st.session_state.streak += 1
                    # Best streak tracken
                    if st.session_state.streak > st.session_state.get("best_streak", 0):
                        st.session_state.best_streak = st.session_state.streak
                else:
                    st.session_state.streak = 0

                st.session_state.last_correct = is_correct
                st.session_state.show_feedback = True
                st.rerun()
            else:
                st.warning("Bitte schreib erst eine Antwort! 😊")

        if show_hint:
            st.info(exercise.get('hint', 'Denk an die unregelmäßigen Verben!'))

# --- Results Screen ---
else:
    st.balloons()

    results = st.session_state.results
    correct = sum(1 for r in results if r["correct"])
    total = len(results)
    quote = int(correct / total * 100) if total > 0 else 0
    best_streak = st.session_state.get("best_streak", 0)

    # AUTO-SAVE: Session automatisch speichern wenn noch nicht geschehen
    if not st.session_state.get("session_saved", False) and results:
        session_id = save_session_result(results)
        update_error_patterns(results)
        update_spaced_repetition(results)

        # === ENGAGEMENT SYSTEM ===
        try:
            # 1. Streak aktualisieren
            new_streak = update_daily_streak()
            st.session_state.updated_streak = new_streak

            # 2. XP berechnen und vergeben
            total_xp, xp_breakdown = calculate_session_xp(results, best_streak)
            for xp_type in ['correct_answer', 'streak_bonus', 'perfect_session']:
                # Vereinfacht: alles als session_xp
                pass
            award_xp(total_xp, 'session', session_id)
            st.session_state.earned_xp = total_xp
            st.session_state.xp_breakdown = xp_breakdown

            # 3. Topic Mastery aktualisieren
            update_topic_mastery(results)

            # 4. Achievements prüfen
            stats = get_user_stats()
            new_achievements = check_and_unlock_achievements(stats, results)
            st.session_state.new_achievements = new_achievements

        except Exception as e:
            # Engagement-System Fehler sollten Session nicht blockieren
            print(f"Engagement-System Fehler: {e}")
            st.session_state.earned_xp = 0
            st.session_state.xp_breakdown = []
            st.session_state.new_achievements = []

        st.session_state.session_saved = True

    # Motivierende Überschrift basierend auf Ergebnis
    if quote >= 90:
        st.title("🏆 Fantastisch, Aurelie!")
        st.markdown("Du bist heute eine echte Englisch-Meisterin! 🌟")
    elif quote >= 70:
        st.title("🎉 Super gemacht!")
        st.markdown("Das war richtig gut! Weiter so! 💪")
    elif quote >= 50:
        st.title("👍 Gut gemacht!")
        st.markdown("Du wirst immer besser! Übung macht den Meister! 📈")
    else:
        st.title("💪 Nicht aufgeben!")
        st.markdown("Jeder Fehler ist eine Chance zu lernen. Beim nächsten Mal klappt's besser! 🌱")

    st.markdown("---")

    # === XP EARNED DISPLAY ===
    earned_xp = st.session_state.get('earned_xp', 0)
    xp_breakdown = st.session_state.get('xp_breakdown', [])
    new_achievements = st.session_state.get('new_achievements', [])
    updated_streak = st.session_state.get('updated_streak', 0)

    if earned_xp > 0:
        st.markdown(f"### ⭐ +{earned_xp} XP verdient!")
        for line in xp_breakdown:
            st.caption(line)

    # Neue Achievements anzeigen
    if new_achievements:
        st.markdown("---")
        st.markdown("### 🏅 Neue Achievements freigeschaltet!")
        for a in new_achievements:
            st.success(f"**{a['name']}** - {a['description']}")

    # Streak Update
    if updated_streak > 1:
        st.info(f"🔥 Dein Streak: **{updated_streak} Tage** in Folge!")

    st.markdown("---")

    # Statistiken mit großen Zahlen
    st.markdown("### 📊 Deine Ergebnisse")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Übungen", total)
    with col2:
        st.metric("Richtig", f"{correct} ✓")
    with col3:
        st.metric("Quote", f"{quote}%")
    with col4:
        st.metric("Beste Serie", f"{best_streak} 🔥")

    st.markdown("---")

    # Konkrete Beispiele sammeln (nicht nur Themen-Zähler)
    correct_examples = []  # Liste von {"answer": "went", "verb": "go"}
    wrong_examples = []    # Liste von {"user": "goed", "correct": "went", "verb": "go"}

    for r in results:
        # Verb aus der Frage extrahieren
        verb_match = re.search(r'\((\w+)\)', r.get("question", ""))
        verb = verb_match.group(1) if verb_match else ""

        if r["correct"]:
            correct_examples.append({
                "answer": r["correct_answer"],
                "verb": verb
            })
        else:
            wrong_examples.append({
                "user": r["user_answer"],
                "correct": r["correct_answer"],
                "verb": verb
            })

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### ✅ Das kannst du schon:")
        if correct_examples:
            # Zeige konkrete Beispiele (max 5)
            for ex in correct_examples[:5]:
                if ex["verb"]:
                    st.markdown(f"- **{ex['verb']}** → _{ex['answer']}_ ✓")
                else:
                    st.markdown(f"- _{ex['answer']}_ ✓")
            if len(correct_examples) > 5:
                st.caption(f"... und {len(correct_examples) - 5} weitere")
        else:
            st.markdown("_Beim nächsten Mal wird's besser!_")

    with col2:
        st.markdown("### 📝 Das üben wir nochmal:")
        if wrong_examples:
            # Zeige konkrete Fehler mit Korrektur
            for ex in wrong_examples[:5]:
                st.markdown(f"- **{ex['verb']}**: ~~{ex['user']}~~ → **{ex['correct']}**")
            if len(wrong_examples) > 5:
                st.caption(f"... und {len(wrong_examples) - 5} weitere")
        else:
            st.markdown("_Alles perfekt! Wow!_ 🌟")

    st.markdown("---")

    # Details (aufklappbar)
    st.markdown("### 📋 Alle Übungen im Detail")

    for i, r in enumerate(results, 1):
        status = "✅" if r["correct"] else "❌"
        with st.expander(f"{status} Übung {i}: {r['topic']}"):
            st.markdown(f"**Frage:** {r['question']}")
            st.markdown(f"**Deine Antwort:** {r['user_answer']}")
            if not r["correct"]:
                st.markdown(f"**Richtige Antwort:** {r['correct_answer']}")

    st.markdown("---")

    # Was kommt als nächstes - konkrete Verben
    st.markdown("### 🔮 Morgen")
    if wrong_examples:
        # Zeige die konkreten Verben die wiederholt werden
        wrong_verbs = list(set(ex["verb"] for ex in wrong_examples if ex["verb"]))
        if wrong_verbs:
            st.info(f"💡 Wir üben morgen besonders: **{', '.join(wrong_verbs)}**")
            st.caption("Diese werden automatisch in dein Spaced Repetition System aufgenommen.")
        else:
            st.info("💡 Wir wiederholen morgen die Fehler von heute.")
    else:
        st.success("🎯 Du bist bereit für neue Themen!")

    st.markdown("---")

    # Auto-Save Bestätigung anzeigen
    st.success("✅ Deine Session wurde automatisch gespeichert!")

    # Button für neue Session
    if st.button("🔄 Neue Session starten", type="primary", use_container_width=True):
        st.session_state.exercise_num = 0
        st.session_state.session_saved = False  # Reset für nächste Session
        st.session_state.current_exercise = None
        st.session_state.results = []
        st.session_state.streak = 0
        st.session_state.best_streak = 0
        st.session_state.show_feedback = False
        st.session_state.session_started = False
        st.rerun()

    st.markdown("---")
    st.markdown("**Bis morgen, Aurelie! 👋💪**")

# --- Sidebar ---
with st.sidebar:
    # === VERSTECKTER TEST-MODUS ===
    # Aktiviere mit URL-Parameter: ?mode=test
    # Aurelie sieht das nie - nur Vincent kennt den Parameter
    query_params = st.query_params
    is_test_mode = query_params.get("mode") == "test"

    if is_test_mode:
        # Test-Modus aktivieren wenn noch nicht gesetzt
        if st.session_state.current_user != "test_user":
            st.session_state.current_user = "test_user"
            st.session_state.session_started = False
            st.session_state.results = []
            st.session_state.streak = 0
            st.session_state.best_streak = 0
            st.session_state.exercise_num = 0
            st.session_state.current_exercise = None
            st.cache_data.clear()
            st.rerun()

        st.warning("🧪 **TEST-MODUS**")
        st.caption("Daten werden separat gespeichert")
        st.markdown("---")

    st.markdown("### 📊 Session Info")
    st.markdown(f"**Richtig:** {sum(1 for r in st.session_state.results if r.get('correct', False))}")
    st.markdown(f"**Gesamt:** {len(st.session_state.results)}")

    if st.session_state.streak > 0:
        st.markdown(f"**🔥 Streak:** {st.session_state.streak}")

    st.markdown("---")
    st.markdown("### ℹ️ Info")
    st.markdown("Tippe deine Antwort ein und drücke 'Prüfen'.")
    st.markdown("Bei Lückentexten: Nur das fehlende Wort eingeben.")

    st.markdown("---")
    st.markdown("### 📸 Schulmaterial importieren")
    st.caption("Fotografiere Arbeitsblätter oder Buchseiten")

    uploaded_files = st.file_uploader(
        "Fotos hochladen",
        type=["jpg", "jpeg", "png"],
        key="school_material_upload",
        help="Lade Fotos von deinem Englisch-Material hoch",
        accept_multiple_files=True
    )

    if uploaded_files:
        # Vorschau aller Bilder
        for i, uploaded_file in enumerate(uploaded_files):
            st.image(uploaded_file, caption=f"Bild {i+1}: {uploaded_file.name}", use_container_width=True)

        if st.button("🔍 Alles extrahieren", key="extract_vocab_btn"):
            all_extractions = []
            for i, file in enumerate(uploaded_files):
                with st.spinner(f"Analysiere Bild {i+1} von {len(uploaded_files)}..."):
                    image_bytes = file.getvalue()
                    extraction = extract_from_school_material(image_bytes)
                    if extraction:
                        all_extractions.append(f"### Bild {i+1}: {file.name}\n\n{extraction}")

            if all_extractions:
                combined = "\n\n---\n\n".join(all_extractions)
                st.success(f"✅ {len(all_extractions)} Bild(er) analysiert!")
                st.markdown(combined)

                # In session_state speichern für späteren Zugriff
                st.session_state.last_extraction = combined

        # Speichern-Button (außerhalb des if-Blocks)
        if st.session_state.get("last_extraction"):
            if st.button("💾 Ins Curriculum speichern", key="save_vocab_btn"):
                filename = save_extracted_vocabulary(st.session_state.last_extraction)
                if filename:
                    st.success(f"Gespeichert: {filename}")
                    st.session_state.last_extraction = None
                else:
                    st.error("Speichern fehlgeschlagen")
