terraform {
  required_version = ">= 1.10, < 2.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
  backend "s3" {
    bucket       = "i2g-ci-terraform-394167325273-us-west-2"
    key          = "ci-runners/terraform.tfstate"
    region       = "us-west-2"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region              = "us-west-2"
  allowed_account_ids = ["394167325273"]
  default_tags {
    tags = {
      Project   = "Innovate-To-Grow"
      Component = "ci-runners"
      ManagedBy = "Terraform"
    }
  }
}
