#!/usr/bin/env python3
"""
CloudFormation template generator for cluster IAM roles using Jinja2.

This script generates CloudFormation templates for cluster-specific IAM roles
by rendering Jinja2 templates with provided parameters. It solves the YAML
limitations of CloudFormation when dealing with dynamic OIDC provider URLs.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, Any

try:
    from jinja2 import Environment, FileSystemLoader, Template
except ImportError:
    print("Error: jinja2 is required. Install with: pip install jinja2")
    sys.exit(1)

# Script directory
SCRIPT_DIR = Path(__file__).parent
TEMPLATES_DIR = SCRIPT_DIR / "templates"
RENDERED_DIR = SCRIPT_DIR / "rendered"

# Default values
DEFAULTS = {
    'project_name': 'multi-tenant-logging',
    'environment': 'development',
    'service_account_namespace': 'logging',
    'vector_service_account_name': 'vector-logs',
    'processor_service_account_name': 'log-processor',
    'oidc_audience': 'openshift'
}

def setup_jinja_environment() -> Environment:
    """Set up Jinja2 environment with proper configuration."""
    if not TEMPLATES_DIR.exists():
        raise FileNotFoundError(f"Templates directory not found: {TEMPLATES_DIR}")
    
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True
    )

def ensure_rendered_dir():
    """Ensure the rendered directory exists."""
    RENDERED_DIR.mkdir(exist_ok=True)

def validate_template_vars(template_vars: Dict[str, Any], template_type: str) -> None:
    """Validate required template variables."""
    required_common = ['cluster_name', 'oidc_provider_url', 'project_name', 'environment']
    
    if template_type == 'vector':
        required = required_common + ['service_account_name', 'service_account_namespace']
    elif template_type == 'processor':
        required = required_common + ['service_account_name', 'service_account_namespace']
    else:
        raise ValueError(f"Unknown template type: {template_type}")
    
    missing = [var for var in required if not template_vars.get(var)]
    if missing:
        raise ValueError(f"Missing required variables for {template_type} template: {missing}")

def render_template(template_type: str, template_vars: Dict[str, Any]) -> str:
    """Render a Jinja2 template with the provided variables."""
    env = setup_jinja_environment()
    
    template_file = f"cluster-{template_type}-role.yaml.j2"
    try:
        template = env.get_template(template_file)
    except Exception as e:
        raise FileNotFoundError(f"Template not found: {template_file}") from e
    
    # Validate variables
    validate_template_vars(template_vars, template_type)
    
    # Render template
    return template.render(**template_vars)

def write_rendered_template(content: str, template_type: str, output_dir: Path = None) -> Path:
    """Write rendered template to file."""
    if output_dir is None:
        output_dir = RENDERED_DIR
    
    output_dir.mkdir(exist_ok=True)
    
    output_file = output_dir / f"cluster-{template_type}-role.yaml"
    output_file.write_text(content)
    
    return output_file

def validate_cloudformation_template(template_path: Path) -> bool:
    """Validate CloudFormation template using AWS CLI."""
    import subprocess
    
    try:
        result = subprocess.run([
            'aws', 'cloudformation', 'validate-template',
            '--template-body', f'file://{template_path}'
        ], capture_output=True, text=True, check=True)
        
        print(f"✅ Template validation successful: {template_path.name}")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Template validation failed: {template_path.name}")
        print(f"Error: {e.stderr}")
        return False
    except FileNotFoundError:
        print("⚠️  AWS CLI not found. Skipping template validation.")
        print("   Install AWS CLI to enable template validation.")
        return True  # Don't fail if AWS CLI isn't available

def main():
    parser = argparse.ArgumentParser(
        description="Generate CloudFormation templates for cluster IAM roles",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate processor role template
  python generate_templates.py processor \\
    --cluster-name ocp-cluster \\
    --oidc-provider oidc.op1.openshiftapps.com/abc123

  # Generate vector role template
  python generate_templates.py vector \\
    --cluster-name my-eks \\
    --oidc-provider oidc.eks.us-east-2.amazonaws.com/id/ABC123 \\
    --oidc-audience sts.amazonaws.com

  # Generate both templates
  python generate_templates.py both \\
    --cluster-name ocp-cluster \\
    --oidc-provider oidc.op1.openshiftapps.com/abc123
        """
    )
    
    parser.add_argument(
        'template_type',
        choices=['vector', 'processor', 'both'],
        help='Type of template to generate'
    )
    
    parser.add_argument(
        '--cluster-name',
        required=True,
        help='Name of the cluster (used for resource naming)'
    )
    
    parser.add_argument(
        '--oidc-provider',
        required=True,
        help='OIDC provider URL (without https://)'
    )
    
    parser.add_argument(
        '--oidc-audience',
        default=DEFAULTS['oidc_audience'],
        choices=['openshift', 'sts.amazonaws.com'],
        help='OIDC audience (default: openshift)'
    )
    
    parser.add_argument(
        '--project-name',
        default=DEFAULTS['project_name'],
        help=f'Project name (default: {DEFAULTS["project_name"]})'
    )
    
    parser.add_argument(
        '--environment',
        default=DEFAULTS['environment'],
        choices=['production', 'staging', 'development'],
        help=f'Environment (default: {DEFAULTS["environment"]})'
    )
    
    parser.add_argument(
        '--service-account-namespace',
        default=DEFAULTS['service_account_namespace'],
        help=f'Service account namespace (default: {DEFAULTS["service_account_namespace"]})'
    )
    
    parser.add_argument(
        '--vector-service-account-name',
        default=DEFAULTS['vector_service_account_name'],
        help=f'Vector service account name (default: {DEFAULTS["vector_service_account_name"]})'
    )
    
    parser.add_argument(
        '--processor-service-account-name',
        default=DEFAULTS['processor_service_account_name'],
        help=f'Processor service account name (default: {DEFAULTS["processor_service_account_name"]})'
    )
    
    parser.add_argument(
        '--validate',
        action='store_true',
        help='Validate generated templates using AWS CLI'
    )
    
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=RENDERED_DIR,
        help=f'Output directory for rendered templates (default: {RENDERED_DIR})'
    )
    
    args = parser.parse_args()
    
    # Update rendered directory if specified
    rendered_dir = args.output_dir
    
    # Build template variables
    base_vars = {
        'cluster_name': args.cluster_name,
        'oidc_provider_url': args.oidc_provider,
        'oidc_audience': args.oidc_audience,
        'project_name': args.project_name,
        'environment': args.environment,
        'service_account_namespace': args.service_account_namespace,
    }
    
    # Determine which templates to generate
    templates_to_generate = []
    if args.template_type in ['vector', 'both']:
        templates_to_generate.append(('vector', {
            **base_vars,
            'service_account_name': args.vector_service_account_name
        }))
    
    if args.template_type in ['processor', 'both']:
        templates_to_generate.append(('processor', {
            **base_vars,
            'service_account_name': args.processor_service_account_name
        }))
    
    # Generate templates
    generated_files = []
    for template_type, template_vars in templates_to_generate:
        try:
            print(f"Generating {template_type} role template...")
            
            # Render template
            content = render_template(template_type, template_vars)
            
            # Write to file
            output_file = write_rendered_template(content, template_type, rendered_dir)
            generated_files.append(output_file)
            
            print(f"✅ Generated: {output_file}")
            
        except Exception as e:
            print(f"❌ Failed to generate {template_type} template: {e}")
            sys.exit(1)
    
    # Validate templates if requested
    if args.validate:
        print("\nValidating generated templates...")
        validation_results = []
        for template_file in generated_files:
            validation_results.append(validate_cloudformation_template(template_file))
        
        if not all(validation_results):
            print("\n❌ Some templates failed validation")
            sys.exit(1)
        else:
            print("\n✅ All templates validated successfully")
    
    print(f"\n🎉 Template generation complete!")
    print(f"Generated files in: {rendered_dir}")
    for file in generated_files:
        print(f"  - {file.name}")

if __name__ == '__main__':
    main()