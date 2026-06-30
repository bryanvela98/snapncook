# =============================================================================
# Description: One-time bootstrap stack for the Snap & Cook Terraform remote
#              backend. Creates the S3 bucket that stores remote state and the
#              DynamoDB table used for state locking. This stack uses LOCAL
#              state by design (chicken-and-egg: it provisions the very
#              resources the main stack's S3 backend depends on). Run once,
#              then never touch again unless the backend itself changes.
# Last Modified By: bvela
# Created: 2026-06-30
# Last Modified:
#     2026-06-30 - File created: S3 state bucket + DynamoDB lock table.
# =============================================================================

terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = var.project_name
      ManagedBy = "terraform"
      Stack     = "bootstrap"
    }
  }
}

# S3 bucket holding remote Terraform state for the main stack.
resource "aws_s3_bucket" "tfstate" {
  bucket = "${var.project_name}-tfstate-${var.account_id}"
}

# Versioning lets us recover prior state if an apply corrupts the file.
resource "aws_s3_bucket_versioning" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  versioning_configuration {
    status = "Enabled"
  }
}

# State can contain sensitive values (ARNs, secrets) — encrypt at rest.
resource "aws_s3_bucket_server_side_encryption_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# State must never be publicly reachable.
resource "aws_s3_bucket_public_access_block" "tfstate" {
  bucket                  = aws_s3_bucket.tfstate.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# DynamoDB table for state locking — prevents concurrent applies (e.g. a local
# run racing a GitHub Actions run) from corrupting state.
resource "aws_dynamodb_table" "tflock" {
  name         = "${var.project_name}-tflock"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }
}
