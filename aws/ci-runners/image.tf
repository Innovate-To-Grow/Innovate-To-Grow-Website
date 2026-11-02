data "aws_ssm_parameter" "ubuntu" {
  name = "/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id"
}

# Image Builder updates this pointer after successfully testing each image.
# Do not route jobs to this pool until the first baked image is available.
resource "aws_ssm_parameter" "runner_ami" {
  name      = "/imagebuilder/i2g-ci/runner-ami"
  type      = "String"
  data_type = "aws:ec2:image"
  value     = data.aws_ssm_parameter.ubuntu.value
  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_security_group" "image_builder" {
  name        = "${local.prefix}-image-builder"
  description = "Image builder, no inbound connectivity"
  vpc_id      = aws_vpc.ci.id
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_iam_role" "image_builder" {
  name = "${local.prefix}-image-builder"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow", Principal = { Service = "ec2.amazonaws.com" }, Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "builder" {
  for_each = toset([
    "arn:aws:iam::aws:policy/EC2InstanceProfileForImageBuilder",
    "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore",
  ])
  role       = aws_iam_role.image_builder.name
  policy_arn = each.value
}

resource "aws_iam_instance_profile" "image_builder" {
  name = "${local.prefix}-image-builder"
  role = aws_iam_role.image_builder.name
}

resource "aws_iam_role" "image_execution" {
  name = "${local.prefix}-image-execution"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow", Principal = { Service = "imagebuilder.amazonaws.com" }, Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "image_execution" {
  role       = aws_iam_role.image_execution.name
  policy_arn = "arn:aws:iam::aws:policy/EC2ImageBuilderExecutionPolicy"
}

resource "aws_iam_role_policy" "image_parameter" {
  role = aws_iam_role.image_execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["ssm:PutParameter", "ssm:GetParameter"], Resource = aws_ssm_parameter.runner_ami.arn },
      { Effect = "Allow", Action = ["ec2:DescribeImages"], Resource = "*" },
    ]
  })
}

resource "aws_imagebuilder_component" "runner" {
  name     = "${local.prefix}-ubuntu-tools"
  platform = "Linux"
  version  = "1.0.0"
  lifecycle {
    create_before_destroy = true
  }
  data = yamlencode({
    name          = "I2GRunnerTools"
    description   = "Docker, GitHub runner, Python, Node and cached CI container images"
    schemaVersion = "1.0"
    phases = [{
      name = "build"
      steps = [{
        name   = "InstallRunnerTools", action = "ExecuteBash"
        inputs = { commands = [file("${path.module}/bake-image.sh")] }
      }]
      }, {
      name = "validate"
      steps = [{
        name = "ValidateRunnerTools", action = "ExecuteBash"
        inputs = { commands = [
          "set -euo pipefail",
          "docker info >/dev/null",
          "test -x /opt/actions-runner/run.sh",
          "test -x /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl",
          "node --version | grep '^v22.22.2$'",
          "/opt/hostedtoolcache/Python/3.11.18/x64/bin/python3 --version",
          "/opt/hostedtoolcache/Python/3.14.10/x64/bin/python3 --version",
          "id runner && test -r /etc/sudoers.d/runner",
        ] }
      }]
    }]
  })
}

resource "aws_imagebuilder_image_recipe" "runner" {
  name         = "${local.prefix}-ubuntu-24"
  version      = "1.0.0"
  parent_image = "ssm:${data.aws_ssm_parameter.ubuntu.name}"
  lifecycle {
    create_before_destroy = true
  }
  component {
    component_arn = aws_imagebuilder_component.runner.arn
  }
  block_device_mapping {
    device_name = "/dev/sda1"
    ebs {
      volume_size           = 80
      volume_type           = "gp3"
      delete_on_termination = true
      encrypted             = true
    }
  }
}

resource "aws_imagebuilder_infrastructure_configuration" "runner" {
  name                          = "${local.prefix}-image-builder"
  instance_profile_name         = aws_iam_instance_profile.image_builder.name
  instance_types                = ["m7i.xlarge"]
  subnet_id                     = aws_subnet.ci["a"].id
  security_group_ids            = [aws_security_group.image_builder.id]
  terminate_instance_on_failure = true
  resource_tags                 = { Component = "ci-image-builder", Project = "Innovate-To-Grow" }
  depends_on                    = [aws_iam_role_policy_attachment.builder, aws_route_table_association.ci]
}

resource "aws_imagebuilder_distribution_configuration" "runner" {
  name = "${local.prefix}-image-distribution"
  distribution {
    region = "us-west-2"
    ami_distribution_configuration {
      name     = "i2g-ci-ubuntu24-{{ imagebuilder:buildDate }}"
      ami_tags = { Component = "ci-runners", Project = "Innovate-To-Grow" }
    }
    ssm_parameter_configuration {
      parameter_name = aws_ssm_parameter.runner_ami.name
      data_type      = "aws:ec2:image"
    }
  }
}

resource "aws_imagebuilder_image_pipeline" "runner" {
  name                             = "${local.prefix}-runner-image"
  image_recipe_arn                 = aws_imagebuilder_image_recipe.runner.arn
  infrastructure_configuration_arn = aws_imagebuilder_infrastructure_configuration.runner.arn
  distribution_configuration_arn   = aws_imagebuilder_distribution_configuration.runner.arn
  execution_role                   = aws_iam_role.image_execution.arn
  enhanced_image_metadata_enabled  = false
  image_tests_configuration {
    image_tests_enabled = false
  }
  schedule {
    schedule_expression                = "cron(0 10 ? * SUN *)"
    pipeline_execution_start_condition = "EXPRESSION_MATCH_ONLY"
  }
  depends_on = [aws_iam_role_policy_attachment.image_execution, aws_iam_role_policy.image_parameter]
}

resource "aws_iam_role" "image_cleanup" {
  name = "${local.prefix}-image-cleanup"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow", Principal = { Service = "imagebuilder.amazonaws.com" }, Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "image_cleanup" {
  role       = aws_iam_role.image_cleanup.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/EC2ImageBuilderLifecycleExecutionPolicy"
}

# Weekly rebakes must not accumulate snapshots indefinitely. The selection is
# limited to this fleet's recipe; production AMIs are outside this policy.
resource "aws_imagebuilder_lifecycle_policy" "runner" {
  name           = "${local.prefix}-keep-three-images"
  execution_role = aws_iam_role.image_cleanup.arn
  resource_type  = "AMI_IMAGE"
  status         = "ENABLED"
  resource_selection {
    recipe {
      name             = aws_imagebuilder_image_recipe.runner.name
      semantic_version = "x.x.x"
    }
  }
  policy_detail {
    action {
      type = "DELETE"
      include_resources {
        amis      = true
        snapshots = true
      }
    }
    filter {
      type  = "COUNT"
      value = 3
    }
  }
  depends_on = [aws_iam_role_policy_attachment.image_cleanup]
}
