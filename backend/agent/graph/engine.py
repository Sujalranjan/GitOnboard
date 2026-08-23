"""
AgentGraphOrchestrator: Thin adapter for invoking the LangGraph workflow.

Responsibility:
- Compiles the Phase 1 graph once.
- Accepts an agent run identifier and triggers graph execution.
- Relies strictly on graph nodes and EngineeringAgent for domain transitions.
- Does NOT duplicate state machine, safety, or event coordinator logic.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from sqlalchemy.orm import Session

from backend.agent.graph.builder import build_agent_graph
from backend.agent.graph.state import AgentGraphState, agent_run_to_graph_state, sync_graph_state_to_run
from backend.agent.engineering_agent import EngineeringAgent
from backend.models.implementation import AgentRun, AgentState

logger = logging.getLogger(__name__)


class AgentGraphOrchestrator:
    """
    Thin execution adapter that triggers compiled LangGraph workflows.
    """

    def __init__(
        self,
        agent_service: Optional[EngineeringAgent] = None,
        intent_router: Optional[Any] = None,
    ):
        self.agent_service = agent_service or EngineeringAgent()
        self.intent_router = intent_router
        self.graph = build_agent_graph(agent_service=self.agent_service, intent_router=self.intent_router)

    def run_graph(
        self,
        run_id: str,
        db: Optional[Session] = None,
        initial_state: Optional[Dict[str, Any]] = None,
    ) -> AgentGraphState:
        """
        Synchronously invokes the LangGraph workflow for the specified run_id.
        """
        logger.info(f"AgentGraphOrchestrator starting graph execution for run '{run_id}'")

        state: AgentGraphState
        if initial_state:
            state = AgentGraphState(**initial_state)  # type: ignore
        elif db is not None:
            run = self.agent_service.get_run(db, run_id)
            state = agent_run_to_graph_state(run)
        else:
            state = AgentGraphState(run_id=run_id, node_history=[])

        try:
            final_state: AgentGraphState = self.graph.invoke(state)  # type: ignore
            logger.info(f"AgentGraphOrchestrator completed graph execution for run '{run_id}' with state: {final_state.get('current_state')}")
            return final_state
        except Exception as err:
            logger.error(f"AgentGraphOrchestrator unhandled graph error on run '{run_id}': {err}", exc_info=True)
            if db is not None:
                try:
                    run = self.agent_service.get_run(db, run_id)
                    if not self.agent_service.state_machine.is_terminal(run.current_state):
                        self.agent_service.transition_state(
                            db,
                            run_id=run_id,
                            to_state=AgentState.FAILED,
                            reason=f"Graph orchestration failure: {err}",
                        )
                except Exception as sync_err:
                    logger.warning(f"Failed to record failure in AgentRun '{run_id}': {sync_err}")
            raise
