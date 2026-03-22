"""
Context Engine: ExecutionTrace (tracer) unit tests.
"""
import time

import pytest

from app.engine.tracer import ExecutionTrace, TraceEntry


@pytest.fixture
def trace():
    return ExecutionTrace(trace_id="test123", goal="What is liability?")


# --- step lifecycle ---

def test_log_step_start(trace):
    trace.log_step_start(1, "researcher", "researcher.research")
    assert len(trace.entries) == 1
    assert trace.entries[0].step_id == 1
    assert trace.entries[0].agent == "researcher"
    assert trace.entries[0].status == "started"
    assert trace.entries[0].started_at > 0


def test_log_step_complete(trace):
    trace.log_step_start(1, "researcher", "researcher.research")
    trace.log_step_complete(1, "chunks=3")
    entry = trace.entries[0]
    assert entry.status == "completed"
    assert entry.completed_at is not None
    assert entry.duration_ms is not None
    assert entry.duration_ms >= 0
    assert entry.output_summary == "chunks=3"


def test_log_step_failed(trace):
    trace.log_step_start(1, "researcher", "researcher.research")
    trace.log_step_failed(1, "LLM timeout")
    entry = trace.entries[0]
    assert entry.status == "failed"
    assert entry.error == "LLM timeout"
    assert entry.duration_ms >= 0


def test_log_step_skipped(trace):
    trace.log_step_skipped(0, "no intent_query")
    assert len(trace.entries) == 1
    assert trace.entries[0].status == "skipped"
    assert trace.entries[0].output_summary == "no intent_query"


def test_complete_nonexistent_step_is_noop(trace):
    trace.log_step_complete(99, "should not crash")
    assert len(trace.entries) == 0


def test_failed_nonexistent_step_is_noop(trace):
    trace.log_step_failed(99, "should not crash")
    assert len(trace.entries) == 0


# --- output_summary truncation ---

def test_output_summary_truncated(trace):
    trace.log_step_start(1, "a", "a.t")
    trace.log_step_complete(1, "x" * 500)
    assert len(trace.entries[0].output_summary) == 200


# --- finalize ---

def test_finalize_completed(trace):
    trace.log_step_start(1, "researcher", "researcher.research")
    trace.log_step_complete(1, "done")
    trace.finalize("completed")
    assert trace.status == "completed"
    assert trace.completed_at is not None
    assert trace.total_duration_ms >= 0


def test_finalize_failed(trace):
    trace.finalize("failed")
    assert trace.status == "failed"


# --- to_dict ---

def test_to_dict_structure(trace):
    trace.log_step_start(1, "researcher", "researcher.research")
    trace.log_step_complete(1, "chunks=2")
    trace.log_step_skipped(-1, "no context")
    trace.finalize("completed")

    d = trace.to_dict()
    assert d["trace_id"] == "test123"
    assert d["goal"] == "What is liability?"
    assert d["status"] == "completed"
    assert d["total_duration_ms"] >= 0
    assert len(d["entries"]) == 2
    assert d["entries"][0]["step_id"] == 1
    assert d["entries"][0]["status"] == "completed"
    assert d["entries"][1]["status"] == "skipped"


def test_to_dict_truncates_goal(trace):
    trace.goal = "x" * 500
    d = trace.to_dict()
    assert len(d["goal"]) == 200


# --- find_entry picks latest ---

def test_find_entry_picks_latest(trace):
    trace.log_step_start(1, "a", "a.t")
    trace.log_step_start(1, "a", "a.t")  # duplicate step_id
    trace.log_step_complete(1, "second")
    # The latest entry for step_id=1 should be completed
    assert trace.entries[-1].status == "completed"
    # First entry should still be started
    assert trace.entries[0].status == "started"
