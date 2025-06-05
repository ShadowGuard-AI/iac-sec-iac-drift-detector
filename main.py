import argparse
import logging
import yaml
import json
import os
import subprocess
from jsonpath_ng.ext import parse

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def setup_argparse():
    """
    Sets up the argument parser for the CLI.
    """
    parser = argparse.ArgumentParser(description="Detects drift between IaC templates and deployed infrastructure.")
    parser.add_argument("-t", "--template", required=True, help="Path to the IaC template file (e.g., Terraform or Kubernetes YAML).")
    parser.add_argument("-p", "--provider", required=True, choices=['terraform', 'pulumi', 'kubernetes'], help="Infrastructure provider (terraform, pulumi, kubernetes).")
    parser.add_argument("-s", "--state", required=True, help="Path to the state file or live infrastructure details (e.g., Terraform state, Pulumi stack, Kubernetes cluster config).")
    parser.add_argument("-o", "--output", default="drift_report.txt", help="Output file for the drift report (default: drift_report.txt).")
    parser.add_argument("-j", "--jsonpath", help="JSONPath expression to filter specific resources in the state file (optional). Example: $.resources[*].instances[*].attributes")
    return parser.parse_args()

def load_iac_template(template_path):
    """
    Loads the IaC template from the given path.
    Supports YAML and JSON formats.
    """
    try:
        with open(template_path, 'r') as f:
            if template_path.endswith(('.yaml', '.yml')):
                return yaml.safe_load(f)
            elif template_path.endswith('.json'):
                return json.load(f)
            else:
                raise ValueError("Unsupported template file format.  Must be YAML or JSON.")
    except FileNotFoundError:
        logging.error(f"Template file not found: {template_path}")
        raise
    except yaml.YAMLError as e:
        logging.error(f"Error parsing YAML template: {e}")
        raise
    except json.JSONDecodeError as e:
        logging.error(f"Error parsing JSON template: {e}")
        raise
    except Exception as e:
        logging.error(f"Error loading IaC template: {e}")
        raise


def load_infrastructure_state(state_path, provider):
    """
    Loads the infrastructure state based on the provider.
    For Terraform, reads the state file.
    For Pulumi and Kubernetes, attempts to retrieve live infrastructure details.
    """
    try:
        if provider == 'terraform':
            with open(state_path, 'r') as f:
                return json.load(f)
        elif provider == 'pulumi':
            # Implement Pulumi stack retrieval here.  Requires Pulumi CLI setup and login.
            # Example (replace with actual Pulumi command):
            # pulumi_cmd = ["pulumi", "stack", "output", "--json"]
            # result = subprocess.run(pulumi_cmd, capture_output=True, text=True, check=True)
            # return json.loads(result.stdout)

            # Placeholder:
            logging.warning("Pulumi state retrieval is not fully implemented. Returning empty dictionary.")
            return {}
        elif provider == 'kubernetes':
            # Implement Kubernetes resource retrieval here.  Requires kubectl access.
            # Example (replace with actual kubectl commands):
            # kubectl_cmd = ["kubectl", "get", "pods", "-o", "json"]
            # result = subprocess.run(kubectl_cmd, capture_output=True, text=True, check=True)
            # return json.loads(result.stdout)

            # Placeholder:
            logging.warning("Kubernetes state retrieval is not fully implemented. Returning empty dictionary.")
            return {}
        else:
            raise ValueError(f"Unsupported provider: {provider}")

    except FileNotFoundError:
        logging.error(f"State file not found: {state_path}")
        raise
    except json.JSONDecodeError as e:
        logging.error(f"Error parsing JSON state: {e}")
        raise
    except subprocess.CalledProcessError as e:
        logging.error(f"Error retrieving state from provider: {e}.  Command: {e.cmd}, Return code: {e.returncode}, Output: {e.output}")
        raise
    except Exception as e:
        logging.error(f"Error loading infrastructure state: {e}")
        raise

def compare_infrastructure(template_data, state_data, jsonpath_expression=None):
    """
    Compares the IaC template with the infrastructure state.
    If jsonpath_expression is provided, it filters the state data before comparison.
    """
    differences = []

    if jsonpath_expression:
        try:
            jsonpath_expr = parse(jsonpath_expression)
            state_data = [match.value for match in jsonpath_expr.find(state_data)]
        except Exception as e:
            logging.error(f"Error applying JSONPath expression: {e}")
            raise

    # Basic comparison - replace with more sophisticated logic as needed.
    #  This is a placeholder and needs to be adapted to the specific IaC structure.
    if template_data != state_data:
        differences.append("Significant differences detected between template and state.")
    else:
        differences.append("No significant differences detected.")

    return differences

def write_report(report, output_file):
    """
    Writes the drift report to the specified output file.
    """
    try:
        with open(output_file, 'w') as f:
            for line in report:
                f.write(line + "\n")
        logging.info(f"Drift report written to: {output_file}")
    except Exception as e:
        logging.error(f"Error writing report to file: {e}")
        raise

def main():
    """
    Main function to execute the IaC drift detector.
    """
    try:
        args = setup_argparse()

        # Input Validation
        if not os.path.exists(args.template):
            raise FileNotFoundError(f"Template file not found: {args.template}")
        if not os.path.exists(args.state):
            raise FileNotFoundError(f"State file not found: {args.state}")


        template_data = load_iac_template(args.template)
        state_data = load_infrastructure_state(args.state, args.provider)

        differences = compare_infrastructure(template_data, state_data, args.jsonpath)

        write_report(differences, args.output)

    except FileNotFoundError as e:
        print(f"Error: {e}")
        logging.error(e)
        exit(1)
    except ValueError as e:
        print(f"Error: {e}")
        logging.error(e)
        exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        logging.exception("An unexpected error occurred:")
        exit(1)

if __name__ == "__main__":
    main()