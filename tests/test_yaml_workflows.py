"""Tests for the included YAML workflow definitions."""
from __future__ import annotations

import os

import pytest
import yaml

from app.services.workflow_engine import WorkflowDefinition

WORKFLOW_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "workflows")


class TestLeadQualificationWorkflow:
    def test_parse(self):
        path = os.path.join(WORKFLOW_DIR, "lead_qualification.yaml")
        with open(path) as f:
            defn = WorkflowDefinition(f.read())
        assert defn.name == "lead_qualification"
        assert defn.trigger_path == "/triggers/lead_qualification"

    def test_validate(self):
        path = os.path.join(WORKFLOW_DIR, "lead_qualification.yaml")
        with open(path) as f:
            defn = WorkflowDefinition(f.read())
        errors = defn.validate()
        assert errors == [], f"Validation errors: {errors}"

    def test_has_llm_step(self):
        path = os.path.join(WORKFLOW_DIR, "lead_qualification.yaml")
        with open(path) as f:
            defn = WorkflowDefinition(f.read())
        types = [s["type"] for s in defn.steps]
        assert "llm" in types

    def test_has_condition_step(self):
        path = os.path.join(WORKFLOW_DIR, "lead_qualification.yaml")
        with open(path) as f:
            defn = WorkflowDefinition(f.read())
        types = [s["type"] for s in defn.steps]
        assert "condition" in types

    def test_has_notify_steps(self):
        path = os.path.join(WORKFLOW_DIR, "lead_qualification.yaml")
        with open(path) as f:
            defn = WorkflowDefinition(f.read())
        notify_steps = [s for s in defn.steps if s["type"] == "notify"]
        assert len(notify_steps) >= 2


class TestDocumentSummaryWorkflow:
    def test_parse(self):
        path = os.path.join(WORKFLOW_DIR, "document_summary.yaml")
        with open(path) as f:
            defn = WorkflowDefinition(f.read())
        assert defn.name == "document_summary"

    def test_validate(self):
        path = os.path.join(WORKFLOW_DIR, "document_summary.yaml")
        with open(path) as f:
            defn = WorkflowDefinition(f.read())
        errors = defn.validate()
        assert errors == [], f"Validation errors: {errors}"

    def test_has_http_step(self):
        path = os.path.join(WORKFLOW_DIR, "document_summary.yaml")
        with open(path) as f:
            defn = WorkflowDefinition(f.read())
        types = [s["type"] for s in defn.steps]
        assert "http" in types

    def test_has_llm_step(self):
        path = os.path.join(WORKFLOW_DIR, "document_summary.yaml")
        with open(path) as f:
            defn = WorkflowDefinition(f.read())
        types = [s["type"] for s in defn.steps]
        assert "llm" in types


class TestSupportTriageWorkflow:
    def test_parse(self):
        path = os.path.join(WORKFLOW_DIR, "support_triage.yaml")
        with open(path) as f:
            defn = WorkflowDefinition(f.read())
        assert defn.name == "support_triage"

    def test_validate(self):
        path = os.path.join(WORKFLOW_DIR, "support_triage.yaml")
        with open(path) as f:
            defn = WorkflowDefinition(f.read())
        errors = defn.validate()
        assert errors == [], f"Validation errors: {errors}"

    def test_has_condition_for_urgency(self):
        path = os.path.join(WORKFLOW_DIR, "support_triage.yaml")
        with open(path) as f:
            defn = WorkflowDefinition(f.read())
        condition_steps = [s for s in defn.steps if s["type"] == "condition"]
        assert len(condition_steps) >= 1

    def test_step_count(self):
        path = os.path.join(WORKFLOW_DIR, "support_triage.yaml")
        with open(path) as f:
            defn = WorkflowDefinition(f.read())
        assert len(defn.steps) == 4


class TestAllWorkflowsValid:
    def test_all_yaml_files_parse(self):
        for filename in os.listdir(WORKFLOW_DIR):
            if filename.endswith(".yaml"):
                path = os.path.join(WORKFLOW_DIR, filename)
                with open(path) as f:
                    content = f.read()
                defn = WorkflowDefinition(content)
                errors = defn.validate()
                assert errors == [], f"{filename} has errors: {errors}"
