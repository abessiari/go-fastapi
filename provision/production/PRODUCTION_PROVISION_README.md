# go-fastapi Deployment

This guide describes the deployment of the `go-fastapi` stack to AWS using Terraform, ansible, and the "go-deploy" Python library. 

### Prerequisites: Note, we have a docker-based environment with all these tools installed. 

#### software:

- go-fastapi checkout 
- Terraform: v1.1.4
- Ansible: 2.10.7
- go-deploy: `poetry install go-deploy==0.4.1` # requires python >=3.8

#### configuration files:

  - vars.yaml
  - docker-vars.yaml
  - s3-vars.yaml
  - ssl-vars.yaml
  - qos-vars.yaml
  - stage.yaml
  - start_services.yaml

#### artifacts deployed to a staging directory on AWS:

  - s3 credentials files (used to push Apache logs and pull ssl credentials from the associated s3 bucket)
  - qos.conf and robots.txt (used for Apache mitigation)
  - docker-production-compose.yaml
  - various configuration files

#### DNS: 

DNS record is used for `go-fastapi`. Once the instance has been provisioned, you would need to point this record to the elastic IP of the VM. For testing purposes, you can use: `aes-test-go-fastapi.geneontology.org`

#### SSH Keys:

For testing purposes you can you your own ssh keys. But for production please ask for the go ssh keys.

## STANDARD OPERATING PROCEDURE 

#### Spin up the provided dockerized development environment:

```bash
docker run --name go-dev -it geneontology/go-devops-base:tools-jammy-0.4.1  /bin/bash
git clone https://github.com/geneontology/go-fastapi.git
cd go-fastapi/provision
```

#### Prepare AWS credentials:

The credentials are used by Terraform to provision the AWS instance and by the provisioned instance to access the certificate store and the s3 buckets used to store Apache logs.  Copy and modify the aws credential file to the default location `/tmp/go-aws-credentials` 

Note: you will need to supply an `aws_access_key_id` and `aws_secret_access_key`. These will be marked with `REPLACE_ME` in the `go-aws-credentials.sample` file.

```bash
cp production/go-aws-credentials.sample /tmp/go-aws-credentials
nano /tmp/go-aws-credentials  # update the `aws_access_key_id` and `aws_secret_access_key`
```

#### Prepare and initialize the S3 Terraform backend:

```bash

# The S3 backend is used to store the terraform state.
cp ./production/backend.tf.sample ./aws/backend.tf
cat ./aws/backend.tf

# Use the AWS cli to make sure you have access to the terraform s3 backend bucket
export AWS_SHARED_CREDENTIALS_FILE=/tmp/go-aws-credentials

# S3 bucket
aws s3 ls s3://REPLACE_ME_WITH_TERRAFORM_BACKEND_BUCKET 
go-deploy -init --working-directory aws -verbose

# Use these commands to figure out the name of an existing workspace if any. The name should have a pattern `production-YYYY-MM-DD`
go-deploy --working-directory aws -list-workspaces -verbose 
```

#### Provision instance on AWS:

If a workspace exists above, then you can skip the provisioning of the AWS instance.  Else, create a workspace using the following namespace pattern `production-YYYY-MM-DD`.  e.g.: `production-2023-01-30`

* Remember you can use the -dry-run and the -verbose options to test "go-deploy"

```bash
# copy `production/config-instance.yaml.sample` to another location and modify using vim or emacs.

cp ./production/config-instance.yaml.sample config-instance.yaml

# verify the location of the ssh keys for your AWS instance in your copy of `config-instance.yaml` under `ssh_keys`.
# verify location of the public ssh key in `aws/main.tf`

cp ./production/config-instance.yaml.sample config-instance.yaml
cat ./config-instance.yaml   # Verify contents and modify if needed.
go-deploy --workspace production-YYYY-MM-DD --working-directory aws -verbose --conf config-instance.yaml

# The previous command creates a terraform tfvars. These variables override the variables in `aws/main.tf`
```

Note: write down the IP address of the AWS instance that is created. This can be found in production-YYYY-MM-DD.cfg

#### deploy stack to AWS:

1. Make DNS names for go-fastapi point to the public IP address on AWS Route 53
2. Location of SSH keys may need to be replaced after copying config-stack.yaml.sample
3. s3 credentials are placed in a file using the format described above
4. s3 uri if SSL is enabled. Location of SSL certs/key
5. QoS mitigation if QoS is enabled
6. Use the same workspace name as in the previous step

```bash
cp ./production/config-stack.yaml.sample ./config-stack.yaml
cat ./config-stack.yaml    # Verify contents and modify if needed.
export ANSIBLE_HOST_KEY_CHECKING=False
go-deploy --workspace production-YYYY-MM-DD --working-directory aws -verbose --conf config-stack.yaml
```

#### Access go-fastapi from a browser:

We use health checks in the docker-compose file.  
Use go-fastapi dns name. http://{go-fastapi_host}/docs

#### Debugging:

- Use -dry-run and copy and paste the command and execute it manually
- ssh to the machine; username is ubuntu. Try using DNS names to make sure they are fine.
```bash
docker-compose -f stage_dir/docker-compose.yaml ps
docker-compose -f stage_dir/docker-compose.yaml down # whenever you make any changes 
docker-compose -f stage_dir/docker-compose.yaml up -d
docker-compose -f stage_dir/docker-compose.yaml logs -f 
```

#### Testing LogRotate:

```bash
docker exec -u 0 -it apache_fastapi bash # enter the container
cat /opt/credentials/s3cfg
echo $S3_BUCKET
aws s3 ls s3://$S3_BUCKET
logrotate -v -f /etc/logrotate.d/apache2 # Use -f option to force log rotation.
```

#### Testing Health Check:

```sh
docker inspect --format "{{json .State.Health }}" fastapi
```

#### Destroy Instance and Delete Workspace:

```bash
# Make sure you point to the correct workspace before destroying the stack.

terraform -chdir=aws workspace list
terraform -chdir=aws workspace select <name_of_workspace>
terraform -chdir=aws workspace show # shows the name of current workspace
terraform -chdir=aws show           # shows the state you are about to destroy
terraform -chdir=aws destroy        # You would need to type Yes to approve.

# Now delete the workspace.

terraform -chdir=aws workspace select default # change to default workspace
terraform -chdir=aws workspace delete <name_of_workspace>  # delete workspace.
```

### For Developers:
Use the recipe below to create a local, development environment for this application. 

```
# start docker container `go-dev` in interactive mode.

```bash
docker run --rm --name go-dev -it geneontology/go-devops-base:tools-jammy-0.4.1  /bin/bash

In the command above we used the `--rm` option which means the container will be deleted when you exit. If that is not the intent and you want to delete it later at your own convenience. Use the following `docker run` command.

```bash
docker run --name go-dev -it geneontology/go-devops-base:tools-jammy-0.4.1  /bin/bash
```

#### Exit or stop the container:

```bash
docker stop go-dev                   # stop container with the intent of restarting it. This is equivalent to `exit` inside the container.
docker start -ia go-dev              # restart and attach to the container.
docker rm -f go-dev                  # remove it for good.
```

#### Use `docker cp` to copy these credentials to /tmp:

```bash
docker cp /tmp/go-aws-credentials go-dev:/tmp/
docker cp /tmp/go-ssh go-dev:/tmp
docker cp /tmp/go-ssh.pub go-dev:/tmp
```

#### Then, within the docker image:

```bash
chown root /tmp/go-*
chgrp root /tmp/go-*
chmod 400 /tmp/go-ssh
```


 #### additional terraform commands? 
```
cat production-YYYY-MM-DD.tfvars.json

# The previous command creates an ansible inventory file.
cat production-YYYY-MM-DD-inventory.cfg

# Useful terraform commands to check what you have just done
terraform -chdir=aws workspace show   # current terraform workspace
terraform -chdir=aws show             # current state deployed ...
terraform -chdir=aws output           # public ip of aws instance
```