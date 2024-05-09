from aws_cdk import (
    aws_s3 as s3,
    aws_codecommit as codecommit,
    aws_codebuild as codebuild,
    aws_codepipeline as codepipeline,
    aws_codepipeline_actions as codepipeline_actions,
    aws_iam as iam,
    Stack,
    CfnParameter,
    Fn,
    RemovalPolicy
)
from constructs import Construct


class CdkPipelineStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        project_url = CfnParameter(self, "projectUrl",
                                   type="String",
                                   description="My software pipeline delivery template using Cloudformation and CodeCommit")

        s3_bucket_name = CfnParameter(self, "S3BucketName",
                                      type="String",
                                      description="S3 bucket name for storing artifacts")

        repository_name = CfnParameter(self, "RepositoryName",
                                       type="String",
                                       description="CodeCommit repository name")

        artifact_bucket = s3.Bucket(self, "ArtifactBucket",
                                    bucket_name=s3_bucket_name.value_as_string,
                                    encryption=s3.BucketEncryption.S3_MANAGED,
                                    removal_policy=RemovalPolicy.DESTROY)

        artifact_bucket.add_to_resource_policy(iam.PolicyStatement(
            actions=["s3:PutObject"],
            resources=[f"{artifact_bucket.bucket_arn}/*"],
            conditions={"StringNotEquals": {"s3:x-amz-server-side-encryption": "aws:kms"}},
            effect=iam.Effect.DENY,
            principals=[iam.AnyPrincipal()]
        ))

        repository = codecommit.Repository(self, "JavaProjectRepository",
                                           repository_name=repository_name.value_as_string)

        build_project_role = iam.Role(self, "AppBuildRole",
                                      assumed_by=iam.ServicePrincipal("codebuild.amazonaws.com"),
                                      managed_policies=[iam.ManagedPolicy.from_aws_managed_policy_name("AmazonS3ReadOnlyAccess")],
                                      inline_policies={
                                          "CodeBuildAccess": iam.PolicyDocument(
                                              statements=[
                                                  iam.PolicyStatement(
                                                      actions=["s3:PutObject", "s3:GetObject", "s3:GetObjectVersion",
                                                               "s3:GetBucketAcl", "s3:GetBucketLocation"],
                                                      resources=[f"arn:aws:s3:::{s3_bucket_name.value_as_string}",
                                                                 f"arn:aws:s3:::{s3_bucket_name.value_as_string}/*"]
                                                  )
                                              ]
                                          )
                                      })

        build_project = codebuild.Project(self, "AppBuildProject",
                                          project_name="AppBuildProject",
                                          role=build_project_role,
                                          environment=codebuild.BuildEnvironment(
                                              build_image=codebuild.LinuxBuildImage.STANDARD_5_0,
                                              compute_type=codebuild.ComputeType.SMALL),
                                          source=codebuild.Source.code_commit(repository=repository),
                                          artifacts=codebuild.Artifacts.s3(
                                              bucket=artifact_bucket,
                                              include_build_id=False,
                                              package_zip=True,
                                              path='',
                                              identifier='BuildOutput',
                                              encryption=True
                                          ))

        pipeline_role = iam.Role(self, "CodePipelineServiceRole",
                                 assumed_by=iam.ServicePrincipal("codepipeline.amazonaws.com"),
                                 managed_policies=[iam.ManagedPolicy.from_aws_managed_policy_name("AmazonS3ReadOnlyAccess")],
                                 inline_policies={
                                     "ec2codedeploy": iam.PolicyDocument(
                                         statements=[
                                             iam.PolicyStatement(
                                                 actions=["s3:GetObject", "s3:GetBucketAcl", "s3:GetBucketLocation"],
                                                 resources=[artifact_bucket.bucket_arn,
                                                            f"{artifact_bucket.bucket_arn}/*"]
                                             )
                                         ]
                                     )
                                 })

        codepipeline.Pipeline(self, "AppPipeline",
                              pipeline_name="AppPipeline",
                              role=pipeline_role,
                              artifact_bucket=artifact_bucket,
                              stages=[
                                  codepipeline.StageProps(
                                      stage_name="Source",
                                      actions=[
                                          codepipeline_actions.CodeCommitSourceAction(
                                              action_name="SourceAction",
                                              repository=repository,
                                              branch="master",
                                              output=codepipeline.Artifact("SourceOutput")
                                          )
                                      ]
                                  ),
                                  codepipeline.StageProps(
                                      stage_name="Build",
                                      actions=[
                                          codepipeline_actions.CodeBuildAction(
                                              action_name="BuildAction",
                                              project=build_project,
                                              input=codepipeline.Artifact("SourceOutput"),
                                              outputs=[codepipeline.Artifact("BuildOutput")]
                                          )
                                      ]
                                  )
                              ])


