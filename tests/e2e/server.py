"""Run the real app with deterministic model output, never application credentials."""

import argparse
import os
from datetime import date

import uvicorn
from pydantic_ai.models import override_allow_model_requests
from pydantic_ai.models.test import TestModel

from app.agent import build_agent
from app.embeddings import get_embedding_client
from app.main import create_app, get_agent_factory
from app.monitoring import get_monitoring_date
from app.qa_agent import build_qa_agent, get_qa_agent_factory
from app.qa_routes import get_qa_clock
from tests.database import require_disposable_database
from tests.knowledge_fixtures import SyntheticEmbeddings


def output_for(scenario):
    drug = {
        "requirement": "Drug screening",
        "proposed_status": "Completed",
        "supporting_text": "Drug screening completed.",
    }
    warnings = []
    if scenario == "inferred":
        drug.update(
            proposed_status="Scheduled",
            date={"text": "on the 18th", "day": 18},
            supporting_text="Drug screening on the 18th.",
        )
    if scenario == "additional":
        drug.update(requirement="Orientation", supporting_text="Orientation completed.")
    if scenario == "failure":
        drug["proposed_status"] = " "
    if scenario == "html":
        drug["supporting_text"] = "<script>window.injected = true</script>"
    if scenario == "empty":
        return {"suggestions": [], "ambiguities": ["Insufficient information."]}
    if scenario == "warning":
        drug["proposed_status"] = "Scheduled"
        warnings = ["Scheduled date is missing."]
    suggestions = [drug]
    if scenario == "multiple":
        suggestions.append(
            {
                "requirement": "Insurance credentialing",
                "proposed_status": "Incomplete",
                "supporting_text": "Credentialing returned for missing info.",
            }
        )
    return {"suggestions": suggestions, "ambiguities": warnings}


def create_test_app(
    test_database_url: str, scenario: str, as_of: date = date(2026, 11, 11)
):
    require_disposable_database(test_database_url, None)
    os.environ["DATABASE_URL"] = test_database_url
    application = create_app()
    application.dependency_overrides[get_monitoring_date] = lambda: as_of
    output = output_for(scenario)
    application.dependency_overrides[get_agent_factory] = lambda: (
        lambda: build_agent(TestModel(custom_output_args=output))
    )
    application.dependency_overrides[get_embedding_client] = SyntheticEmbeddings
    application.dependency_overrides[get_qa_clock] = lambda: lambda: as_of
    application.dependency_overrides[get_qa_agent_factory] = lambda: (
        lambda: build_qa_agent(
            TestModel(custom_output_args={"outcome": "cannot_answer"})
        )
    )
    return application


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--as-of", type=date.fromisoformat, default=date(2026, 11, 11))
    parser.add_argument(
        "--scenario",
        default="completed",
        choices=[
            "completed",
            "inferred",
            "failure",
            "html",
            "empty",
            "warning",
            "multiple",
            "additional",
        ],
    )
    args = parser.parse_args()
    with override_allow_model_requests(False):
        uvicorn.run(
            create_test_app(os.environ["DATABASE_URL"], args.scenario, args.as_of),
            host="127.0.0.1",
            port=args.port,
            log_level="warning",
        )


if __name__ == "__main__":
    main()
