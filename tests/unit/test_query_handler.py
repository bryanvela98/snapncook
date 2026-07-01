"""
Description: Unit tests for the query_handler Lambda. Uses moto to mock
             DynamoDB. Tests cover COMPLETE, PROCESSING, FAILED, 404, and
             missing-parameter cases.
Last Modified By: bvela
Created: 2026-07-01
Last Modified:
    2026-07-01 - File created: initial test suite.
    2026-07-01 - Removed unused `time` import.
"""

import json
import os

import boto3
import pytest
from moto import mock_aws

os.environ.setdefault("RESULTS_TABLE", "test-results-table")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")

from lambdas.query.handler import handler  # noqa: E402

_RECIPES = [
    {
        "name": "Tomato Omelette",
        "ingredients": ["2 eggs", "1 tomato"],
        "instructions": ["Beat eggs.", "Cook.", "Add tomato.", "Serve."],
        "prep_time": "5 min",
        "cook_time": "10 min",
    },
    {
        "name": "Tomato Scramble",
        "ingredients": ["3 eggs", "1 tomato"],
        "instructions": ["Beat eggs.", "Scramble.", "Add tomato.", "Season."],
        "prep_time": "5 min",
        "cook_time": "8 min",
    },
]


@pytest.fixture()
def ddb_table():
    """Mocked DynamoDB table pre-seeded with test records."""
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        table = ddb.create_table(
            TableName="test-results-table",
            KeySchema=[{"AttributeName": "requestId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "requestId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        table.put_item(Item={
            "requestId": "complete-id",
            "status": "COMPLETE",
            "ingredients": ["Tomato", "Egg"],
            "recipes": _RECIPES,
        })
        table.put_item(Item={"requestId": "processing-id", "status": "PROCESSING"})
        table.put_item(Item={
            "requestId": "failed-id",
            "status": "FAILED",
            "error_message": "Rekognition error",
        })
        yield table


def _event(request_id: str | None) -> dict:
    """Build a minimal API Gateway event for GET /recipes/{requestId}."""
    return {"pathParameters": {"requestId": request_id} if request_id else {}}


class TestQueryHandler:
    def test_complete_returns_200_with_recipes(self, ddb_table):
        response = handler(_event("complete-id"), None)
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["status"] == "COMPLETE"
        assert len(body["recipes"]) == 2
        assert body["ingredients"] == ["Tomato", "Egg"]
        assert body["requestId"] == "complete-id"

    def test_processing_returns_200_with_status(self, ddb_table):
        response = handler(_event("processing-id"), None)
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["status"] == "PROCESSING"
        assert "recipes" not in body

    def test_failed_returns_200_with_error(self, ddb_table):
        response = handler(_event("failed-id"), None)
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["status"] == "FAILED"
        assert "Rekognition" in body["error"]

    def test_unknown_id_returns_404(self, ddb_table):
        response = handler(_event("does-not-exist"), None)
        assert response["statusCode"] == 404
        body = json.loads(response["body"])
        assert "error" in body

    def test_missing_path_param_returns_400(self, ddb_table):
        response = handler({"pathParameters": None}, None)
        assert response["statusCode"] == 400

    def test_cors_header_present(self, ddb_table):
        response = handler(_event("complete-id"), None)
        assert response["headers"]["Access-Control-Allow-Origin"] == "*"
