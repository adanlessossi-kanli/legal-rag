import logging

from app.agents.librarian import LibrarianAgent
from app.agents.orchestrator import Orchestrator
from app.agents.researcher import ResearcherAgent
from app.agents.summarizer import SummarizerAgent
from app.agents.writer import WriterAgent

logger = logging.getLogger(__name__)

_orchestrator: Orchestrator | None = None


async def create_orchestrator() -> Orchestrator:
    global _orchestrator

    librarian = LibrarianAgent()
    summarizer = SummarizerAgent()
    writer = WriterAgent()
    researcher = ResearcherAgent(librarian, summarizer)

    _orchestrator = Orchestrator(librarian, researcher, writer, summarizer)
    logger.info("Multi-agent system started (4 agents)")
    return _orchestrator


def get_orchestrator() -> Orchestrator:
    if _orchestrator is None:
        raise RuntimeError("Orchestrator not initialized. Ensure create_orchestrator() was called at startup.")
    return _orchestrator
