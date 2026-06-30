# =============================================================================
# Description: Terraform + provider version pins and the S3 remote backend
#              configuration for the main Snap & Cook stack. The backend block
#              cannot interpolate variables, so the bucket/table names are
#              literal here — they must match the outputs of infra/bootstrap.
# Last Modified By: bvela
# Created: 2026-06-30
# Last Modified:
#     2026-06-30 - File created: version pins + S3 backend.
# =============================================================================

terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Remote state — provisioned once by infra/bootstrap. If you change these
  # names, update the bootstrap stack to match and re-run `terraform init`.
  backend "s3" {
    bucket         = "snap-and-cook-tfstate-945504685682"
    key            = "main/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "snap-and-cook-tflock"
    encrypt        = true
  }
}
