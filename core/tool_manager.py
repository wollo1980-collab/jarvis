"""
Tool Manager: wählt anhand des Intent den passenden Command aus der
Registry aus. Trennt "welches Werkzeug passt" (Tool Manager) von
"das Werkzeug ausführen" (Executor) - Separation of Concerns
(Handbook Kap. 4/31: Module kommunizieren über Rückgabewerte, nicht
über verstecktes Wissen übereinander).
"""
from __future__ import annotations

import logging
from typing import Optional

from commands import REGISTRY, Command
from core.models import Plan

logger = logging.getLogger("jarvis.tool_manager")


class ToolManager:
    def resolve(self, plan: Plan) -> Optional[Command]:
        """Gibt den passenden Command zurück oder None, wenn kein
        Command für den Intent registriert ist (z. B. reiner Chat
        oder ein noch nicht implementierter Intent)."""
        command = REGISTRY.get(plan.intent)
        if command is None:
            logger.debug("Kein Tool für Intent '%s' registriert.", plan.intent)
        return command
