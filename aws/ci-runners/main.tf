variable "maximum_runners" {
  description = "Total concurrent EC2 runners for this repository; no warm pool is created."
  type        = number
  default     = 32
  validation {
    condition     = var.maximum_runners >= 1 && var.maximum_runners <= 32 && floor(var.maximum_runners) == var.maximum_runners
    error_message = "Choose a whole number between 1 and the approved fleet ceiling of 32."
  }
}

locals {
  prefix     = "i2g-ci"
  repository = "Innovate-To-Grow/Innovate-To-Grow-Website"
  secret_arn = "arn:aws:ssm:us-west-2:394167325273:parameter/i2g-ci/github-app"
}

# No peering, inbound rules, NAT gateways, or connection to production networks.
resource "aws_vpc" "ci" {
  cidr_block           = "10.60.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = "${local.prefix}-isolated" }
}

resource "aws_internet_gateway" "ci" {
  vpc_id = aws_vpc.ci.id
}

resource "aws_subnet" "ci" {
  for_each                = { a = "10.60.1.0/24", b = "10.60.2.0/24", c = "10.60.3.0/24" }
  vpc_id                  = aws_vpc.ci.id
  cidr_block              = each.value
  availability_zone       = "us-west-2${each.key}"
  map_public_ip_on_launch = true
  tags                    = { Name = "${local.prefix}-${each.key}" }
}

resource "aws_route_table" "ci" {
  vpc_id = aws_vpc.ci.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.ci.id
  }
}

resource "aws_route_table_association" "ci" {
  for_each       = aws_subnet.ci
  subnet_id      = each.value.id
  route_table_id = aws_route_table.ci.id
}

resource "aws_vpc_endpoint" "s3" {
  vpc_id          = aws_vpc.ci.id
  service_name    = "com.amazonaws.us-west-2.s3"
  route_table_ids = [aws_route_table.ci.id]
}

module "runners" {
  source  = "github-aws-runners/github-runner/aws"
  version = "8.0.0"

  prefix     = local.prefix
  aws_region = "us-west-2"
  vpc_id     = aws_vpc.ci.id
  subnet_ids = [for subnet in aws_subnet.ci : subnet.id]

  github_app = {
    id_ssm = {
      name = "/i2g-ci/github-app/id"
      arn  = "${local.secret_arn}/id"
    }
    key_base64_ssm = {
      name = "/i2g-ci/github-app/key-base64"
      arn  = "${local.secret_arn}/key-base64"
    }
    webhook_secret_ssm = {
      name = "/i2g-ci/github-app/webhook-secret"
      arn  = "${local.secret_arn}/webhook-secret"
    }
  }

  webhook_lambda_zip                = "${path.module}/.artifacts/webhook.zip"
  runners_lambda_zip                = "${path.module}/.artifacts/runners.zip"
  runner_binaries_syncer_lambda_zip = "${path.module}/.artifacts/runner-binaries-syncer.zip"

  enable_organization_runners             = false
  repository_white_list                   = [local.repository]
  runner_extra_labels                     = ["i2g-aws"]
  enable_runner_bidirectional_label_match = true
  enable_ephemeral_runners                = true
  enable_jit_config                       = true
  enable_job_queued_check                 = true
  runners_maximum_count                   = var.maximum_runners
  scale_up_reserved_concurrent_executions = 1
  # SQS visibility follows this timeout; use the upstream 30-second default so
  # throttled deliveries do not hold otherwise-ready jobs for 90 seconds.
  runners_scale_up_lambda_timeout                                = 30
  lambda_event_source_mapping_batch_size                         = 10
  lambda_event_source_mapping_maximum_batching_window_in_seconds = 2
  delay_webhook_event                                            = 0
  pool_config                                                    = []
  idle_config                                                    = []
  scale_down_schedule_expression                                 = "cron(* * * * ? *)"
  scale_down_idle_confirmation_seconds                           = 60
  minimum_running_time_in_minutes                                = 2
  runner_boot_time_in_minutes                                    = 5

  # On-demand avoids interrupted builds and Spot capacity waits.
  instance_target_capacity_type = "on-demand"
  instance_allocation_strategy  = "prioritized"
  instance_types                = ["c7i.2xlarge", "c7a.2xlarge"]
  runners_ebs_optimized         = true
  associate_public_ipv4_address = true
  runner_run_as                 = "runner"
  runner_name_prefix            = "i2g-aws-"
  userdata_template             = "${path.module}/runner-user-data.sh.tftpl"
  enable_cloudwatch_agent       = true
  enable_ssm_on_runners         = true
  logging_retention_in_days     = 14
  ami = {
    id_ssm_parameter_arn = "arn:aws:ssm:us-west-2:394167325273:parameter/imagebuilder/i2g-ci/runner-ami"
  }
  block_device_mappings = [{
    device_name           = "/dev/sda1"
    volume_size           = 80
    volume_type           = "gp3"
    throughput            = 250
    encrypted             = true
    delete_on_termination = true
  }]

  # Restrict outbound access to web traffic (DNS uses the VPC resolver).
  # Debian base images use signed APT repositories over HTTP during builds.
  runner_egress_rules = [{
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = []
    prefix_list_ids  = []
    from_port        = 443
    to_port          = 443
    protocol         = "tcp"
    security_groups  = []
    self             = false
    description      = "GitHub, AWS APIs and HTTPS package registries"
    }, {
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = []
    prefix_list_ids  = []
    from_port        = 80
    to_port          = 80
    protocol         = "tcp"
    security_groups  = []
    self             = false
    description      = "Signed operating-system package repositories in Docker builds"
  }]
  depends_on = [aws_ssm_parameter.runner_ami]
}

output "webhook_url" {
  value = module.runners.webhook.endpoint
}

output "runner_pool" {
  value = {
    repository        = local.repository
    labels            = ["self-hosted", "Linux", "X64", "i2g-aws"]
    maximum           = var.maximum_runners
    idle              = 0
    instance_types    = ["c7i.2xlarge", "c7a.2xlarge"]
    vpc_id            = aws_vpc.ci.id
    ami_parameter     = aws_ssm_parameter.runner_ami.name
    image_pipeline    = aws_imagebuilder_image_pipeline.runner.arn
    scale_up_lambda   = module.runners.runners.lambda_up.function_name
    scale_down_lambda = module.runners.runners.lambda_down.function_name
  }
}
