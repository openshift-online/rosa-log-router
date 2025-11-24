// TERRAMATE: GENERATED AUTOMATICALLY DO NOT EDIT

variable "access_key" {
}
variable "secret_key" {
}
variable "region" {
}
variable "pord_2_account_id" {
}
terraform {
  required_version = ">= 1.8.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
  backend "s3" {
  }
}
provider "aws" {
  access_key = var.access_key
  region     = var.region
  secret_key = var.secret_key
  default_tags {
    tags = {
      app-code               = "OSD-002"
      cost-center            = "148"
      managed_by_integration = "terraform-repo"
      service-phase          = "prod"
    }
  }
}
provider "aws" {
  alias  = "af-south-1"
  region = "af-south-1"
  default_tags {
    tags = {
      app-code               = "OSD-002"
      cost-center            = "148"
      managed_by_integration = "terraform-repo"
      service-phase          = "prod"
    }
  }
}
provider "aws" {
  alias  = "ap-east-1"
  region = "ap-east-1"
  default_tags {
    tags = {
      app-code               = "OSD-002"
      cost-center            = "148"
      managed_by_integration = "terraform-repo"
      service-phase          = "prod"
    }
  }
}
provider "aws" {
  alias  = "ap-northeast-1"
  region = "ap-northeast-1"
  default_tags {
    tags = {
      app-code               = "OSD-002"
      cost-center            = "148"
      managed_by_integration = "terraform-repo"
      service-phase          = "prod"
    }
  }
}
provider "aws" {
  alias  = "ap-northeast-2"
  region = "ap-northeast-2"
  default_tags {
    tags = {
      app-code               = "OSD-002"
      cost-center            = "148"
      managed_by_integration = "terraform-repo"
      service-phase          = "prod"
    }
  }
}
provider "aws" {
  alias  = "ap-northeast-3"
  region = "ap-northeast-3"
  default_tags {
    tags = {
      app-code               = "OSD-002"
      cost-center            = "148"
      managed_by_integration = "terraform-repo"
      service-phase          = "prod"
    }
  }
}
provider "aws" {
  alias  = "ap-south-1"
  region = "ap-south-1"
  default_tags {
    tags = {
      app-code               = "OSD-002"
      cost-center            = "148"
      managed_by_integration = "terraform-repo"
      service-phase          = "prod"
    }
  }
}
provider "aws" {
  alias  = "ap-south-2"
  region = "ap-south-2"
  default_tags {
    tags = {
      app-code               = "OSD-002"
      cost-center            = "148"
      managed_by_integration = "terraform-repo"
      service-phase          = "prod"
    }
  }
}
provider "aws" {
  alias  = "ap-southeast-1"
  region = "ap-southeast-1"
  default_tags {
    tags = {
      app-code               = "OSD-002"
      cost-center            = "148"
      managed_by_integration = "terraform-repo"
      service-phase          = "prod"
    }
  }
}
provider "aws" {
  alias  = "ap-southeast-2"
  region = "ap-southeast-2"
  default_tags {
    tags = {
      app-code               = "OSD-002"
      cost-center            = "148"
      managed_by_integration = "terraform-repo"
      service-phase          = "prod"
    }
  }
}
provider "aws" {
  alias  = "ap-southeast-3"
  region = "ap-southeast-3"
  default_tags {
    tags = {
      app-code               = "OSD-002"
      cost-center            = "148"
      managed_by_integration = "terraform-repo"
      service-phase          = "prod"
    }
  }
}
provider "aws" {
  alias  = "ap-southeast-4"
  region = "ap-southeast-4"
  default_tags {
    tags = {
      app-code               = "OSD-002"
      cost-center            = "148"
      managed_by_integration = "terraform-repo"
      service-phase          = "prod"
    }
  }
}
provider "aws" {
  alias  = "ap-southeast-5"
  region = "ap-southeast-5"
  default_tags {
    tags = {
      app-code               = "OSD-002"
      cost-center            = "148"
      managed_by_integration = "terraform-repo"
      service-phase          = "prod"
    }
  }
}
provider "aws" {
  alias  = "ap-southeast-6"
  region = "ap-southeast-6"
  default_tags {
    tags = {
      app-code               = "OSD-002"
      cost-center            = "148"
      managed_by_integration = "terraform-repo"
      service-phase          = "prod"
    }
  }
}
provider "aws" {
  alias  = "ap-southeast-7"
  region = "ap-southeast-7"
  default_tags {
    tags = {
      app-code               = "OSD-002"
      cost-center            = "148"
      managed_by_integration = "terraform-repo"
      service-phase          = "prod"
    }
  }
}
provider "aws" {
  alias  = "ca-central-1"
  region = "ca-central-1"
  default_tags {
    tags = {
      app-code               = "OSD-002"
      cost-center            = "148"
      managed_by_integration = "terraform-repo"
      service-phase          = "prod"
    }
  }
}
provider "aws" {
  alias  = "ca-west-1"
  region = "ca-west-1"
  default_tags {
    tags = {
      app-code               = "OSD-002"
      cost-center            = "148"
      managed_by_integration = "terraform-repo"
      service-phase          = "prod"
    }
  }
}
provider "aws" {
  alias  = "eu-central-1"
  region = "eu-central-1"
  default_tags {
    tags = {
      app-code               = "OSD-002"
      cost-center            = "148"
      managed_by_integration = "terraform-repo"
      service-phase          = "prod"
    }
  }
}
provider "aws" {
  alias  = "eu-central-2"
  region = "eu-central-2"
  default_tags {
    tags = {
      app-code               = "OSD-002"
      cost-center            = "148"
      managed_by_integration = "terraform-repo"
      service-phase          = "prod"
    }
  }
}
provider "aws" {
  alias  = "eu-north-1"
  region = "eu-north-1"
  default_tags {
    tags = {
      app-code               = "OSD-002"
      cost-center            = "148"
      managed_by_integration = "terraform-repo"
      service-phase          = "prod"
    }
  }
}
provider "aws" {
  alias  = "eu-south-1"
  region = "eu-south-1"
  default_tags {
    tags = {
      app-code               = "OSD-002"
      cost-center            = "148"
      managed_by_integration = "terraform-repo"
      service-phase          = "prod"
    }
  }
}
provider "aws" {
  alias  = "eu-south-2"
  region = "eu-south-2"
  default_tags {
    tags = {
      app-code               = "OSD-002"
      cost-center            = "148"
      managed_by_integration = "terraform-repo"
      service-phase          = "prod"
    }
  }
}
provider "aws" {
  alias  = "eu-west-1"
  region = "eu-west-1"
  default_tags {
    tags = {
      app-code               = "OSD-002"
      cost-center            = "148"
      managed_by_integration = "terraform-repo"
      service-phase          = "prod"
    }
  }
}
provider "aws" {
  alias  = "eu-west-2"
  region = "eu-west-2"
  default_tags {
    tags = {
      app-code               = "OSD-002"
      cost-center            = "148"
      managed_by_integration = "terraform-repo"
      service-phase          = "prod"
    }
  }
}
provider "aws" {
  alias  = "eu-west-3"
  region = "eu-west-3"
  default_tags {
    tags = {
      app-code               = "OSD-002"
      cost-center            = "148"
      managed_by_integration = "terraform-repo"
      service-phase          = "prod"
    }
  }
}
provider "aws" {
  alias  = "il-central-1"
  region = "il-central-1"
  default_tags {
    tags = {
      app-code               = "OSD-002"
      cost-center            = "148"
      managed_by_integration = "terraform-repo"
      service-phase          = "prod"
    }
  }
}
provider "aws" {
  alias  = "us-east-1"
  region = "us-east-1"
  default_tags {
    tags = {
      app-code               = "OSD-002"
      cost-center            = "148"
      managed_by_integration = "terraform-repo"
      service-phase          = "prod"
    }
  }
}
provider "aws" {
  alias  = "me-central-1"
  region = "me-central-1"
  default_tags {
    tags = {
      app-code               = "OSD-002"
      cost-center            = "148"
      managed_by_integration = "terraform-repo"
      service-phase          = "prod"
    }
  }
}
provider "aws" {
  alias  = "me-south-1"
  region = "me-south-1"
  default_tags {
    tags = {
      app-code               = "OSD-002"
      cost-center            = "148"
      managed_by_integration = "terraform-repo"
      service-phase          = "prod"
    }
  }
}
provider "aws" {
  alias  = "mx-central-1"
  region = "mx-central-1"
  default_tags {
    tags = {
      app-code               = "OSD-002"
      cost-center            = "148"
      managed_by_integration = "terraform-repo"
      service-phase          = "prod"
    }
  }
}
provider "aws" {
  alias  = "sa-east-1"
  region = "sa-east-1"
  default_tags {
    tags = {
      app-code               = "OSD-002"
      cost-center            = "148"
      managed_by_integration = "terraform-repo"
      service-phase          = "prod"
    }
  }
}
provider "aws" {
  alias  = "us-east-2"
  region = "us-east-2"
  default_tags {
    tags = {
      app-code               = "OSD-002"
      cost-center            = "148"
      managed_by_integration = "terraform-repo"
      service-phase          = "prod"
    }
  }
}
provider "aws" {
  alias  = "us-west-2"
  region = "us-west-2"
  default_tags {
    tags = {
      app-code               = "OSD-002"
      cost-center            = "148"
      managed_by_integration = "terraform-repo"
      service-phase          = "prod"
    }
  }
}
