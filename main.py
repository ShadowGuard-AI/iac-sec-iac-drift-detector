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
    parser.add_argument("-t", "--template", required=True, help="Path to the IaC template file (YAML or JSON).")
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
    Loads the infrastructure state from the state file for every provider.
    Terraform state files are JSON. Pulumi and Kubernetes state files are
    read as JSON or YAML, matching the file extension.
    """
    try:
        # The provider choice changes only how the state file is parsed.
        # Terraform state is always read as JSON, whatever its extension says,
        # while the template's format is chosen by its extension alone.
        if provider == 'terraform':
            with open(state_path, 'r') as f:
                return json.load(f)
        elif provider in ('pulumi', 'kubernetes'):
            with open(state_path, 'r') as f:
                if state_path.endswith(('.yaml', '.yml')):
                    return yaml.safe_load(f)
                elif state_path.endswith('.json'):
                    return json.load(f)
                else:
                    raise ValueError("Unsupported state file format.  Must be YAML or JSON.")
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

def _collect_differences(template_data, state_data, path, differences):
    """
    Walks both structures and appends one line per differing path, naming
    the path and both values.
    """
    if isinstance(template_data, dict) and isinstance(state_data, dict):
        for key in sorted(set(template_data) | set(state_data), key=str):
            child_path = f"{path}.{key}" if path else str(key)
            if key not in template_data:
                differences.append(f"Difference at {child_path}: template=<absent>, state={state_data[key]!r}")
            elif key not in state_data:
                differences.append(f"Difference at {child_path}: template={template_data[key]!r}, state=<absent>")
            else:
                _collect_differences(template_data[key], state_data[key], child_path, differences)
    elif isinstance(template_data, list) and isinstance(state_data, list):
        if len(template_data) != len(state_data):
            differences.append(
                f"Difference at {path or 'root'}: template has {len(template_data)} item(s), "
                f"state has {len(state_data)} item(s)"
            )
        # Lists are compared positionally, over the zip of both. When the
        # lengths differ, the length line above is the only report about the
        # extra items; their contents are never compared, and a reordering of
        # the same items reads as a difference at every moved index.
        for index, (template_item, state_item) in enumerate(zip(template_data, state_data)):
            _collect_differences(template_item, state_item, f"{path}[{index}]", differences)
    # Leaf comparison is plain inequality, so types count: the number 1
    # and the string 1 differ, and a YAML yes parsed as a boolean differs
    # from a JSON true only in spelling, not in value, which the structures
    # cannot show after parsing.
    elif template_data != state_data:
        differences.append(f"Difference at {path or 'root'}: template={template_data!r}, state={state_data!r}")


def compare_infrastructure(template_data, state_data, jsonpath_expression=None):
    """
    Compares the IaC template with the infrastructure state.
    If jsonpath_expression is provided, it filters both sides before
    comparison. Returns one line per differing path, or the no
    differences line when the two sides match.
    """
    if jsonpath_expression:
        try:
            jsonpath_expr = parse(jsonpath_expression)
            # The expression filters both sides into flat lists of matched values,
            # and the walk then compares those lists positionally. The comparison
            # is only meaningful when the expression matches the same things in
            # the same order on both sides; an extra match on one side shifts
            # every later pairing.
            template_data = [match.value for match in jsonpath_expr.find(template_data)]
            state_data = [match.value for match in jsonpath_expr.find(state_data)]
        except Exception as e:
            logging.error(f"Error applying JSONPath expression: {e}")
            raise

    differences = []
    _collect_differences(template_data, state_data, "", differences)

    if differences:
        return ["Significant differences detected between template and state:"] + differences
    return ["No significant differences detected."]

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


        resolved_output = os.path.realpath(args.output)
        if resolved_output in (os.path.realpath(args.template), os.path.realpath(args.state)):
            raise ValueError(f"Output path resolves to an input file, refusing to overwrite it: {args.output}")

        template_data = load_iac_template(args.template)
        state_data = load_infrastructure_state(args.state, args.provider)

        differences = compare_infrastructure(template_data, state_data, args.jsonpath)

        # The report is written before the exit code is decided. A run that
        # finds drift leaves a complete report on disk and then exits 1, so a
        # caller gets the evidence and the failure signal together.
        write_report(differences, args.output)

        if any(line.startswith("Difference at ") for line in differences):
            logging.warning("Drift detected between template and state.")
            exit(1)

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