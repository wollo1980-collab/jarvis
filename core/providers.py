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

import json
import logging
import re
from enum import Enum
from typing import Optional, Protocol

from core.config import Config
from core.models import Message

logger = logging.getLogger("jarvis.providers")


class LLMProvider(Protocol):
    """Rohschnittstelle: Nachrichten rein, Text raus. Prompt-Bau,
    JSON-Parsing, confirmed-Strip und Fallbacks liegen in AIEngine.

    Function-Calling (`choose_tool`, ADR-060 Scheibe 3a) ist eine OPTIONALE
    Faehigkeit: der OpenAIProvider implementiert sie, der ClaudeProvider (noch)
    nicht. AIEngine prueft deshalb per hasattr und faellt ohne diese Faehigkeit
    fail-safe auf 'kein Werkzeug' (Gespraech) zurueck - so kann Claude spaeter
    ohne weitere Aenderung andocken (nur die Methode ergaenzen)."""

    def chat(
        self,
        system: str,
        messages: list[Message],
        *,
        json_mode: bool = False,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        ...


# GPT-5- und o-Serien-Modelle (Reasoning-Familie) lehnen `max_tokens` mit 400
# ab (verlangen `max_completion_tokens`) und akzeptieren keine eigene
# temperature (nur Default 1). Erkennung defensiv am Namenspraefix, damit ein
# answer_model wie "gpt-5-chat-latest" ohne Code-Aenderung funktioniert;
# Suffix-Varianten (-mini, -chat-latest, .1, Datumsstempel) zaehlen mit.
_COMPLETION_TOKEN_STYLE = re.compile(r"^(gpt-5|o\d+)([.\-]|$)")


def uses_completion_token_style(model: str) -> bool:
    """True, wenn das Modell den neuen Parameter-Stil verlangt
    (max_completion_tokens statt max_tokens, keine eigene temperature)."""
    return bool(_COMPLETION_TOKEN_STYLE.match(model.strip().lower()))


class OpenAIProvider:
    """OpenAI Chat Completions. system als erste Nachricht (role system);
    json_mode -> response_format={"type":"json_object"}. Parameter-Stil
    (max_tokens vs. max_completion_tokens) wird pro Aufruf am effektiven
    Modellnamen erkannt - noetig, weil answer_model ein GPT-5-Modell
    unterschieben kann, waehrend der Planner auf gpt-4o-mini bleibt."""

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

    def chat(
        self,
        system: str,
        messages: list[Message],
        *,
        json_mode: bool = False,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        payload = [{"role": "system", "content": system}]
        payload += [m.to_openai_format() for m in messages]
        # model-Override pro Aufruf ("Stimme & Hirn"-Scheibe 2026-07-10):
        # answer_model hebt Chat-Antworten auf ein staerkeres Modell,
        # waehrend der Planner beim schnellen Default bleibt. max_tokens-
        # Override analog (Nutzungslauf-Befund 2026-07-10: Chat-Antworten
        # brachen am globalen 300er-Deckel mitten im Satz ab).
        effective_model = model or self.model
        budget = max_tokens or self.max_tokens
        kwargs = {
            "model": effective_model,
            "messages": payload,
        }
        if uses_completion_token_style(effective_model):
            kwargs["max_completion_tokens"] = budget
        else:
            kwargs["temperature"] = self.temperature
            kwargs["max_tokens"] = budget
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        response = self.client.chat.completions.create(**kwargs)
        # Verbrauchs-Logging (Nachtplan Scheibe 7, Vorarbeit Kosten-Kachel):
        # NUR Zahlen (Modell + Token), nie Inhalte - Muster kosten= des
        # Agenten-Arms. Fail-safe: fehlt usage, wird nichts geloggt.
        usage = getattr(response, "usage", None)
        if usage is not None:
            logger.info(
                "Verbrauch: provider=openai modell=%s tokens_in=%s tokens_out=%s",
                effective_model,
                getattr(usage, "prompt_tokens", "?"),
                getattr(usage, "completion_tokens", "?"),
            )
        return response.choices[0].message.content.strip()

    def choose_tool(
        self,
        system: str,
        messages: list[Message],
        tools: list[dict],
        *,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> "list[tuple[str, dict]]":
        """Function-Calling (ADR-060): der Kern waehlt KEINS, EINS oder MEHRERE
        Werkzeuge (Multi-Step, Phase 2). Rueckgabe: Liste [(werkzeugname,
        argumente), ...] in der Reihenfolge des Modells; LEERE Liste = kein Tool
        (Gespraech/chat). `argumente` ist das geparste arguments-Objekt je
        tool_call ({target, parameters}, siehe core/tool_schemas) - NIE
        ausgefuehrt, nur die WAHL. Executor + alle Sicherheits-Gates bleiben
        unberuehrt (dieses Modul beschreibt keine Ausfuehrung).

        tool_choice='auto': das Modell darf bewusst KEIN Werkzeug rufen
        (Gespraech) oder fuer 'X und Y' zwei. Kaputte/fehlende arguments ->
        leeres Objekt (fail-safe; reasoning.decide normalisiert weiter)."""
        payload = [{"role": "system", "content": system}]
        payload += [m.to_openai_format() for m in messages]
        effective_model = model or self.model
        budget = max_tokens or self.max_tokens
        kwargs = {
            "model": effective_model,
            "messages": payload,
            "tools": tools,
            "tool_choice": "auto",
        }
        if uses_completion_token_style(effective_model):
            kwargs["max_completion_tokens"] = budget
        else:
            kwargs["temperature"] = self.temperature
            kwargs["max_tokens"] = budget
        response = self.client.chat.completions.create(**kwargs)
        # Verbrauchs-Logging (wie chat): NUR Zahlen, nie Inhalte.
        usage = getattr(response, "usage", None)
        if usage is not None:
            logger.info(
                "Verbrauch: provider=openai modell=%s tokens_in=%s tokens_out=%s",
                effective_model,
                getattr(usage, "prompt_tokens", "?"),
                getattr(usage, "completion_tokens", "?"),
            )
        # Verbrauch zusaetzlich als Attribut (Eval-Artefakt, Truth Repair II):
        # NUR Zahlen, je Aufruf ueberschrieben. Messinstrumente lesen es nach
        # dem Call (via AIEngine.last_tool_usage); die Produktion ignoriert es.
        self.last_usage = {
            "model": effective_model,
            "tokens_in": getattr(usage, "prompt_tokens", None) if usage else None,
            "tokens_out": getattr(usage, "completion_tokens", None) if usage else None,
        }
        message = response.choices[0].message
        tool_calls = getattr(message, "tool_calls", None) or []
        result: list[tuple[str, dict]] = []
        for call in tool_calls:
            try:
                args = json.loads(call.function.arguments or "{}")
            except (ValueError, TypeError):
                args = {}
            if not isinstance(args, dict):
                args = {}
            result.append((call.function.name, args))
        return result  # leere Liste = kein Werkzeug (Gespraech)


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

    def chat(
        self,
        system: str,
        messages: list[Message],
        *,
        json_mode: bool = False,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        anthropic_messages = [{"role": m.role, "content": m.content} for m in messages]
        response = self.client.messages.create(
            model=model or self.model,
            system=system,
            messages=anthropic_messages,
            max_tokens=max_tokens or self.max_tokens,
            # Sonnet 5: kein temperature/top_p (non-default sampling params
            # werden mit 400 abgelehnt). thinking deaktiviert -> direkter
            # Text/JSON ohne Thinking-Tokens.
            thinking={"type": "disabled"},
        )
        # Verbrauchs-Logging (Scheibe 7): NUR Zahlen, nie Inhalte.
        usage = getattr(response, "usage", None)
        if usage is not None:
            logger.info(
                "Verbrauch: provider=claude modell=%s tokens_in=%s tokens_out=%s",
                model or self.model,
                getattr(usage, "input_tokens", "?"),
                getattr(usage, "output_tokens", "?"),
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
