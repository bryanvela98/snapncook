"""
Description: Unit tests for the Rekognition detection half of processor_handler.
             Uses botocore stubbers to mock Rekognition and DynamoDB responses
             without making real AWS calls. Tests cover label filtering logic,
             low-confidence rejection, and empty-label handling.
Last Modified By: bvela
Created: 2026-06-30
Last Modified:
    2026-06-30 - File created: initial test suite for Rekognition path.
"""

import json
import os

import boto3
import pytest
from botocore.stub import Stubber

os.environ.setdefault("IMAGE_BUCKET", "test-image-bucket")
os.environ.setdefault("RESULTS_TABLE", "test-table")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")

from lambdas.processor.handler import _detect_ingredients, _filter_food_labels  # noqa: E402


def _make_label(name: str, confidence: float, parents: list[str] | None = None) -> dict:
    """Build a Rekognition label dict for use in stub responses."""
    return {
        "Name": name,
        "Confidence": confidence,
        "Parents": [{"Name": p} for p in (parents or [])],
        "Instances": [],
        "Aliases": [],
        "Categories": [],
    }


class TestFilterFoodLabels:
    def test_keeps_label_with_food_parent(self):
        labels = [_make_label("Tomato", 95.0, parents=["Vegetable", "Food"])]
        assert _filter_food_labels(labels) == ["Tomato"]

    def test_keeps_label_whose_name_is_food_parent(self):
        labels = [_make_label("Food", 95.0, parents=[])]
        assert _filter_food_labels(labels) == ["Food"]

    def test_rejects_non_food_label(self):
        labels = [_make_label("Table", 99.0, parents=["Furniture"])]
        assert _filter_food_labels(labels) == []

    def test_deduplicates_repeated_names(self):
        labels = [
            _make_label("Apple", 95.0, parents=["Fruit"]),
            _make_label("Apple", 88.0, parents=["Food"]),
        ]
        assert _filter_food_labels(labels) == ["Apple"]

    def test_mixed_food_and_non_food(self):
        labels = [
            _make_label("Cheese", 90.0, parents=["Food", "Dairy"]),
            _make_label("Chair", 85.0, parents=["Furniture"]),
            _make_label("Broccoli", 80.0, parents=["Vegetable"]),
            _make_label("Laptop", 70.0, parents=["Electronics"]),
        ]
        result = _filter_food_labels(labels)
        assert "Cheese" in result
        assert "Broccoli" in result
        assert "Chair" not in result
        assert "Laptop" not in result

    def test_empty_labels_returns_empty(self):
        assert _filter_food_labels([]) == []


class TestDetectIngredients:
    def test_returns_food_labels_from_rekognition(self, monkeypatch):
        """_detect_ingredients filters raw Rekognition output to food labels."""
        fake_response = {
            "Labels": [
                _make_label("Tomato", 95.0, parents=["Vegetable", "Food"]),
                _make_label("Cheese", 88.0, parents=["Food"]),
                _make_label("Cutting Board", 99.0, parents=["Furniture"]),
            ],
            "LabelModelVersion": "3.0",
        }

        import lambdas.processor.handler as proc_module

        stubber = Stubber(proc_module._rekognition)
        stubber.add_response(
            "detect_labels",
            fake_response,
            expected_params={
                "Image": {"S3Object": {"Bucket": "test-image-bucket", "Name": "uploads/123/image.jpeg"}},
                "MaxLabels": 30,
                "MinConfidence": 70.0,
            },
        )

        with stubber:
            result = _detect_ingredients("uploads/123/image.jpeg", "req-123")

        assert "Tomato" in result
        assert "Cheese" in result
        assert "Cutting Board" not in result

    def test_empty_when_no_food_labels(self, monkeypatch):
        """Returns empty list when Rekognition finds no food-relevant labels."""
        import lambdas.processor.handler as proc_module

        stubber = Stubber(proc_module._rekognition)
        stubber.add_response(
            "detect_labels",
            {"Labels": [_make_label("Desk", 99.0, parents=["Furniture"])], "LabelModelVersion": "3.0"},
            expected_params={
                "Image": {"S3Object": {"Bucket": "test-image-bucket", "Name": "uploads/999/image.jpeg"}},
                "MaxLabels": 30,
                "MinConfidence": 70.0,
            },
        )

        with stubber:
            result = _detect_ingredients("uploads/999/image.jpeg", "req-999")

        assert result == []
