@router.get("/api/transcript/{filename:path}")
def get_transcript_from_s3(filename: str, current_user: User = Depends(get_current_user)):
    import boto3

    s3 = boto3.client("s3", region_name=settings.aws_region)
    base_name = os.path.splitext(filename)[0]

    try:
        # Construct the correct key for the transcript .txt file
        transcript_key = f"transcripts/{base_name}.txt"
        txt_obj = s3.get_object(Bucket=settings.s3_bucket,
                                Key=transcript_key)
        text = txt_obj["Body"].read().decode("utf-8")
    except Exception:
        raise HTTPException(status_code=404, detail="Transcript not found.")

    # Construct the correct key for the segments .json file
    segments_key = f"transcripts/{base_name}.json"

    try:
        seg_obj = s3.get_object(Bucket=settings.s3_bucket, Key=segments_key)
        segments = json.loads(seg_obj["Body"].read().decode("utf-8"))
    except Exception:
        # If segments file doesn't exist, return an empty list as before
        segments = []

    return JSONResponse(content={"transcript": text, "segments": segments})
