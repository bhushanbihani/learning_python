import json
import boto3
import PyPDF2
import io

s3_client = boto3.client("s3")
bedrock_client = boto3.client("bedrock-runtime", region_name="us-east-1")

BUCKET_NAME = "myaisummariserfileuploadbucket"

# Common CORS headers
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "https://myaisummariserstaticwebsite.s3-website-us-east-1.amazonaws.com",
    "Access-Control-Allow-Methods": "OPTIONS,POST",
    "Access-Control-Allow-Headers": "Content-Type",
}

def extract_text_from_s3(file_key):
    """
    Extract text from S3 PDF or TXT files.
    """
    file_obj = s3_client.get_object(Bucket=BUCKET_NAME, Key=file_key)
    file_content = file_obj["Body"].read()

    if file_key.endswith(".txt"):
        return file_content.decode("utf-8")
    elif file_key.endswith(".pdf"):
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_content))
        text = ""
        for page in pdf_reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text.strip()
    else:
        raise ValueError("Unsupported file type. Only PDF and TXT supported.")

def call_bedrock_titan(prompt):
    """
    Call Amazon Bedrock Titan Text G1 - Express for summarization
    """
    try:
        response = bedrock_client.invoke_model(
            modelId="amazon.titan-text-express-v1",
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "inputText": prompt,
                "textGenerationConfig": {
                    "temperature": 0.7,
                    "maxTokenCount": 500
                }
            })
        )
        result = json.loads(response["body"].read())
        return result["results"][0]["outputText"]
    except Exception as e:
        raise RuntimeError(f"Bedrock model call failed: {str(e)}")

def lambda_handler(event, context):
    print("Incoming event:", event)
    
    method = event.get("requestContext", {}).get("http", {}).get("method") or event.get("httpMethod")
    
    if method == "OPTIONS":
        return {"statusCode": 200, "headers": CORS_HEADERS, "body": ""}

    if method != "POST":
        return {"statusCode": 405, "headers": CORS_HEADERS, "body": json.dumps({"error": "Method not allowed"})}

    try:
        body = json.loads(event.get("body", "{}"))
        file_key = body.get("fileKey")
        role = body.get("role", "General")

        if not file_key:
            raise ValueError("Missing fileKey in request")

        # 1. Extract text from S3
        text = extract_text_from_s3(file_key)
        print("Extracted Text (first 500 chars):", text[:500])

        # 2. Build role-specific prompt
        prompt = f"""
You are an AI summarizer.
Role: {role}
Document: {text[:3000]}

Please return ONLY a JSON object with the following structure:
{{
  "summary": "A concise 2-3 sentence summary of the document.",
  "sentiment": "Neutral, Positive, or Negative",
  "insights": ["1-5 key insights from the document, each as a short sentence"],
  "actions": ["1-5 actionable steps derived from the document"],
  "risks": ["1-5 risks mentioned or implied in the document"]
}}

Instructions:
- Do NOT repeat the same content across fields.
- Each field should be concise and specific.
- Return valid JSON only, no extra text, no markdown, no backticks.
"""

        # 3. Call Bedrock Titan
        ai_output = call_bedrock_titan(prompt)
        print("AI Raw Output:\n", ai_output)

        # 4. Attempt JSON parsing, fallback to labeled text parsing
        try:
            parsed_output = json.loads(ai_output)
        except Exception:
            parsed_output = {
                "summary": "",
                "sentiment": "Neutral",
                "insights": [],
                "actions": [],
                "risks": []
            }
            lines = ai_output.splitlines()
            current_field = None
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                if line.lower().startswith("summary:"):
                    current_field = "summary"
                    parsed_output[current_field] = line[len("summary:"):].strip()
                elif line.lower().startswith("sentiment:"):
                    current_field = "sentiment"
                    parsed_output[current_field] = line[len("sentiment:"):].strip()
                elif line.lower().startswith("insights:"):
                    current_field = "insights"
                elif line.lower().startswith("actions:"):
                    current_field = "actions"
                elif line.lower().startswith("risks:"):
                    current_field = "risks"
                else:
                    if current_field in ["insights", "actions", "risks"]:
                        if line.startswith("-"):
                            parsed_output[current_field].append(line[1:].strip())
                        else:
                            parsed_output[current_field].append(line.strip())
                    elif current_field == "summary":
                        parsed_output[current_field] += " " + line

        print("Parsed Output:", parsed_output)
        return {"statusCode": 200, "headers": CORS_HEADERS, "body": json.dumps(parsed_output)}

    except Exception as e:
        print("Error:", str(e))
        return {"statusCode": 500, "headers": CORS_HEADERS, "body": json.dumps({"error": str(e)})}
