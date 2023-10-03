#!/usr/bin/env bash

ansible --version
terraform --version
ls -l /tmp


# Prepare config yaml files.
zone_id=`aws route53 list-hosted-zones-by-name --dns-name geneontology.io. --max-items 1  --query "HostedZones[].Id" --output text  | tr "/" " " | awk '{ print $2 }'`
record_name=cicd-test-go-fastapi.geneontology.io

sed "s/REPLACE_ME_WITH_ZONE_ID/$zone_id/g" ./github/config-instance.yaml.sample > ./github/config-instance.yaml
sed -i "s/REPLACE_ME_WITH_RECORD_NAME/$record_name/g" ./github/config-instance.yaml

s3_cert_bucket=$S3_CERT_BUCKET
ssl_certs="s3:\/\/$s3_cert_bucket\/geneontology.io.tar.gz"
sed "s/REPLACE_ME_WITH_URI/$ssl_certs/g" ./github/config-stack.yaml.sample > ./github/config-stack.yaml
sed -i "s/REPLACE_ME_WITH_RECORD_NAME/$record_name/g" ./github/config-stack.yaml

# Provision aws instance and fast-api stack.

go-deploy -init --working-directory aws -verbose

go-deploy --working-directory aws -w test-go-deploy-api -c ./github/config-instance.yaml -verbose

go-deploy --working-directory aws -w test-go-deploy-api -output -verbose

go-deploy --working-directory aws -w test-go-deploy-api -c ./github/config-stack.yaml -verbose

ret=1
total=${NUM_OF_RETRIES:=12}


for (( c=1; c<=$total; c++ ))
do
   echo wget http://$record_name/openapi.json
   wget  --no-dns-cache http://$record_name/openapi.json
   ret=$?
   if [ "${ret}" == 0 ]
   then
        echo "Success"
        break
   fi
   echo "Got exit_code=$ret.Going to sleep. Will retry.attempt=$c:total=$total"
   sleep 10
done

if [ "${ret}" == 0 ]
then
   echo "Parsing json file openapi.json ...."
   python3 -c "import json;fp=open('openapi.json');json.load(fp)"
   ret=$?
fi


# Destroy
go-deploy --working-directory aws -w test-go-deploy-api -destroy -verbose
exit $ret 