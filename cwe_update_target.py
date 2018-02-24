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


def assume_role(role_arn, duration):
    """Assume stack update role."""
    response = sts.assume_role(
        RoleArn=role_arn,
        RoleSessionName='cwe_update_target_LambdaFunction',
        DurationSeconds=duration,
    )
    log.info("assume_role: {}".format(response))
    return response


def get_elevated_session(assume_role_response):
    """Create new boto3 session with assumed role."""
    update_stack_session = boto3.Session(
     aws_access_key_id=assume_role_response['Credentials']['AccessKeyId'],
     aws_secret_access_key=assume_role_response['Credentials']['SecretAccessKey'],
     aws_session_token=assume_role_response['Credentials']['SessionToken'])
    elevated_cfn_client = update_stack_session.client('cloudformation')
    return elevated_cfn_client


def get_metrics(event_name):
    """Get event invoke count."""
    response = cloudwatch.get_metric_statistics(
        Namespace='AWS/Events',
        MetricName='Invocations',
        Dimensions=[
            {
                'Name': 'RuleName',
                'Value': event_name,
            },
        ],
        StartTime=datetime.now() - timedelta(days=1),
        EndTime=datetime.now() + timedelta(days=1),
        Period=86400,
        Statistics=[
            'Sum',
        ],
        Unit='Count'
    )
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
        if not get_metrics(event_name)['Datapoints'] or (
          stack['StackStatus'] is not "CREATE_IN_PROGRESS"):
            duration = 3600  # in seconds. 900 (15min) or greater.
            update_stack_role = assume_role(stack_update_arn, duration)
            log.info("Assumed StackUpdateRole for {} seconds".format(duration))
            elevated_cfn_client = get_elevated_session(update_stack_role)
            log.info("Retrieved elevated cfn client.")
            update_stack(elevated_cfn_client, stack_name, toggle_parameter,
                         toggle_values)
            log.info(
             'CloudWatch successfully triggered update of stack: {}'.format(
               stack_name))
    except Exception as e:
        log.exception('CloudWatch triggerd update of stack: {} failed.'.format(
           stack_name))
