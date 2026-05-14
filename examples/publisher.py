import os
from intent_bus import IntentClient
from intent_bus.exceptions import IntentBusError

# Uses INTENT_API_KEY from environment or ~/.apikey automatically
try:
    with IntentClient() as client:
        print("Publishing job to the bus...")
        
        # Publish a private intent to the 'image-processing' namespace
        job = client.publish(
            goal="resize_image",
            payload={"url": "s3://bucket/image1.png", "width": 800},
            namespace="image-processing",
            required_capability="gpu"
        )
        
        if job:
            print(f"Success! Job ID: {job.id}")
            print(f"Status: {job.status}")
            
except IntentBusError as e:
    print(f"Failed to publish: {e}")
