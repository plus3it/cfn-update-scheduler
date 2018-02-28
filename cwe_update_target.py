"""Update stacks."""

from ast import literal_eval
from datetime import datetime, timedelta
import os
import boto3
import logging
import traceback

client = boto3.client('cloudformation')
cloudwatch = boto3.client('cloudwatch')
sts = boto3.client('sts')

stack_update_arn = os.environ['STACK_UPDATE_ARN']

# https://stackoverflow.com/questions/37703609/using-python-logging-with-aws-lambda
# while len(logging.root.handlers) > 0:
#     logging.root.removeHandler(logging.root.handlers[-1])
# logging.basicConfig(format='%(asctime)s %(message)s', level=logging.DEBUG)
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


def get_assume_role_input(role_arn, duration):
    """Create input for assume_role."""
    assume_role_input = {
        'RoleArn': role_arn,
        'RoleSessionName': 'cwe_update_target_LambdaFunction',
        'DurationSeconds': duration
    }
    return assume_role_input


def assume_role(**kwargs):
    """Assume stack update role."""
    response = sts.assume_role(**kwargs)
    log.info("assume_role: {}".format(response))
    return response


def get_elevated_session_input(response):
    """Create input for get_elevated_session."""
    elevated_session_input = {
     'aws_access_key_id': response['Credentials']['AccessKeyId'],
     'aws_secret_access_key': response['Credentials']['SecretAccessKey'],
     'aws_session_token': response['Credentials']['SessionToken']
    }
    return elevated_session_input


def get_elevated_session(**kwargs):
    """Create new boto3 session with assumed role."""
    update_stack_session = boto3.Session(**kwargs)
    elevated_cfn_client = update_stack_session.client('cloudformation')
    return elevated_cfn_client


def get_metrics_input(event_name):
    """Create get_metrics input."""
    get_metrics_input = {
        'Namespace': 'AWS/Events',
        'MetricName': 'Invocations',
        'Dimensions': [
            {
                'Name': 'RuleName',
                'Value': event_name,
            },
        ],
        'StartTime': datetime.now() - timedelta(days=1),
        'EndTime': datetime.now() + timedelta(days=1),
        'Period': 86400,
        'Statistics': [
            'Sum',
        ],
        'Unit': 'Count'
    }
    return get_metrics_input


def get_metrics(**kwargs):
    """Get event invoke count."""
    response = cloudwatch.get_metric_statistics(**kwargs)
    log.info("get_metrics: {}".format(response))
    return response


def get_parameters(stack_name):
    """Get stack's parameters."""
    stack = client.describe_stacks(StackName=stack_name)['Stacks'][0]
    current_parameter_list = stack['Parameters']
    return current_parameter_list


def change_toggle(parameter_list, toggle_parameter, toggle_values):
    """Change stack update toggle."""
    for index, dictionary in enumerate(parameter_list):
        key = dictionary['ParameterKey']
        value = dictionary['ParameterValue']
        if key == toggle_parameter and value == toggle_values[0]:
            parameter_list[index] = (
             {'ParameterKey': toggle_parameter,
              'ParameterValue': toggle_values[1]})
        elif key == toggle_parameter and value == toggle_values[1]:
            parameter_list[index] = (
              {'ParameterKey': toggle_parameter,
               'ParameterValue': toggle_values[0]})
        else:
            continue
    updated_parameter_list = parameter_list
    log.info("updated parameter list: {}".format(updated_parameter_list))
    return updated_parameter_list


def update_stack(elevated_cfn_client, stack_name, toggle_parameter,
                 toggle_values):
    """Update stack."""
    # skip the update if the stack_name is None
    if not stack_name:
        return
    stack_parameters = change_toggle(get_parameters(stack_name),
                                     toggle_parameter,
                                     toggle_values)
    stack = client.describe_stacks(StackName=stack_name)['Stacks'][0]
    kwargs = {
              'StackName': stack_name,
              'UsePreviousTemplate': True,
              'Parameters': stack_parameters,
              'Capabilities': [
                    'CAPABILITY_IAM',
                    'CAPABILITY_NAMED_IAM'
                ],
              'Tags': stack['Tags']
    }
    # print(kwargs)
    response = elevated_cfn_client.update_stack(**kwargs)
    log.info("update_stack: {}".format(response))
    return response


def assumed_role_update_stack(stack_name, toggle_parameter, toggle_values,
                              duration):
    """Update stack with assumed role."""
    assume_role_input = get_assume_role_input(stack_update_arn, duration)
    assume_role_response = assume_role(**assume_role_input)
    log.info("Assumed StackUpdateRole for {} seconds".format(duration))

    elevated_session_input = get_elevated_session_input(assume_role_response)
    elevated_cfn_client = get_elevated_session(**elevated_session_input)
    log.info("Retrieved elevated cfn client.")

    update_stack(elevated_cfn_client, stack_name, toggle_parameter,
                 toggle_values)
    log.info('CloudWatch successfully triggered update of stack: {}'.format(
       stack_name))


def lambda_handler(event, context):
    """Parse event."""
    # print(event)
    try:
        event_name = event['event_name']
        stack_name = event['stack_name']
        toggle_parameter = event['toggle_parameter']
        toggle_values = literal_eval(event['toggle_values'])
        stack = client.describe_stacks(StackName=stack_name)['Stacks'][0]
        # prevent update if trigger is being run for the first time
        metrics = get_metrics(**get_metrics_input(event_name))
        invoke_update_metric = metrics['Datapoints']
        if not invoke_update_metric or (
         stack['StackStatus'] is not "CREATE_IN_PROGRESS"):
            duration = 3600  # in seconds. 900 (15min) or greater.
            assumed_role_update_stack(stack_name, toggle_parameter,
                                      toggle_values, duration)
    except Exception as e:
        log.exception('CloudWatch triggerd update failed.')
