from intent_bus import IntentClient, WorkerRuntime

def process_image(payload: dict) -> dict:
    """The handler function. Must return a dict or a raw value."""
    print(f"Downloading image from: {payload.get('url')}")
    print(f"Resizing to: {payload.get('width')}px")
    
    # Simulate work
    import time; time.sleep(1)
    
    # Return structured fulfillment
    return {
        "result": {"status": "resized", "s3_path": "s3://bucket/image1_800.png"},
        "result_type": "json"
    }

if __name__ == "__main__":
    client = IntentClient()
    
    # Initialize the resilient runtime
    runtime = WorkerRuntime(
        client=client,
        worker_id="worker-node-alpha",
        capabilities=["gpu", "image-io"]
    )
    
    print("Worker starting. Press Ctrl+C to exit.")
    # This will block and poll indefinitely
    runtime.listen(
        goal="resize_image",
        namespace="image-processing",
        handler=process_image
    )
