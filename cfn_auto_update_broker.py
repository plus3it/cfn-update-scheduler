"""Create auto update CloudWatch events."""

import boto3
import cfnresponse
import os
import logging
import json

client = boto3.client('cloudformation')
event = boto3.client('events')
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


class AWSLambda(object):
    """Define AWS lambda function and associated operations."""

    def __init__(self, function_name, event_name):
        """Define AWS lambda function components."""
        self.name = function_name
        self.event_name = event_name
        self.statement_id = "AWSEvents_{}_{}".format(self.event_name,
                                                     self.name)
        self.rule_arn = "arn:aws:events:{}:{}:rule/{}".format(region,
                                                              account_id,
                                                              self.event_name)
        self.get_function_input = {'FunctionName': self.name}
        self.add_permission_input = {
            'FunctionName': self.name,
            'StatementId': self.statement_id,
            'Action': 'lambda:InvokeFunction',
            'Principal': 'events.amazonaws.com',
            'SourceArn': self.rule_arn,
        }
        self.remove_permission_input = {
            'FunctionName': self.name,
            'StatementId': self.statement_id
        }


class CloudwatchEvent(object):
    """Define Cloudwatch event and associated operations."""

    def __init__(self, stack_name, interval, toggle_parameter,
                 toggle_values):
        """Define Cloudwatch event components."""
        self.stack_name = stack_name
        self.name = "auto-update-{}".format(self.stack_name)
        self.interval = interval
        self.toggle_parameter = toggle_parameter
        self.toggle_values = toggle_values
        self.description = "trigger for {} auto update".format(self.stack_name)
        self.target_function_name = function_name
        self.target_lambda_arn = get_lambda_arn(
         FunctionName=self.target_function_name)
        self.event_constant = {
             'event_name': self.name,
             'stack_name': self.stack_name,
             'toggle_parameter': self.toggle_parameter,
             'toggle_values': self.toggle_values
           }
        self.rule_text = {
            'Name': self.name,
            'ScheduleExpression': self.interval,
            'State': 'ENABLED',
            'Description': self.description
        }
        self.put_targets_input = {
             'Rule': self.name,
             'Targets': [
                {
                    'Id': self.target_function_name,
                    'Arn': self.target_lambda_arn,
                    'Input': json.dumps(self.event_constant)
                }
             ]
        }
        self.remove_targets_input = {
            'Rule': self.name,
            'Ids': [
                self.target_function_name,
                ]
        }
        self.delete_rule_input = {
            'Name': self.name
        }


def get_lambda_arn(**kwargs):
    """Return lambda function arn."""
    response = aws_lambda.get_function(**kwargs)
    log.info("get_lambda_name: {}".format(response))
    lambda_arn = response['Configuration']['FunctionArn']
    return lambda_arn


def lambda_add_resource_policy(**kwargs):
    """Update lambda resource policy."""
    response = aws_lambda.add_permission(**kwargs)
    log.info("lambda_add_resource_policy: {}".format(response))
    return response


def lambda_remove_resource_policy(**kwargs):
    """Remove lambda resource policy."""
    response = aws_lambda.remove_permission(**kwargs)
    log.info("lambda_remove_resource_policy: {}".format(response))
    return response


def create_event(**kwargs):
    """Create a cloudwatch event."""
    response = event.put_rule(**kwargs)
    log.info("create_event: {}".format(response))
    return response


def put_targets(**kwargs):
    """Set Cloudwatch event target."""
    response = event.put_targets(**kwargs)
    log.info("put_targets: {}".format(response))
    return response


def remove_event_targets(**kwargs):
    """Remove CloudWatch event target."""
    """
    Cloudwatch events cannot be deleted if they ref a target
    """
    response = event.remove_targets(**kwargs)
    log.info("remove_targets: {}".format(response))
    return response


def delete_event(**kwargs):
    """Delete target cloudwatch event."""
    response = event.delete_rule(**kwargs)
    log.info("delete_event: {}".format(response))
    return response


def lambda_handler(event, context):
    """Parse event."""
    log.info("labmda_handler recieved event: {}".format(event))
    response_type = cfnresponse.FAILED
    try:
        response_value = event['ResourceProperties']
        response_data = {}
        response_data['Data'] = response_value
        toggle_values = event['ResourceProperties']['ToggleValues']
        toggle_parameter = event['ResourceProperties']['ToggleParameter']
        interval = event['ResourceProperties']['UpdateSchedule']
        stack_name = event['ResourceProperties']['StackName']
        reason = None

        def cfn_delete_request():
            """Delete event."""
            log.info('Recieved Delete event')

            event_obj = CloudwatchEvent(stack_name, None, None, None)
            remove_event_targets(**event_obj.remove_targets_input)
            delete_event(**event_obj.delete_rule_input)

            aws_lambda_obj = AWSLambda(function_name, event_obj.name)
            lambda_remove_resource_policy(
             **aws_lambda_obj.remove_permission_input)

            return cfnresponse.SUCCESS

        def cfn_update_request():
            """Update event."""
            log.info('Recieved Update event')
            event_obj = CloudwatchEvent(stack_name, interval, toggle_parameter,
                                        toggle_values)
            stack = client.describe_stacks(StackName=stack_name)['Stacks'][0]
            if stack['StackStatus'] is not 'CREATE_IN_PROGRESS':
                create_event(**event_obj.rule_text)
                log.info('Succesfully updated auto-update rule: {}'.format(
                 event_obj.name))

            return cfnresponse.SUCCESS

        def cfn_create_request():
            """Create event."""
            log.info('Recieved Create event')

            event_obj = CloudwatchEvent(stack_name, interval, toggle_parameter,
                                        toggle_values)
            create_event(**event_obj.rule_text)
            put_targets(**event_obj.put_targets_input)

            aws_lambda_obj = AWSLambda(function_name, event_obj.name)
            lambda_add_resource_policy(**aws_lambda_obj.add_permission_input)
            return cfnresponse.SUCCESS

        if event['RequestType'] == "Delete":
            response_type = cfn_delete_request()
        if event['RequestType'] == "Create":
            response_type = cfn_create_request()
        if event['RequestType'] == "Update":
            response_type = cfn_update_request()
        if event['RequestType'] == "Create Traceback":
            response_type = cfnresponse.FAILED
            log.error("Create error occured and rollback intitiated.")
        if event['RequestType'] == "Delete Traceback":
            log.exception('Error with delete action occured.' +
                          'View the logs for more deatils.')
            raise Exception
        else:
            log.exception('Unknown request type')
            raise Exception
    except Exception as e:
        log.exception(
         'Error: Failed on event type {}'.format(event['RequestType']))
        print(str(e), e.args)
        raise
    finally:
        cfnresponse.send(event, context, response_type, response_data, reason,
                         "CustomResourcePhyiscalID")
