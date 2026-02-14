###############################################################################
# AWS AgentCore Demo — Provider & Backend
###############################################################################

provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile
}

# Local backend for now — migrate to S3 when ready
terraform {
  backend "local" {
    path = "terraform.tfstate"
  }
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.name
  ecr_uri    = "${local.account_id}.dkr.ecr.${local.region}.amazonaws.com/${aws_ecr_repository.agent.name}"
  name_prefix = var.project_name
}
