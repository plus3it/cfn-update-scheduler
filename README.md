# CFN Update Scheduler

A [Serverless framework](https://serverless.com/learn/) deployable Lambda function pair that generates a CloudWatch rule that will automatically perform stack updates when called as a custom resource within CloudFormation.

## Getting Started

These instructions will get you a copy of the project up and running on your local machine for development and testing purposes. See deployment for notes on how to deploy the project on a live system.

### Prerequisites

1. Command line access to an AWS account with the [required permissions](##Deployment)

2. Ensure your environment has been configured in accordance with the [AWS installation instructions for the serverless framework](https://serverless.com/framework/docs/providers/aws/guide/installation/).

3. Install the [serverless-pseudo-parameters](https://www.npmjs.com/package/serverless-pseudo-parameters) plugin

```
npm install serverless-pseudo-parameters
```

### Installing

1. Download this repository

```
git clone git://github.com/userhas404d/cfn_update_scheduler.git
```

2. Using the Serverless framework, deploy the project to your AWS environment

```
sls deploy
```

## Running the tests

Explain how to run the automated tests for this system

### Break down into end to end tests

Explain what these tests test and why

```
Give an example
```

### And coding style tests

Explain what these tests test and why

```
Give an example
```

## Deployment

1. Deploy the included CloudFormation template or add a custom resource to your own template as outlined below.

*Note:*
*The included CloudFormation template utilizes the following ADDITIONAL custom resource: [`AmiIdLookup` custom resource](https://github.com/userhas404d/cfn-look-up-ami-ids)*

2. During stack deployment include your stack's desired update interval as a cron expression or `rate(value unit)` for the `UpdateSchedule` parameter. See the following AWS documentation for further details: [Schedule Expressions for Rules](https://docs.aws.amazon.com/AmazonCloudWatch/latest/events/ScheduledEvents.html)

3. Confirm the CloudWatch rule has been created for your stack by navigating to the CloudWatch > Rules section of your AWS account's web console.

#### CloudFormation template required Parameters:
A toggle is utilized to force CloudFormation to re-evaluate a resource during the stack update.

```
"ForceUpdateToggle" :
{
    "Description" : "A/B toggle that forces a change to a LaunchConfig property, triggering the stack Update Policy",
    "Type" : "String",
    "Default" : "A",
    "AllowedValues" :
       [
          "A",
          "B"
       ]
},
"UpdateSchedule" :
{
  "Description" : "Time interval between auto stack updates",
  "Type" : "String",
  "Default" : "5 minutes"
}
```
#### CloudFormation template required Resources:
The included [example template](https://github.com/userhas404d/cfn_update_scheduler/blob/master/Lambda-cfn-auto-update.template) utilizes this toggle to update the value of the `AdditionalInfo` property of an EC2 instance. This in turn forces the [`AmiIdLookup` custom resource](https://github.com/userhas404d/cfn-look-up-ami-ids) to always return the latest AMI Id on stack update.
```
"Resources" : {
    "SampleInstance": {
      "Type": "AWS::EC2::Instance",
      "Properties": {
        "InstanceType"   : { "Ref" : "InstanceType" },
        "ImageId": { "Fn::GetAtt" : [ "AmiIdLookup", "Id" ] },
        "AdditionalInfo" : { "Ref" : "ForceUpdateToggle"}
      }
    },
    "AmiIdLookup" :
    {
          "Type" : "Custom::AmiIdLookup",
          "Properties" :
          {
              "ServiceToken" :
              { "Fn::Join" : [ ":", [
                  "arn:aws:lambda",
                  { "Ref" : "AWS::Region" },
                  { "Ref" : "AWS::AccountId" },
                  "function:cfn-look-up-amis-ids-dev-cfn-look-up-amis-ids"
              ]]},
              "Region" : { "Ref" : "AWS::Region" },
              "AmiNameSearchString" : { "Ref" : "AmiNameSearchString" },
              "TemplateAmiID" : { "Ref" : "AmiId" },
              "AutoUpdateAmi" : { "Ref" : "AutoUpdateAmi" }
          }
    }
```
And finally the custom resource that references the `cfn_update_broker` Lambda function.
```
"AutoUpdateStack" :
{
      "Type" : "Custom::AutoUpdateStack",
      "Properties" :
      {
          "ServiceToken" :
          { "Fn::Join" : [ ":", [
              "arn:aws:lambda",
              { "Ref" : "AWS::Region" },
              { "Ref" : "AWS::AccountId" },
              "function:cfn-update-scheduler-dev-cfn_auto_update_broker"
          ]]},
          "StackName" : { "Ref" : "AWS::StackName" },
          "UpdateSchedule": { "Fn::Join" : [
            "", ["rate(",{ "Ref" : "UpdateSchedule" }, ")"]
            ]},
          "ToggleParameter" : "ForceUpdateToggle",
          "ToggleValues" : ["A","B"]
      }
}
```
## Functionality Overview

When this project's serverless package is deployed two lambda functions will be created.

### `cfn_auto_update_broker`

This function is running with a least privilege IAM role (`cfn-update-scheduler-dev-us-east-1-lambdaRole`) and operates as the listener to the CloudWatch custom resource.

It operates as follows:

* On receiving a CREATE event :

    - Create CloudWatch rule and include the stack specific `ForceUpdateToggle` and `ToggleValues` in the rule's `Constant`

    - Add stack to the CloudWatch rule target

    - Add required permissions to the `cwe_update_target` function to allow the event to trigger the update.


* On receiving a UPDATE event:

  - update the CloudWatch rule schedule and `Constant`

* On receiving a DELETE event:

  - delete the CloudWatch rule.

### `cwe_update_target`

This function is invoked by the scheduled Cloudwatch rules. On receiving the rule's event it does the following:

* Assumes an administrative role (`StackUpdateRole`) to perform stack updates.

  - It assumes this role for a default of 3600 seconds.


  *Note: `StackUpdateRole` does NOT exercise principles of least privilege. This will be addressed in a follow on update.*

  * Swaps the value of the `ForceUpdateToggle` from A to B or B to A accordingly.

    - These values are customizable but currently the list must include two separate values.


  * Updates the target stack utilizing the assumed role and the updated `ForceUpdateToggle` values.

## Built With

* [Serverless](https://serverless.com/learn/) - The deployment method used
* [Boto 3](http://boto3.readthedocs.io/en/latest/) - programatic AWS resource manipulation
* [cfnresponse.py](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-lambda-function-code.html) - module to send responses to AWS resources

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details

## To Do
- unit testing with moto https://github.com/spulec/moto
- document testing..
- move resource declarations out of globals and into function parameters
- better error handling
- send notifications to a sns topic on update or failure.
- improve readme
