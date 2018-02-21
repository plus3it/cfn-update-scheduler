"""Find and update tagged cfn stacks."""

from ast import literal_eval
import boto3
import cfnresponse
import json
import os
import logging

cloudformation = boto3.resource('cloudformation')
client = boto3.client('cloudformation')
event = boto3.client('events')
iam = boto3.client('iam')
aws_lambda = boto3.client('lambda')

stage = os.environ['STAGE']
region = os.environ['REGION']
service = os.environ['SERVICE']
function_name = os.environ['FUNCTION_NAME']
account_id = os.environ['ACCOUNT_ID']

function_name = "{}-{}-{}".format(service, stage, function_name)

# https://stackoverflow.com/questions/37703609/using-python-logging-with-aws-lambda
while len(logging.root.handlers) > 0:
    logging.root.removeHandler(logging.root.handlers[-1])
logging.basicConfig(format='%(asctime)s %(message)s', level=logging.INFO)
logformat = '[%(name)s]: %(message)s'
logging.basicConfig(format=logformat, level=logging.INFO)
log = logging.getLogger(__name__)


def create_event(stack_name, interval, toggle_parameter, toggle_values):
    """Create a cloudwatch event."""
    event_name = "auto-update-{}".format(stack_name)
    event_description = "trigger for {} auto update".format(stack_name)
    response = event.put_rule(
        Name=event_name,
        ScheduleExpression=interval,
        State='ENABLED',
        Description=event_description
    )
    log.info(response)
    return response


def put_targets(stack_name, toggle_parameter, toggle_values):
    """Set event target and add constants."""
    """
    Sets event target to source Lambda function, sets stack specific
    constants, and calls the resource policy additon function.
    """
    event_name = "auto-update-{}".format(stack_name)
    target_input = {
      "event_name": "{}".format(event_name),
      "stack_name": "{}".format(stack_name),
      "toggle_parameter": "{}".format(toggle_parameter),
      "toggle_values": "{}".format(toggle_values)
      }
    lambda_arn = "arn:aws:lambda:{}:{}:function:{}".format(
      region, account_id, function_name)
    response = event.put_targets(
        Rule=event_name,
        Targets=[
            {
                'Id': function_name,
                'Arn': lambda_arn,
                'Input': json.dumps(target_input)
            }
        ]
    )
    log.info(response)
    return response


def lambda_add_resource_policy(event_name):
    """Update resource policy."""
    rule_arn = (
      "arn:aws:events:{}:{}:rule/{}".format(region, account_id, event_name))
    statement_id = "AWSEvents_{}_{}".format(event_name, function_name)
    response = aws_lambda.add_permission(
            FunctionName=function_name,
            StatementId=statement_id,
            Action='lambda:InvokeFunction',
            Principal='events.amazonaws.com',
            SourceArn=rule_arn,
        )
    log.info(response)
    return response


def lambda_remove_resource_policy(event_name):
    """Remove resource policy."""
    statement_id = "AWSEvents_{}_{}".format(event_name, function_name)
    response = aws_lambda.remove_permission(
        FunctionName=function_name,
        StatementId=statement_id,
    )
    log.info(response)
    return response


def remove_targets(event_name):
    """Remove CloudWatch event target."""
    """
    Cloudwatch events cannot be deleted if they ref a target
    """
    response = event.remove_targets(
        Rule=event_name,
        Ids=[
            function_name,
            ]
        )
    lambda_remove_resource_policy(event_name)
    log.info(response)
    return response


def delete_event(stack_name):
    """Delete target cloudwatch event."""
    event_name = "auto-update-{}".format(stack_name)
    remove_targets(event_name)
    response = event.delete_rule(
        Name=event_name
        )
    log.info(response)
    return response


def change_toggle(stack_name, toggle_parameter, toggle_values):
    """Change stack update toggle."""
    flagged_stack = cloudformation.Stack(stack_name)
    parameterlist = flagged_stack.parameters
    for index, dictionary in enumerate(parameterlist):
        key = dictionary['ParameterKey']
        value = dictionary['ParameterValue']
        if key == toggle_parameter and value == toggle_values[0]:
            parameterlist[index] = (
             {'ParameterKey': toggle_parameter,
              'ParameterValue': toggle_values[1]})
        elif key == toggle_parameter and value == toggle_values[1]:
            parameterlist[index] = (
              {'ParameterKey': toggle_parameter,
               'ParameterValue': toggle_values[0]})
        else:
            continue
    log.info(parameterlist)
    return parameterlist


def update_stack(stack_name, toggle_parameter, toggle_values):
    """Update stack."""
    # skip the update if the stack_name is None
    if not stack_name:
        return
    stack_parameters = change_toggle(stack_name, toggle_parameter,
                                     toggle_values)
    stack = cloudformation.Stack(stack_name)
    kwargs = {
              'StackName': stack_name,
              'UsePreviousTemplate': True,
              'Parameters': stack_parameters,
              'Capabilities': [
                    'CAPABILITY_IAM',
                    'CAPABILITY_NAMED_IAM'
                ],
              'Tags': stack.tags
    }
    # print(kwargs)
    response = client.update_stack(**kwargs)
    log.info(response)
    return response


def lambda_handler(event, context):
    """Parse event."""
    print(event)
    try:
        response_value = event['ResourceProperties']
        response_data = {}
        response_data['Data'] = response_value
        toggle_values = event['ResourceProperties']['ToggleValues']
        toggle_parameter = event['ResourceProperties']['ToggleParameter']
        interval = event['ResourceProperties']['UpdateSchedule']
        stack_name = event['ResourceProperties']['StackName']
        if event['RequestType'] == 'Delete':
            event_name = ("auto-update-{}".format(stack_name))
            try:
                delete_event(stack_name)
                log.info('Deleted event: {}'.format(event_name))
                cfnresponse.send(event, context, cfnresponse.SUCCESS,
                                 response_data)
            except Exception as e:
                cfnresponse.send(event, context, cfnresponse.SUCCESS,
                                 response_data)
                log.error(
                 'Delete event: {} operation failed.'.format(event_name))
                raise
        if event['RequestType'] == 'Create':
            event_name = ("auto-update-{}".format(stack_name))
            try:
                create_event(stack_name, interval, toggle_parameter,
                             toggle_values)
                log.info(
                 'Created CloudWatch event: {}'.format(event_name))
                put_targets(stack_name, toggle_parameter, toggle_values)
                log.info(
                 'Associated Cloudwatch event {} with {}'.format(
                   event_name, stack_name))
                lambda_add_resource_policy(event_name)
                log.info('Added resource policy for Cloudwatch event.')
                cfnresponse.send(event, context, cfnresponse.SUCCESS,
                                 response_data, "CustomResourcePhyiscalID")
            except Exception as e:
                log.error('Create event failed.')
                print(str(e), e.args)
                cfnresponse.send(event, context, cfnresponse.FAILED,
                                 response_data, "CustomResourcePhyiscalID")
                raise
        if event['RequestType'] == 'Update':
            try:
                create_event(stack_name, interval, toggle_parameter,
                             toggle_values)
                log.info('Succesfully updated stack: {}'.format(stack_name))
                cfnresponse.send(event, context, cfnresponse.SUCCESS,
                                 response_data, "CustomResourcePhyiscalID")
            except Exception as e:
                log.error('Update event failed.')
                print(str(e), e.args)
                cfnresponse.send(event, context, cfnresponse.FAILED,
                                 response_data, "CustomResourcePhyiscalID")
                raise
    except KeyError:
        try:
            stack_name = event['stack_name']
            toggle_parameter = event['toggle_parameter']
            toggle_values = literal_eval(event['toggle_values'])
            update_stack(stack_name, toggle_parameter, toggle_values)
            log.info(
             'CloudWatch successfully triggered update of stack: {}'.format(
               stack_name))
        except Exception as e:
            log.error('CloudWatch triggerd update of stack: {} failed.'.format(
               stack_name))
            print(str(e), e.args)
