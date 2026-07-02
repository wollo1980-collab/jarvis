"""
LLM-Provider-Abstraktion (v0.8 Multi-KI Phase 1, ADR-029).

AIEngine (core/ai.py) baut Prompts, parst JSON, entfernt sicherheitskritisch
das confirmed-Feld (Trust Boundary) und faengt Fehler ab - alles
providerunabhaengig. Ein LLMProvider kapselt nur den rohen
"Nachrichten rein -> Text raus"-Aufruf. Zwei Implementierungen:
OpenAIProvider (OpenAI Chat Completions) und ClaudeProvider (Anthropic
Messages). Die Auswahl erfolgt explizit ueber config.ai_provider - kein
Auto-Routing.

Beide SDKs werden erst im Provider-Konstruktor importiert (lazy): das
anthropic-SDK ist optional, damit reine OpenAI-Setups OHNE installiertes
anthropic laufen (ADR-029). Der JSON-Modus fuer get_plan wird bei OpenAI
ueber response_format erzwungen, bei Claude bewusst nur ueber die
Prompt-Instruktion (kein Structured-Output/Tool-Use in Phase 1) - das
robuste Parsing/Fallback bleibt in AIEngine.
"""
from __future__ import annotations

import logging
from enum import Enum
from typing import Protocol

from core.config import Config
from core.models import Message

logger = logging.getLogger("jarvis.providers")


class LLMProvider(Protocol):
    """Rohschnittstelle: Nachrichten rein, Text raus. Prompt-Bau,
    JSON-Parsing, confirmed-Strip und Fallbacks liegen in AIEngine."""

    def chat(self, system: str, messages: list[Message], *, json_mode: bool = False) -> str:
        ...


class OpenAIProvider:
    """OpenAI Chat Completions. system als erste Nachricht (role system);
    json_mode -> response_format={"type":"json_object"}."""

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        timeout: float,
        temperature: float,
        max_tokens: int,
    ):
        from openai import OpenAI

        self.client = OpenAI(api_key=api_key, timeout=timeout)
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def chat(self, system: str, messages: list[Message], *, json_mode: bool = False) -> str:
        payload = [{"role": "system", "content": system}]
        payload += [m.to_openai_format() for m in messages]
        kwargs = {
            "model": self.model,
            "messages": payload,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        response = self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content.strip()


class ClaudeProvider:
    """Anthropic Messages. system als eigener system=-Parameter (Anthropic-
    Konvention), Turns als user/assistant. thinking wird deaktiviert - fuer
    einen einfachen, direkten Plan-/Chat-Aufruf ohne Thinking-Overhead (und
    damit ohne Kuerzungsrisiko beim kleinen max_tokens-Budget). json_mode
    wird bewusst NICHT ausgewertet: die JSON-Forderung steht bereits im
    System-Prompt (ADR-029), Parsing/Fallback bleiben in AIEngine."""

    def __init__(self, api_key: str, model: str, *, timeout: float, max_tokens: int):
        try:
            import anthropic
        except ImportError as e:  # pragma: no cover - trivialer Guard
            raise RuntimeError(
                "ai_provider='claude' benoetigt das Paket 'anthropic' "
                "(pip install anthropic). Reine OpenAI-Setups brauchen es nicht "
                "(siehe README / ADR-029)."
            ) from e
        if not api_key:
            raise RuntimeError(
                "ai_provider='claude' benoetigt die Umgebungsvariable "
                "ANTHROPIC_API_KEY (nie in config.json/Git)."
            )
        self.client = anthropic.Anthropic(api_key=api_key, timeout=timeout)
        self.model = model
        self.max_tokens = max_tokens

    def chat(self, system: str, messages: list[Message], *, json_mode: bool = False) -> str:
        anthropic_messages = [{"role": m.role, "content": m.content} for m in messages]
        response = self.client.messages.create(
            model=self.model,
            system=system,
            messages=anthropic_messages,
            max_tokens=self.max_tokens,
            # Sonnet 5: kein temperature/top_p (non-default sampling params
            # werden mit 400 abgelehnt). thinking deaktiviert -> direkter
            # Text/JSON ohne Thinking-Tokens.
            thinking={"type": "disabled"},
        )
        return "".join(block.text for block in response.content if block.type == "text").strip()


def build_named_provider(name: str, config: Config) -> LLMProvider:
    """Konstruiert EINEN Provider anhand seines Namens (explizit, kein
    Auto-Routing). Genutzt von build_provider (Standardprovider) und - fuer die
    aufgabenabhaengige Auswahl in Phase 2 (ADR-030) - vom Router-getriebenen
    Lazy-Pfad in AIEngine. Unbekannter Name -> klarer Fehler."""
    if name == "openai":
        return OpenAIProvider(
            config.openai_api_key,
            config.model,
            timeout=config.timeout,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )
    if name == "claude":
        return ClaudeProvider(
            config.anthropic_api_key,
            config.claude_model,
            timeout=config.timeout,
            max_tokens=config.max_tokens,
        )
    raise RuntimeError(
        f"Unbekannter Provider: {name!r} (erwartet 'openai' oder 'claude')."
    )


def build_provider(config: Config) -> LLMProvider:
    """Standardprovider gemaess config.ai_provider (ADR-029). Bleibt in Phase 2
    der Anker/Fallback des Routers (ADR-030)."""
    return build_named_provider(config.ai_provider, config)


class TaskType(str, Enum):
    """Aufgabentyp einer LLM-Nutzung in AIEngine - das EINZIGE, rein interne
    und vertrauenswuerdige Routing-Signal in Phase 2 (ADR-030). Bewusst nur
    zwei Werte; kein Routing nach Intent (ist Ergebnis von get_plan) oder
    Sicherheitsstufe (erst im Executor bekannt)."""

    PLANNING = "planning"      # get_plan(): Intent-Erkennung, braucht JSON
    GENERATION = "generation"  # answer(): Textausgabe


class ProviderRouter:
    """Deterministische Weiche TaskType -> Provider-Name (ADR-030).

    Kein Orchestrator: reine Nachschlagetabelle ohne Bewertung, ohne LLM-Call,
    nie von Modell-Output beeinflusst. Legt nur den Grundstein fuer spaetere,
    feinere Aufgaben-Entscheidungen. select() liefert zusaetzlich den
    Auswahlgrund ('regel' bei expliziter Config-Regel, sonst 'default') fuer
    das Logging."""

    def __init__(self, default_name: str, rules: dict[TaskType, str]):
        self._default = default_name
        self._rules = rules

    def select(self, task: TaskType) -> tuple[str, str]:
        if task in self._rules:
            return self._rules[task], "regel"
        return self._default, "default"


def build_router(config: Config) -> ProviderRouter:
    """Baut den Router aus der Config. Fehlende Felder -> Rueckfall auf
    ai_provider (Rueckwaertskompatibilitaet: ohne planning_provider/
    answer_provider verhaelt sich alles wie in Phase 1)."""
    rules: dict[TaskType, str] = {}
    if config.planning_provider:
        rules[TaskType.PLANNING] = config.planning_provider
    if config.answer_provider:
        rules[TaskType.GENERATION] = config.answer_provider
    return ProviderRouter(config.ai_provider, rules)
