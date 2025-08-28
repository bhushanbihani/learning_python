import json
import boto3

# S3 client
s3_client = boto3.client('s3')
BUCKET_NAME = 'myaisummariserfileuploadbucket'  

ALLOWED_ORIGIN = "https://myaisummariserstaticwebsite.s3-website-us-east-1.amazonaws.com"

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "OPTIONS,POST",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Credentials": "false"
}

def lambda_handler(event, context):
    method = event.get('requestContext', {}).get('http', {}).get('method') or event.get('httpMethod')
    print("Lambda invoked. HTTP method:", method)
    print("Received body:", event.get("body"))

    if method == "OPTIONS":
        print("Handling CORS preflight request")
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": ""
        }

    if method == "POST":
        try:
            body = json.loads(event.get('body', '{}'))
            file_name = body.get('fileName')
            content_type = body.get('contentType', 'application/octet-stream')

            if not file_name:
                raise ValueError("Missing 'fileName' in request body")

            url = s3_client.generate_presigned_url(
                ClientMethod='put_object',
                Params={
                    'Bucket': BUCKET_NAME,
                    'Key': f'uploads/{file_name}',
                    'ContentType': content_type
                },
                ExpiresIn=3600  # 1 hour
            )

            response_body = {
                "url": url,
                "key": f"uploads/{file_name}"
            }

            return {
                "statusCode": 200,
                "headers": CORS_HEADERS,
                "body": json.dumps(response_body)
            }

        except Exception as e:
            print("Error:", str(e))
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": str(e)})
            }

    return {
        "statusCode": 405,
        "headers": CORS_HEADERS,
        "body": json.dumps({"error": "Method not allowed"})
    }
