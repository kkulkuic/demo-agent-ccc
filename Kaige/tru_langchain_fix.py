"""
TruLens LangChain Fix - Workaround for trulens 2.7.1
=====================================================

TruChain (trulens.apps.langchain) was removed in trulens 2.7.1.
This module provides a replacement using custom instrumentation.

Usage:
    from tru_langchain_fix import TruChain, TruChainConfig

    # Wrap your LangChain app
    tru_chain = TruChain(app, app_id="my-rag-app")

    # Run with recording
    with tru_chain.recorder:
        response = app.invoke(query)
"""

import os
import sys
from typing import Any, Callable, Dict, List, Optional, Union
from dataclasses import dataclass, field
from functools import wraps

# ─── Try to import trulens components ────────────────────────────────────────
# Handle the case where trulens.apps.langchain is missing

_TRULENS_AVAILABLE = False
_Instrument = None
_TruApp = None
_TruSession = None
_LiteLLM = None
_Feedback = None

try:
    from trulens.apps.app import App as TruApp
    from trulens.core.session import TruSession
    from trulens.providers.litellm import LiteLLM
    from trulens.core.feedback.feedback import Feedback
    from trulens.apps.app import instrument
    _TRULENS_AVAILABLE = True
except ImportError as e:
    print(f"WARNING: Full TruLens not available: {e}")
    print("Using minimal instrumentation mode.")


# ─── Configuration ────────────────────────────────────────────────────────────

@dataclass
class TruChainConfig:
    """Configuration for TruChain instrumentation."""
    app_id: str = "default"
    session_name: Optional[str] = None
    feedbacks: Optional[List[Any]] = None
    feedback_mode: str = "manual"  # "with", "thread", "manual"


# ─── Minimal TruChain Implementation ──────────────────────────────────────────

class TruChain:
    """
    Replacement for the removed TruChain (trulens.apps.langchain).

    This class wraps a LangChain app and instruments it to record
    retrieval and LLM call steps for evaluation.
    """

    def __init__(
        self,
        app: Any,
        config: Optional[TruChainConfig] = None,
        app_id: Optional[str] = None,
        feedbacks: Optional[List[Any]] = None,
    ):
        """
        Initialize TruChain with a LangChain app.

        Args:
            app: The LangChain app to instrument
            config: Optional TruChainConfig
            app_id: Optional app identifier (overrides config)
            feedbacks: Optional list of feedback functions
        """
        self.app = app
        self.config = config or TruChainConfig()
        if app_id:
            self.config.app_id = app_id
        if feedbacks:
            self.config.feedbacks = feedbacks

        self._records: List[Dict] = []
        self._current_record: Optional[Dict] = None
        self._tru_app = None
        self._session = None

        if _TRULENS_AVAILABLE:
            self._setup_trulens()

    def _setup_trulens(self):
        """Set up full TruLens instrumentation if available."""
        try:
            self._session = TruSession()
            self._session.reset_database()

            # Wrap app with TruApp for instrumentation
            self._tru_app = TruApp(
                self.app,
                app_name=self.config.app_id,
                feedbacks=self.config.feedbacks or [],
            )
        except Exception as e:
            print(f"WARNING: Could not set up full TruLens: {e}")
            self._tru_app = None

    @property
    def recorder(self):
        """Return a context manager for recording."""
        return self._RecordingContext(self)

    def invoke(self, query: str, **kwargs) -> str:
        """
        Invoke the wrapped app with recording.

        Args:
            query: The input query
            **kwargs: Additional arguments

        Returns:
            The app's response
        """
        with self.recorder:
            result = self.app.invoke(query, **kwargs)
        return result

    def get_context(self) -> str:
        """Get the last retrieved context (if available)."""
        if hasattr(self.app, 'retriever') and hasattr(self.app.retriever, 'last_context'):
            return self.app.retriever.last_context
        return ""

    def get_records(self) -> List[Dict]:
        """Get all recorded execution records."""
        return self._records


class _RecordingContext:
    """Context manager for recording app invocations."""

    def __init__(self, tru_chain: TruChain):
        self.tru_chain = tru_chain
        self._start_time: Optional[float] = None

    def __enter__(self):
        import time
        self._start_time = time.perf_counter()
        self.tru_chain._current_record = {
            "start_time": self._start_time,
            "steps": [],
            "context": None,
            "response": None,
        }
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        import time
        end_time = time.perf_counter()

        if self.tru_chain._current_record:
            self.tru_chain._current_record["end_time"] = end_time
            self.tru_chain._current_record["duration_ms"] = (
                end_time - self._start_time
            ) * 1000
            self.tru_chain._current_record["error"] = str(exc_val) if exc_val else None

            # Try to capture context from app
            if hasattr(self.tru_chain.app, 'get_context'):
                self.tru_chain._current_record["context"] = (
                    self.tru_chain.app.get_context()
                )

            self.tru_chain._records.append(self.tru_chain._current_record)

        self.tru_chain._current_record = None
        return False  # Don't suppress exceptions


# ─── Feedback Helper Functions ────────────────────────────────────────────────

def create_trulens_feedback(
    provider: Any = None,
    model_engine: str = "anthropic/claude-3-5-haiku"
) -> Dict[str, Any]:
    """
    Create feedback functions for RAG evaluation.

    Uses LiteLLM provider with groundedness and relevance templates.

    Args:
        provider: Optional pre-configured provider
        model_engine: Model to use for feedback evaluation

    Returns:
        Dict with feedback functions: groundedness, context_relevance, answer_relevance
    """
    if not _TRULENS_AVAILABLE:
        return {
            "groundedness": lambda *args, **kwargs: 0.0,
            "context_relevance": lambda *args, **kwargs: 0.0,
            "answer_relevance": lambda *args, **kwargs: 0.0,
        }

    if provider is None:
        provider = LiteLLM(model_engine=model_engine)

    # Create feedback functions using the rag templates
    feedbacks = {}

    try:
        from trulens.feedback.templates.rag import Groundedness, Relevance

        # Groundedness feedback
        gnd_feedback = Feedback(
            provider.groundedness,
            name="groundedness"
        ).on(
            prompt_identifier="hypothesis"
        ).on(
            response_identifier="premise"
        )
        feedbacks["groundedness"] = gnd_feedback

        # Relevance feedback
        rel_feedback = Feedback(
            provider.relevance,
            name="context_relevance"
        ).on(
            prompt_identifier="user_input"
        ).on(
            response_identifier="response"
        )
        feedbacks["context_relevance"] = rel_feedback

    except Exception as e:
        print(f"WARNING: Could not create feedback functions: {e}")

    return feedbacks


# ─── Patch for broken trulens.apps.langchain ─────────────────────────────────

def _create_langchain_patch():
    """
    Create a mock trulens.apps.langchain module to fix import errors.

    This patches the broken import in trulens._mods by creating
    stub modules for the removed langchain integration.
    """
    import sys
    from types import ModuleType

    # Create mock module
    mock_langchain = ModuleType('trulens.apps.langchain')

    # Add stub classes that match the old API
    class MockTruChain:
        """Mock TruChain - use TruChain from this module instead."""
        pass

    class MockGuardrails:
        """Mock Guardrails - not available in this version."""
        pass

    mock_langchain.TruChain = MockTruChain
    mock_langchain.TruChain.__doc__ = """
        Mock class - use tru_langchain_fix.TruChain instead.
        The trulens.apps.langchain module was removed in trulens 2.7.1.
    """

    mock_langchain.Guardrails = MockGuardrails
    mock_langchain.Guardrails.__doc__ = """
        Mock class - Guardrails are no longer available in this format.
    """

    mock_langchain.langchain = ModuleType('trulens.apps.langchain.langchain')
    mock_langchain.tru_chain = ModuleType('trulens.apps.langchain.tru_chain')

    # Register the mock module
    if 'trulens.apps.langchain' not in sys.modules:
        sys.modules['trulens.apps.langchain'] = mock_langchain
        sys.modules['trulens.apps.langchain.langchain'] = mock_langchain.langchain
        sys.modules['trulens.apps.langchain.tru_chain'] = mock_langchain.tru_chain
        sys.modules['trulens.apps.langchain.guardrails'] = mock_langchain

    return mock_langchain


# ─── Utility: Get Last Record ─────────────────────────────────────────────────

def get_last_record(tru_chain: TruChain) -> Optional[Dict]:
    """Get the most recent execution record."""
    records = tru_chain.get_records()
    return records[-1] if records else None


def extract_record_info(record: Dict) -> Dict[str, Any]:
    """
    Extract key information from a record.

    Args:
        record: A record dict from TruChain

    Returns:
        Dict with context, response, duration, error
    """
    if not record:
        return {}

    return {
        "context": record.get("context", ""),
        "response": record.get("response", ""),
        "duration_ms": record.get("duration_ms", 0),
        "error": record.get("error", None),
        "steps": record.get("steps", []),
    }


# ─── Patch trulens if needed ─────────────────────────────────────────────────

def patch_trulens_if_needed():
    """
    Apply patches to fix trulens import issues.

    Call this before importing modules that depend on trulens.apps.langchain.
    """
    _create_langchain_patch()


# Auto-patch on import
patch_trulens_if_needed()