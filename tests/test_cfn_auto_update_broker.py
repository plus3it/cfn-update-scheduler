"""Perform unit test on cfn_auto_update_broker.py."""

import zipfile
import io
import mock
import pytest
import boto3
import os
from moto import mock_events, mock_sts, mock_lambda
from ast import literal_eval
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# mock env vars before import
mock_env = mock.patch.dict(
  os.environ, {
                'FUNCTION_NAME': 'cfn-update-scheduler-dev-cwe_update_target',
                'REGION': 'us-east-1',
                }
            )
mock_env.start()

region = os.environ['REGION']
function_name = os.environ['FUNCTION_NAME']

from cfn_auto_update_broker import (get_lambda_arn,
                                    create_event,
                                    put_targets,
                                    delete_event,
                                    lambda_add_resource_policy,
                                    lambda_remove_resource_policy,
                                    lambda_handler)

mock = mock_sts()
mock.start()
account_id = boto3.client('sts').get_caller_identity().get('Account')
mock.stop()


# TestFunction plagarized from:
# https://github.com/spulec/moto/issues/1338
def _process_lambda(func_str):
    zip_output = io.BytesIO()
    zip_file = zipfile.ZipFile(zip_output, 'w', zipfile.ZIP_DEFLATED)
    zip_file.writestr('lambda_function.py', func_str)
    zip_file.close()
    zip_output.seek(0)
    return zip_output.read()


def get_test_zip_file1():
    """Return test zip file."""
    pfunc = """
def lambda_handler(event, context):
    return event
"""
    return _process_lambda(pfunc)


class TestGetFunction(object):
    """Create mock lambda function."""

    @mock_lambda
    def test_function_response(self):
        """Test that the function is created."""
        # create lambda function in current aws accoint
        client = boto3.client('lambda', region_name='us-east-1')
        self.create_test_function(client)
        # confirm test function exists and validate get_lambda_arn
        lambda_arn = get_lambda_arn('test_function')
        test_arn = self.get_test_function_arn(client)
        assert lambda_arn == test_arn

    @pytest.fixture(scope="session")
    def create_test_function(self, client):
        """Create mock the lambda function."""
        # create function
        response = client.create_function(
            FunctionName='test_function',
            Runtime='python2.7',
            Role='test_role',
            Handler='test_handler',
            Code={
                'ZipFile': get_test_zip_file1(),
            }
        )
        print('response=', response)

    def get_test_function_arn(self, client):
        """Get arn of test function."""
        response = client.get_function(FunctionName='test_function')
        test_arn = response['Configuration']['FunctionArn']
        return test_arn


class TestEventActions(object):
    """Create mock Cloudwatch event."""

    @mock_events
    @pytest.fixture
    def set_up(self):
        """Create event."""
        self.event = boto3.client('events', region_name='us-east-1')
        self.stack_name = 'test-stack'
        self.event_name = "auto-update-{}".format(self.stack_name)
        self.toggle_parameter = 'TestToggleParameter'
        self.toggle_values = literal_eval("['A','B']")
        self.lambda_arn = "arn:aws:lambda:{}:{}:function:test_function:$LATEST".format(region, account_id)
        self.interval = "rate(5 minutes)"
        self.event_description = "trigger for {} auto update".format(
         self.stack_name)
        self.statement_id = "AWSEvents_{}_{}".format(self.event_name,
                                                     function_name)
        self.rule_arn = "arn:aws:events:{}:{}:rule/{}".format(region,
                                                              account_id,
                                                              self.event_name)

    # @pytest.fixture
    # @mock_events
    # def local_event(self, set_up):
    #     """Create a local test event to validate against."""
    #     event_description = "trigger for {} auto update".format('test-stack')
    #     response = self.event.put_rule(
    #                             Name='auto-update-test-stack',
    #                             ScheduleExpression="rate(5 minutes)",
    #                             State='ENABLED',
    #                             Description=event_description
    #                         )
    #     return response

    @mock_events
    def test_create_event(self, set_up):
        """Test cfn_auto_update_broker create_event."""
        response = create_event(self.stack_name, 'rate(5 minutes)',
                                'TestToggleParameter', self.toggle_values)
        events = boto3.client('events', region_name='us-east-1')
        rule = events.describe_rule(Name=self.event_name)
        assert rule['Arn'] == response['RuleArn']
        assert response['ResponseMetadata']['HTTPStatusCode'] == 200

    @mock_events
    def test_put_targets(self, set_up):
        """Test put_targets."""
        event = boto3.client('events', region_name='us-east-1')
        event.put_rule(
            Name=self.event_name,
            ScheduleExpression=self.interval,
            State='ENABLED',
            Description=self.event_description
        )
        response = put_targets(self.stack_name,
                               self.lambda_arn,
                               self.toggle_parameter,
                               self.toggle_values)
        # assert rule['RuleArn'] == response['RuleArn']
        assert response['ResponseMetadata']['HTTPStatusCode'] == 200

    @mock_events
    def test_delete_event(self, set_up):
        """Test delete_event."""
        event = boto3.client('events', region_name='us-east-1')
        event.put_rule(
            Name=self.event_name,
            ScheduleExpression=self.interval,
            State='ENABLED',
            Description=self.event_description
        )
        response = delete_event(self.stack_name)
        assert response['ResponseMetadata']['HTTPStatusCode'] == 200

    # # currently unable to mock awslambda.add_permission or .remove_permission
    # # https://github.com/spulec/moto/issues/883
    # @mock_lambda
    # def test_lambda_add_resource_policy(self, set_up):
    #     """Test lambda_add_resource_policy."""
    #     aws_lambda = boto3.client('lambda')
    #     local_response = aws_lambda.add_permission(
    #         FunctionName=function_name,
    #         StatementId=self.statement_id,
    #         Action='lambda:InvokeFunction',
    #         Principal='events.amazonaws.com',
    #         SourceArn=self.rule_arn,
    #     )
    #     test_response = lambda_add_resource_policy(self.event_name)
    #     assert test_response['ResponseMetadata']['HTTPStatusCode'] == 200
    #     expected_response = {
    #                         "Sid": "AWSEvents_{}_{}".format(self.event_name, function_name),
    #                         "Effect": "Allow",
    #                         "Principal": {
    #                             "Service": "events.amazonaws.com"
    #                             },
    #                         "Action": "lambda:InvokeFunction",
    #                         "Resource": "{}:cfn-update-scheduler-dev-cwe_update_target".format(self.lambda_arn),
    #                         "Condition": {
    #                             "ArnLike": {
    #                                 "AWS:SourceArn": self.rule_arn
    #                                 }
    #                             }
    #                         }
    #     assert test_response['Statement'] == expected_response
    #
    # def test_lambda_remove_resource_policy(self, set_up):
    #     """Test lambda_remove_resource_policy."""
    #     lambda_remove_resource_policy(self.event_name)


# test_create_event = {
#   "RequestType": "Create",
#   "ServiceToken": "arn:aws:lambda:{}:{}:function:{}".format(region, account_id, function_name),
#   "ResponseURL": "https://test.com",
#   "StackId": "arn:aws:cloudformation:{}:{}:stack/test-stack/2858e0b0-142c-11e8-9e11-500c28902e99".format(region, account_id),
#   "RequestId": "95cfd8db-3b44-46c6-868b-f2603b4992ea",
#   "LogicalResourceId": "AutoUpdateStack",
#   "ResourceType": "Custom::AutoUpdateStack",
#   "ResourceProperties": {
#     "ServiceToken": "arn:aws:lambda:{}:{}:function:{}".format(region, account_id, function_name),
#     "ToggleValues": ["A", "B"],
#     "ToggleParameter": "ForceUpdateToggle",
#     "UpdateSchedule": "rate(5 minutes)",
#     "StackName": "test-stack"
#   }
# }
#
# test_delete_event = 'test2'
# test_update_event = 'test3'
#
#
# @pytest.fixture(event=[test_create_event, test_delete_event, test_update_event], context="")
# def test_lambda_handler(event, context):
#     """Test delete_event."""
#     lambda_handler(event, context)
