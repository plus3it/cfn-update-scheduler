"""Find and update tagged cfn stacks."""

import boto3


def get_stack_tags():
    """Find stacks that meet requirements."""
    print("running get_stack_tags")
    stack_session = boto3.client('cloudformation')
    paginator = stack_session.get_paginator('list_stacks')
    response_iterator = paginator.paginate(
      StackStatusFilter=['UPDATE_COMPLETE', 'CREATE_COMPLETE'])
    for page in response_iterator:
        stack = page['StackSummaries']
        for output in stack:
            print(output['StackName'])
            print(output['Tags'])


def validate(stack):
    """Confirm if stack requires update."""
    '''Return False to trigger the canary

    Currently this simply checks whether the EXPECTED string is present.
    However, you could modify this to perform any number of arbitrary
    checks on the contents of SITE.
    '''


def lambda_handler(event, context):
    """Handle Lambda input."""
    get_stack_tags()
