"""Create auto update CloudWatch events."""

import boto3
import cfnresponse
import os
import logging
import json

client = boto3.client('cloudformation')
event = boto3.client('events')
iam = boto3.client('iam')
aws_lambda = boto3.client('lambda')

function_name = os.environ['FUNCTION_NAME']
region = os.environ['REGION']
account_id = boto3.client('sts').get_caller_identity().get('Account')


# https://stackoverflow.com/questions/37703609/using-python-logging-with-aws-lambda
# while len(logging.root.handlers) > 0:
#     logging.root.removeHandler(logging.root.handlers[-1])
# logging.basicConfig(format='%(asctime)s %(message)s', level=logging.DEBUG)
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


def get_lambda_arn(function_name):
    """Return lambda function arn."""
    response = aws_lambda.get_function(
        FunctionName=function_name
    )
    log.info("get_lambda_name: {}".format(response))
    function_name = response['Configuration']['FunctionArn']
    return function_name


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
    log.info("create_event: {}".format(response))
    return response


def put_targets(stack_name, lambda_arn, toggle_parameter, toggle_values):
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
    log.info("put_targets: {}".format(response))
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
    log.info("lambda_add_resource_policy: {}".format(response))
    return response


def lambda_remove_resource_policy(event_name):
    """Remove resource policy."""
    statement_id = "AWSEvents_{}_{}".format(event_name, function_name)
    response = aws_lambda.remove_permission(
        FunctionName=function_name,
        StatementId=statement_id,
    )
    log.info("lambda_remove_resource_policy: {}".format(response))
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
    log.info("remove_targets: {}".format(response))
    return response


def delete_event(stack_name):
    """Delete target cloudwatch event."""
    event_name = "auto-update-{}".format(stack_name)
    remove_targets(event_name)
    response = event.delete_rule(
        Name=event_name
        )
    log.info("delete_event: {}".format(response))
    return response


def get_parameters(stack_name):
    """Get stack's parameters."""
    stack = client.describe_stacks(StackName=stack_name)['Stacks'][0]
    current_parameter_list = stack['Parameters']
    return current_parameter_list


def lambda_handler(event, context):
    """Parse event."""
    log.info("labmda_handler recieved event: {}".format(event))
    try:
        response_value = event['ResourceProperties']
        response_data = {}
        response_data['Data'] = response_value
        toggle_values = event['ResourceProperties']['ToggleValues']
        toggle_parameter = event['ResourceProperties']['ToggleParameter']
        interval = event['ResourceProperties']['UpdateSchedule']
        stack_name = event['ResourceProperties']['StackName']
        reason = None
        if event['RequestType'] == 'Delete':
            log.info('Recieved Delete event')
            event_name = ("auto-update-{}".format(stack_name))
            try:
                delete_event(stack_name)
                log.info('Deleted event: {}'.format(event_name))
                lambda_remove_resource_policy(event_name)
                log.info('Removed event resource policy.')
                reason = "deleted cw update event"
                cfnresponse.send(event,
                                 context,
                                 cfnresponse.SUCCESS,
                                 response_data,
                                 reason,
                                 "CustomResourcePhyiscalID")
            except Exception as e:
                cfnresponse.send(event,
                                 context,
                                 cfnresponse.SUCCESS,
                                 response_data,
                                 reason,
                                 "CustomResourcePhyiscalID")
                log.error(
                 'Delete event: {} operation failed.'.format(event_name))
                print(str(e), e.args)
                raise
        if event['RequestType'] == 'Create':
            log.info('Recieved Create event')
            event_name = ("auto-update-{}".format(stack_name))
            try:
                create_event(stack_name, interval, toggle_parameter,
                             toggle_values)
                log.info(
                 'Created CloudWatch event: {}'.format(event_name))
                lambda_arn = get_lambda_arn(function_name)
                put_targets(stack_name, lambda_arn, toggle_parameter,
                            toggle_values)
                log.info(
                 'Associated Cloudwatch event {} with {}'.format(
                   event_name, stack_name))
                lambda_add_resource_policy(event_name)
                log.info('Added resource policy for Cloudwatch event.')
                reason = "created cw auto update event"
                cfnresponse.send(event,
                                 context,
                                 cfnresponse.SUCCESS,
                                 response_data,
                                 reason,
                                 "CustomResourcePhyiscalID")
            except Exception as e:
                log.exception('Create event failed')
                print(str(e), e.args)
                cfnresponse.send(event,
                                 context,
                                 cfnresponse.FAILED,
                                 response_data,
                                 reason,
                                 "CustomResourcePhyiscalID")
                raise
        if event['RequestType'] == 'Update':
            log.info('Recieved Update event')
            try:
                stack = (
                 client.describe_stacks(StackName=stack_name)['Stacks'][0])
                if stack['StackStatus'] is not 'CREATE_IN_PROGRESS':
                    create_event(stack_name, interval, toggle_parameter,
                                 toggle_values)
                    log.info(
                     'Succesfully updated stack: {}'.format(stack_name))
                reason = "updated cw event"
                cfnresponse.send(event,
                                 context,
                                 cfnresponse.SUCCESS,
                                 response_data,
                                 reason,
                                 "CustomResourcePhyiscalID")
            except Exception as e:
                log.exception('Update event failed.')
                print(str(e), e.args)
                cfnresponse.send(event,
                                 context,
                                 cfnresponse.FAILED,
                                 response_data,
                                 reason,
                                 "CustomResourcePhyiscalID")
                raise
    except Exception as e:
        log.exception('CloudWatch triggerd update of stack: {} failed.'.format(
           stack_name))
